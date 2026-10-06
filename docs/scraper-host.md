# Scraper host

How to run Cardmarket scraper lanes on their own server, next to the staging API. One lane is one container: one Chrome, one sticky DataImpulse address, one request at a time. The design is in [cardmarket-price-reads-production-plan.md](./cardmarket-price-reads-production-plan.md), part 3.

Files:

| File | What it is |
|---|---|
| `compose.scraper-host.yaml` | Lanes `scraper-a` and `scraper-b`, same image and settings as the staging `scraper` service, ports bound to a private address |
| `docker/scraper-host.env.example` | The host's `.env`, without secrets |
| `scripts/scraper-host/bootstrap.sh` | One-time host setup: checks, Docker, `/opt/scanapp-scraper`, ufw for SSH only |
| `scripts/scraper-host/deploy.sh` | Syncs the build context from this checkout, builds, starts the lanes, waits for healthy, checks the API container can reach them |

## Server

Staging is Hetzner Cloud `ubuntu-4gb-fsn1-1` (Falkenstein, 4 GB, x86_64, public interface only).

- Hetzner Cloud, location **fsn1**, so the private network and latency match staging.
- An **x86** type with **8 GB RAM and 4 vCPU** (shared CX or CPX line, or dedicated CCX if solving checks is CPU bound). Not the ARM CAX line: the Dockerfile installs `google-chrome-stable`, which Google publishes for x86_64 only. `bootstrap.sh` stops on any other architecture.
- Ubuntu 24.04, your SSH key, 40 GB disk or more. The image is about 1.5 GB.

8 GB holds two lanes at 1.5 GiB each with room for a third and fourth. Each lane needs about one vCPU while it solves a Cloudflare check. Lane memory has no swap (`memswap_limit` equals `mem_limit`), because a swapping Chrome misses every deadline.

## Private network

The API sends `SCRAPER_API_KEY` as a bearer token over plain HTTP, so the lanes must never listen on a public address. Docker-published ports also bypass ufw. The compose file therefore binds every lane to `SCRAPER_BIND_ADDR` and refuses to start without it.

Pick one:

1. **Hetzner Cloud Network (recommended).** Create a network in `eu-central`, for example `10.0.0.0/16`, and attach both staging and the scraper server. Each gets an address such as `10.0.0.2` (staging) and `10.0.0.3` (scraper). Current Ubuntu images configure the new interface without a reboot. Check with `ip -br -4 addr` on both. Traffic on that network only reaches servers you attached.
2. **Tailscale.** Install it on both hosts and use the scraper's `100.x.y.z` address. Containers on staging reach it through the host's routes.

Set `SCRAPER_BIND_ADDR` to the scraper's private address from the option you picked.

## Firewall

- Hetzner Cloud Firewall on the scraper server: inbound TCP 22 from your admin addresses only, nothing else inbound. Cloud Firewalls apply to public interfaces, so private network traffic still flows.
- Outbound stays open. The build needs Docker Hub, PyPI and `dl.google.com`. The lanes need `gw.dataimpulse.com:823`.
- `bootstrap.sh` enables ufw with only OpenSSH allowed. `SKIP_UFW=1` leaves ufw alone.

## Set up

1. Create the server and the network, as above.
2. Bootstrap, from this repository:

   ```bash
   ssh root@<scraper-public-ip> 'bash -s' < scripts/scraper-host/bootstrap.sh
   ```

3. Write the host's `.env`:

   ```bash
   scp docker/scraper-host.env.example root@<scraper-public-ip>:/opt/scanapp-scraper/.env
   ssh root@<scraper-public-ip> 'chmod 600 /opt/scanapp-scraper/.env && ${EDITOR:-nano} /opt/scanapp-scraper/.env'
   ```

   `SCRAPER_API_KEY` and the `PROXY_*` values are the ones the staging scraper runs with. This prints secrets to your terminal:

   ```bash
   ssh auctaro-staging "docker inspect scanapp-scanapp-z1mwj4-scraper-1 --format '{{range .Config.Env}}{{println .}}{{end}}'" \
     | grep -E '^(SCRAPER_API_KEY|PROXY_)'
   ```

4. Deploy, from the same commit the API runs. The scraper imports `api/app/cardmarket_html.py`, so a different commit can parse pages differently from the API:

   ```bash
   SCRAPER_SSH=root@<scraper-public-ip> ./scripts/scraper-host/deploy.sh
   ```

   It ends by calling `/health` on both lanes from inside the staging API container. A failure there means the private network or `SCRAPER_BIND_ADDR` is wrong.

5. Optional smoke test of one real page. This costs one paid page:

   ```bash
   ssh auctaro-staging "docker exec scanapp-scanapp-z1mwj4-api-1 python -c \"
   import os, httpx
   r = httpx.post('http://10.0.0.3:8001/scrape',
       json={'url': 'https://www.cardmarket.com/en/Pokemon/Products/Singles/151/Blastoise-ex-V1-MEW009', 'session_id': 'smoke-a'},
       headers={'Authorization': 'Bearer ' + os.environ['SCRAPER_API_KEY']}, timeout=150)
   b = r.json(); print(r.status_code, b.get('outcome'), b.get('elapsed_ms'), len(b.get('rows') or []))
   \""
   ```

   Expect `200 offers` with rows. Replace the address with your `SCRAPER_BIND_ADDR`. Blastoise ex (151) already has a stored offers snapshot on staging, so the result can be compared.

## Point the API at the new host

**Before the lane pool exists (one lane).** `compose.dokploy.yaml` reads `SCRAPER_URL` from the environment and defaults to the local `http://scraper:8000`. In the Dokploy environment for scanapp, set `SCRAPER_URL=http://<SCRAPER_BIND_ADDR>:8001` and redeploy from Dokploy, not with a manual `docker compose`. The staging `scraper` container stays defined and idles at about 20 MB until it gets a request. Rollback: remove `SCRAPER_URL` and redeploy.

**After plan part 3 is merged.** Set `SCRAPER_URLS=http://<addr>:8001,http://<addr>:8002`. Then remove the staging `scraper` service from `compose.dokploy.yaml` to free its 1.5 GiB on the API host.

## Operate

All on the scraper host, in `/opt/scanapp-scraper`:

| Task | Command |
|---|---|
| Status | `docker compose -f compose.scraper-host.yaml --env-file .env ps` |
| Logs of one lane | `docker compose -f compose.scraper-host.yaml --env-file .env logs -f --tail 100 scraper-a` |
| Restart one lane | `docker compose -f compose.scraper-host.yaml --env-file .env restart scraper-a` |
| Memory per lane | `docker stats --no-stream` |
| Update | Run `deploy.sh` again from the new commit. Lanes are recreated one build later, a few seconds each |

Logs rotate at 5 × 20 MB per lane.

To add lane `c`: copy the `scraper-b` block in `compose.scraper-host.yaml` as `scraper-c` with `SCRAPER_LANE: c` and port `${SCRAPER_C_PORT:-8003}`, add `SCRAPER_C_PORT` to the host's `.env`, add `scraper-c` to `LANES` in `deploy.sh`, and add the URL to `SCRAPER_URLS`. Check that free memory stays above 1 GB with every lane busy.
