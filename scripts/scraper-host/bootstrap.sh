#!/usr/bin/env bash
# One-time setup of a new scraper host. Run on that host as root:
#   ssh root@<host> 'bash -s' < scripts/scraper-host/bootstrap.sh
# Set SKIP_UFW=1 to leave the host firewall alone.
set -euo pipefail

REMOTE_DIR="${REMOTE_DIR:-/opt/scanapp-scraper}"
MIN_MEM_MB="${MIN_MEM_MB:-7500}"

if [[ "$(id -u)" != "0" ]]; then
  echo "run as root" >&2
  exit 1
fi

arch="$(uname -m)"
if [[ "$arch" != "x86_64" ]]; then
  echo "this host is $arch. google-chrome-stable is only published for x86_64; use an x86 server type" >&2
  exit 1
fi

mem_mb="$(awk '/MemTotal/ {print int($2 / 1024)}' /proc/meminfo)"
cpus="$(nproc)"
echo "== host: $arch, ${mem_mb} MB RAM, ${cpus} vCPU"
if (( mem_mb < MIN_MEM_MB )); then
  echo "warning: under ${MIN_MEM_MB} MB. Each lane is limited to 1.5 GiB; plan one lane per 2 GB and keep 1 GB for the host" >&2
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "== install docker"
  curl -fsSL https://get.docker.com | sh
fi
docker compose version

echo "== private addresses"
ip -br -4 addr | grep -v -E '^(lo|docker|br-|veth)' || true
command -v tailscale >/dev/null 2>&1 && tailscale ip -4 || true

mkdir -p "$REMOTE_DIR"
chmod 700 "$REMOTE_DIR"
echo "== created $REMOTE_DIR"

if [[ "${SKIP_UFW:-}" != "1" ]] && command -v ufw >/dev/null 2>&1; then
  echo "== ufw: allow ssh, deny other inbound"
  ufw allow OpenSSH
  ufw default deny incoming
  ufw default allow outgoing
  ufw --force enable
  ufw status verbose
fi

echo
echo "next: copy docker/scraper-host.env.example to $REMOTE_DIR/.env, fill it in, chmod 600,"
echo "then run scripts/scraper-host/deploy.sh from the repository."
