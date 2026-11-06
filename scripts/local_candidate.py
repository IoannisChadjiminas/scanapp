#!/usr/bin/env python3
"""Run a catalogue candidate on this computer instead of the staging host.

The API container is built from docker/api.Dockerfile for linux/amd64 (the
staging architecture, so reference-feature bundles keep their processing
contract) and configured from `docker compose -f compose.dokploy.yaml config`,
so thresholds, flags and the 2 GiB memory limit are the ones staging uses.
Only the catalogue release file, the PlanetScale credentials file and the data
folder are local. Prices, the scraper and the portfolio database are off.

    python3 scripts/local_candidate.py up enfive --release-env cand.env \\
        --planetscale-env ~/keys/planetscale-readonly.env --data-dir data/staging-data
    python3 scripts/local_candidate.py panel enfive --panel panel.json --photos-root photos
    python3 scripts/local_candidate.py probe enfive --audit-dir audit [--limit 20]
    python3 scripts/local_candidate.py rollback enfive --parent-env parent.env
    python3 scripts/local_candidate.py status enfive
    python3 scripts/local_candidate.py down enfive

Each finished check is written to .local-candidate/<name>/gates.json under a
fingerprint of the release file, feature manifest, API code and inputs. Running
a check again with the same fingerprint prints the stored result and skips the
work; --force runs it anyway. Nothing here writes to PlanetScale or staging.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".local-candidate"
IMAGE = "scanapp-api:local-amd64"
# Local data entries the API writes itself; everything else is mounted read-only.
WRITABLE = {"catalog.sqlite", "results.sqlite", "captures", "review"}
# Price and account features need other services and never change matching.
LOCAL_ENV = {
    "SCRAPER_ENABLED": "false",
    "DAILY_PRICES_ENABLED": "false",
    "PORTFOLIO_DATABASE_URL": "",
    "SCAN_PRICE_SERVER_READ": "off",
    "PRICE_GUIDE_ENABLED": "false",
    "TCGDEX_PRICES_ENABLED": "false",
}


def read_env(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def host_path(container_path: str, data_dir: Path) -> Path | None:
    """Where a /data/... path from the release file lives on this computer."""
    path = Path(container_path)
    if not path.is_relative_to("/data"):
        return None
    return data_dir / path.relative_to("/data")


def data_mounts(data_dir: Path) -> list[str]:
    mounts = []
    for entry in sorted(data_dir.iterdir()):
        if entry.name.startswith(".") or entry.name in WRITABLE:
            continue
        mounts.append(f"{entry.resolve()}:/data/{entry.name}:ro")
    return mounts


def api_code_digest() -> str:
    """HEAD plus any uncommitted change under api/ and docker/."""
    head = git("rev-parse", "HEAD")
    diff = git("diff", "HEAD", "--", "api", "docker", "compose.dokploy.yaml")
    return sha256((head + "\n" + diff).encode())


def git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    return result.stdout if result.returncode == 0 else ""


def fingerprint(config: dict, release_env: Path) -> dict:
    release = read_env(release_env)
    parts = {"release_env": sha256(release_env.read_bytes()), "api_code": api_code_digest()}
    data_dir = Path(config["data_dir"])
    for key in ("REFERENCE_FEATURES_DIR", "ARTWORK_BUNDLE_DIR"):
        if release.get(key):
            local = host_path(release[key], data_dir)
            manifest = local / "manifest.json" if local else None
            parts[key.lower()] = sha256(manifest.read_bytes()) if manifest and manifest.is_file() else "missing"
    if config.get("compose_env"):
        parts["compose_env"] = sha256(Path(config["compose_env"]).read_bytes())
    parts["all"] = sha256(json.dumps(parts, sort_keys=True).encode())
    return parts


class Candidate:
    def __init__(self, name: str) -> None:
        self.name = name
        self.dir = STATE / name
        self.config_path = self.dir / "config.json"

    @property
    def config(self) -> dict:
        if not self.config_path.is_file():
            raise SystemExit(f"No local candidate {self.name!r}; run `up` first")
        return json.loads(self.config_path.read_text())

    # Compose -------------------------------------------------------------

    def resolved_api(self, release_env: Path, config: dict) -> dict:
        env = dict(os.environ, CATALOGUE_RELEASE_ENV_FILE=str(release_env),
                   PLANETSCALE_ENV_FILE=config["planetscale_env"])
        command = ["docker", "compose", "-f", str(ROOT / "compose.dokploy.yaml")]
        if config.get("compose_env"):
            command += ["--env-file", config["compose_env"]]
        command += ["config", "--format", "json", "api"]
        result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
        if result.returncode:
            raise SystemExit("docker compose config failed:\n" + result.stderr)
        return json.loads(result.stdout)["services"]["api"]

    def compose_file(self, project: str, release_env: Path, port: int,
                     tool_mounts: list[str] | None = None) -> Path:
        config = self.config
        api = self.resolved_api(release_env, config)
        api.pop("env_file", None)  # compose config already merged it into environment
        api["environment"] = {**api.get("environment", {}), **LOCAL_ENV}
        api.update(platform="linux/amd64", image=IMAGE, restart="no",
                   ports=[f"127.0.0.1:{port}:8000"])
        api.pop("networks", None)
        data = data_mounts(Path(config["data_dir"]))
        api["volumes"] = [
            {"type": "volume", "source": "scanapp-data", "target": "/data"},
            {"type": "volume", "source": "scanapp-tmp", "target": "/tmp/scanapp"},
            *data,
        ]
        tools = {key: value for key, value in api.items() if key not in {"ports", "healthcheck", "build"}}
        tools.update(
            # A second runtime for the probe gets its own allowance; the API
            # keeps the staging limit so a pass also means it fits staging.
            mem_limit=config.get("tools_mem", "4g"),
            memswap_limit=config.get("tools_mem", "4g"),
            profiles=["tools"],
            volumes=[*api["volumes"], f"{ROOT / 'api' / 'scripts'}:/app/scripts:ro",
                     *(tool_mounts or [])],
        )
        document = {"name": project, "services": {"api": api, "tools": tools},
                    "volumes": {"scanapp-data": {}, "scanapp-tmp": {}}}
        path = self.dir / f"{project}.compose.json"
        path.write_text(json.dumps(document, indent=2))
        path.chmod(0o600)  # holds the PlanetScale read-only credentials
        return path

    def compose(self, path: Path, *args: str, check: bool = True, capture: bool = False):
        command = ["docker", "compose", "-f", str(path), *args]
        result = subprocess.run(command, cwd=ROOT, text=True, capture_output=capture)
        if check and result.returncode:
            raise SystemExit(f"{' '.join(command)} failed")
        return result

    # Gates ---------------------------------------------------------------

    def gates(self) -> dict:
        path = self.dir / "gates.json"
        return json.loads(path.read_text()) if path.is_file() else {}

    def record(self, gate: str, key: str, passed: bool, detail: dict) -> None:
        gates = self.gates()
        gates[gate] = {"key": key, "passed": passed, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                       "detail": detail}
        (self.dir / "gates.json").write_text(json.dumps(gates, indent=2, sort_keys=True) + "\n")
        print(json.dumps({"gate": gate, "passed": passed, **detail}), flush=True)
        if not passed:
            raise SystemExit(f"{gate} failed")

    def already(self, gate: str, key: str, force: bool) -> bool:
        stored = self.gates().get(gate)
        if not force and stored and stored["key"] == key and stored["passed"]:
            print(json.dumps({"gate": gate, "skipped": "passed with the same inputs", "at": stored["at"]}))
            return True
        return False


def wait_ready(candidate: Candidate, path: Path, port: int, timeout: float) -> dict:
    url = f"http://127.0.0.1:{port}/api/v1/health"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                health = json.loads(response.read())
            if health.get("ready"):
                return health
            if health.get("detail"):
                raise SystemExit("API loaded with an error: " + str(health["detail"]))
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            pass
        state = container_state(candidate, path)
        if state and state.get("OOMKilled"):
            raise SystemExit("API ran out of memory while loading; it would not fit staging either")
        if state and state.get("Status") == "exited":
            candidate.compose(path, "logs", "--tail", "60", "api", check=False)
            raise SystemExit("API exited while loading")
        time.sleep(3)
    raise SystemExit("API was not ready in time")


def container_id(candidate: Candidate, path: Path) -> str:
    result = candidate.compose(path, "ps", "-a", "-q", "api", check=False, capture=True)
    return result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""


def container_state(candidate: Candidate, path: Path) -> dict | None:
    cid = container_id(candidate, path)
    if not cid:
        return None
    result = subprocess.run(["docker", "inspect", "-f", "{{json .State}}", cid], capture_output=True, text=True)
    return json.loads(result.stdout) if result.returncode == 0 else None


class PeakMemory:
    """Samples the API container while a check runs."""

    def __init__(self, cid: str) -> None:
        self.cid, self.peak, self._stop = cid, 0, threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self._stop.is_set():
            result = subprocess.run(["docker", "stats", "--no-stream", "--format", "{{json .}}", self.cid],
                                    capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip():
                used = json.loads(result.stdout)["MemUsage"].split("/")[0].strip()
                self.peak = max(self.peak, parse_bytes(used))
            self._stop.wait(1)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        self._thread.join()


def parse_bytes(text: str) -> int:
    units = {"B": 1, "KIB": 1024, "MIB": 1024**2, "GIB": 1024**3, "KB": 1000, "MB": 1000**2, "GB": 1000**3}
    text = text.strip().upper()
    for unit in sorted(units, key=len, reverse=True):
        if text.endswith(unit):
            return int(float(text[: -len(unit)]) * units[unit])
    return int(float(text))


def limit_bytes(value) -> int:
    if isinstance(value, int):
        return value
    text = str(value).strip().lower()
    scale = {"k": 1024, "m": 1024**2, "g": 1024**3}.get(text[-1:], 1)
    return int(float(text.rstrip("kmgb")) * scale)


# Commands -------------------------------------------------------------------

def cmd_up(args) -> None:
    candidate = Candidate(args.name)
    candidate.dir.mkdir(parents=True, exist_ok=True)
    release_env = args.release_env.resolve()
    release = read_env(release_env)
    for key in ("PLANETSCALE_SCHEMA", "PLANETSCALE_IMPORT_ID"):
        if not release.get(key):
            raise SystemExit(f"{release_env} has no {key}")
    data_dir = args.data_dir.resolve()
    if not (data_dir / "models" / "dinov2_small.onnx").is_file():
        raise SystemExit(f"{data_dir} has no models/dinov2_small.onnx; point --data-dir at a copy of staging /data")
    for key in ("REFERENCE_FEATURES_DIR", "ARTWORK_BUNDLE_DIR"):
        if release.get(key):
            local = host_path(release[key], data_dir)
            if local is None or not local.is_dir():
                raise SystemExit(f"{key}={release[key]} is not under {data_dir}")
    config = dict(release_env=str(release_env), planetscale_env=str(args.planetscale_env.resolve()),
                  data_dir=str(data_dir), port=args.port, tools_mem=args.tools_mem,
                  compose_env=str(args.compose_env.resolve()) if args.compose_env else None)
    candidate.config_path.write_text(json.dumps(config, indent=2))
    path = candidate.compose_file(f"scanapp-local-{args.name}", release_env, args.port)
    if args.build or not image_exists():
        candidate.compose(path, "build", "api")
    key = fingerprint(config, release_env)["all"]
    candidate.compose(path, "up", "-d", "--force-recreate", "api")
    started = time.monotonic()
    health = wait_ready(candidate, path, args.port, args.timeout)
    passed = (health.get("catalogue_import_id") == release["PLANETSCALE_IMPORT_ID"]
              and health.get("catalogue_backend") == "planetscale")
    candidate.record("runtime_load", key, passed, {
        "import_id": health.get("catalogue_import_id"), "catalogue_version": health.get("catalogue_version"),
        "model_revision": health.get("model_revision"), "load_seconds": round(time.monotonic() - started),
        "url": f"http://127.0.0.1:{args.port}"})


def image_exists() -> bool:
    return subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True).returncode == 0


def cmd_panel(args) -> None:
    candidate = Candidate(args.name)
    config = candidate.config
    release_env = Path(config["release_env"])
    inputs = [args.panel.read_bytes()]
    photo_mounts = [f"{args.panel.resolve()}:/inputs/panel.json:ro",
                    f"{args.photos_root.resolve()}:/inputs/photos:ro",
                    f"{candidate.dir.resolve()}:/out"]
    extra = []
    if args.extra_photos:
        photo_mounts.append(f"{args.extra_photos.resolve()}:/inputs/extra:ro")
        extra = ["--extra-photos", "/inputs/extra"]
        inputs.append((args.extra_photos / "cases.json").read_bytes())
    key = sha256((fingerprint(config, release_env)["all"] + "".join(sha256(i) for i in inputs)).encode())
    gate = f"panel:{args.label}"
    if candidate.already(gate, key, args.force):
        return
    project = f"scanapp-local-{args.name}"
    path = candidate.compose_file(project, release_env, config["port"], photo_mounts)
    output = candidate.dir / f"panel-{args.label}.jsonl"
    resume = output.exists() and not args.force
    if args.force and output.exists():
        output.unlink()
    cid = container_id(candidate, path)
    if not cid:
        raise SystemExit("API is not running; run `up` first")
    with PeakMemory(cid) as memory:
        result = candidate.compose(path, "run", "--rm", "--no-deps", "tools", "python", "/app/scripts/run_scan_stream_panel.py",
                                   "--panel", "/inputs/panel.json", "--photos-root", "/inputs/photos", *extra,
                                   "--output", f"/out/{output.name}", "--base-url", "http://api:8000",
                                   "--pause", "0", *(["--resume"] if resume else []), check=False)
    state = container_state(candidate, path) or {}
    limit = limit_bytes(candidate.resolved_api(release_env, config).get("mem_limit", "2g"))
    summary_path = output.with_suffix(".summary.json")
    summary = json.loads(summary_path.read_text()) if summary_path.is_file() else {}
    passed = result.returncode == 0 and not state.get("OOMKilled") and bool(summary)
    candidate.record(gate, key, passed, {
        "scans": summary.get("scans"), "peak_api_memory_mib": memory.peak // 1024**2,
        "staging_limit_mib": limit // 1024**2, "oom": bool(state.get("OOMKilled")),
        "output": str(output.relative_to(ROOT)),
        "note": "Timings run under amd64 emulation and are not staging latency."})


def cmd_probe(args) -> None:
    candidate = Candidate(args.name)
    config = candidate.config
    release_env = Path(config["release_env"])
    release = read_env(release_env)
    features = release.get("REFERENCE_FEATURES_DIR")
    if not features:
        raise SystemExit("The release file has no REFERENCE_FEATURES_DIR")
    cases = (args.audit_dir / "cases.json").read_bytes()
    key = sha256((fingerprint(config, release_env)["all"] + sha256(cases) + str(args.limit)).encode())
    gate = "probe_smoke" if args.limit else "probe_full"
    if candidate.already(gate, key, args.force):
        return
    out_name = "paired-smoke.jsonl" if args.limit else "paired-full.jsonl"
    if (args.audit_dir / out_name).exists():
        raise SystemExit(f"{args.audit_dir / out_name} exists; move it aside to run the probe again")
    path = candidate.compose_file(f"scanapp-local-{args.name}", release_env, config["port"],
                                  [f"{args.audit_dir.resolve()}:/audit"])
    command = ["run", "--rm", "--no-deps", "tools", "python", "/app/scripts/staging_reference_feature_probe.py",
               "--audit-dir", "/audit", "--features-dir", features]
    if args.limit:
        command += ["--limit", str(args.limit)]
    result = candidate.compose(path, *command, check=False)
    summary_path = args.audit_dir / ("smoke-summary.json" if args.limit else "full-summary.json")
    summary = json.loads(summary_path.read_text()) if summary_path.is_file() else {}
    passed = result.returncode == 0 and not summary.get("deltas") and not summary.get("blocked_reference_read_attempts")
    candidate.record(gate, key, passed, {"photos": summary.get("photos"), "equal_responses": summary.get("equal_responses"),
                                         "grading_equal": summary.get("grading_equal"), "scores": summary.get("scores")})


def cmd_rollback(args) -> None:
    """Load the parent release next to the candidate, as a restore would."""
    candidate = Candidate(args.name)
    config = candidate.config
    parent_env = args.parent_env.resolve()
    parent = read_env(parent_env)
    key = sha256((fingerprint(config, Path(config["release_env"]))["all"] + sha256(parent_env.read_bytes())).encode())
    if candidate.already("rollback_load", key, args.force):
        return
    port = config["port"] + 1
    path = candidate.compose_file(f"scanapp-local-{args.name}-parent", parent_env, port)
    candidate.compose(path, "up", "-d", "--force-recreate", "api")
    try:
        health = wait_ready(candidate, path, port, args.timeout)
    finally:
        if not args.keep:
            candidate.compose(path, "down", "-v", check=False)
    passed = health.get("catalogue_import_id") == parent["PLANETSCALE_IMPORT_ID"]
    candidate.record("rollback_load", key, passed, {"parent_import_id": health.get("catalogue_import_id"),
                                                    "catalogue_version": health.get("catalogue_version")})


def cmd_status(args) -> None:
    candidate = Candidate(args.name)
    config = candidate.config
    current = fingerprint(config, Path(config["release_env"]))
    print(json.dumps({"config": {k: v for k, v in config.items() if k != "planetscale_env"},
                      "fingerprint": current, "gates": candidate.gates()}, indent=2))


def cmd_down(args) -> None:
    candidate = Candidate(args.name)
    for path in sorted(candidate.dir.glob("*.compose.json")):
        candidate.compose(path, "down", "-v", check=False)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    up = sub.add_parser("up", help="build if needed, start the candidate API and wait until it has loaded")
    up.add_argument("name")
    up.add_argument("--release-env", type=Path, required=True, help="candidate catalogue-release.env")
    up.add_argument("--planetscale-env", type=Path, required=True, help="read-only PlanetScale credentials")
    up.add_argument("--data-dir", type=Path, required=True, help="local copy of staging /data")
    up.add_argument("--compose-env", type=Path, help="non-secret flag values from staging's Dokploy .env")
    up.add_argument("--port", type=int, default=8100)
    up.add_argument("--tools-mem", default="4g")
    up.add_argument("--timeout", type=float, default=1200)
    up.add_argument("--build", action="store_true")
    up.set_defaults(func=cmd_up)

    panel = sub.add_parser("panel", help="scan the review panel against the local API (resumable)")
    panel.add_argument("name")
    panel.add_argument("--panel", type=Path, required=True)
    panel.add_argument("--photos-root", type=Path, required=True)
    panel.add_argument("--extra-photos", type=Path)
    panel.add_argument("--label", default="review")
    panel.add_argument("--force", action="store_true")
    panel.set_defaults(func=cmd_panel)

    probe = sub.add_parser("probe", help="paired image/feature regression in a separate container")
    probe.add_argument("name")
    probe.add_argument("--audit-dir", type=Path, required=True)
    probe.add_argument("--limit", type=int)
    probe.add_argument("--force", action="store_true")
    probe.set_defaults(func=cmd_probe)

    rollback = sub.add_parser("rollback", help="load the parent release locally and confirm its import")
    rollback.add_argument("name")
    rollback.add_argument("--parent-env", type=Path, required=True)
    rollback.add_argument("--timeout", type=float, default=1200)
    rollback.add_argument("--keep", action="store_true")
    rollback.add_argument("--force", action="store_true")
    rollback.set_defaults(func=cmd_rollback)

    for name, func in (("status", cmd_status), ("down", cmd_down)):
        command = sub.add_parser(name)
        command.add_argument("name")
        command.set_defaults(func=func)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main(sys.argv[1:])
