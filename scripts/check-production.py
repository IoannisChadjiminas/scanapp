#!/usr/bin/env python3
"""Read-only local deployment checks. Never print secret values or connect to a DB."""

import argparse
import io
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values
from dotenv.parser import parse_stream


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env-prod"))
    parser.add_argument("--api-env-file", type=Path)
    parser.add_argument("--host-files", action="store_true", help="Also check the production host's catalogue env files")
    args = parser.parse_args()
    failures = []

    def load(path):
        if not path.is_file():
            failures.append("Environment file missing")
            return {}
        if path.stat().st_mode & 0o077:
            failures.append("Environment file permissions must be 0600")
        text = path.read_text()
        if any(binding.error for binding in parse_stream(io.StringIO(text))):
            failures.append("Environment file contains malformed assignments")
            return {}
        return dict(dotenv_values(stream=io.StringIO(text), interpolate=False))

    values = load(args.env_file)
    token = values.get("SCANAPP_SERVICE_TOKEN") or ""
    if len(token) < 32:
        failures.append("SCANAPP_SERVICE_TOKEN must contain at least 32 characters")
    url = values.get("PORTFOLIO_DATABASE_URL") or ""
    try:
        parts = urlsplit(url)
        if not (parts.scheme in {"postgres", "postgresql"}
                and (parts.hostname or "").endswith(".psdb.cloud")
                and parts.path == "/pokesingle-product-prod"):
            failures.append("PORTFOLIO_DATABASE_URL needs the dedicated production ScanApp credential")
    except ValueError:
        failures.append("PORTFOLIO_DATABASE_URL is malformed")
    forbidden = ("BETTER_AUTH_SECRET", "FIREBASE_PRIVATE_KEY", "APPLE_PRIVATE_KEY",
                 "GOOGLE_CLIENT_SECRET", "RESEND_API_KEY", "DATABASE_URL")
    if any(values.get(name) for name in forbidden):
        failures.append("Scanner environment contains product API credentials; keep service environments separate")
    if values.get("SCRAPER_ENABLED", "false").lower() == "true":
        profiles = (values.get("COMPOSE_PROFILES") or "").split(",")
        if "scraping" not in profiles and not (values.get("SCRAPER_URLS") or values.get("SCRAPER_URL")):
            failures.append("Enabled scraping needs its Compose profile or an external scraper URL")
    if args.api_env_file:
        api = load(args.api_env_file)
        if not token or api.get("SCANAPP_SERVICE_TOKEN") != token:
            failures.append("API and ScanApp service tokens differ")
        try:
            base = urlsplit(api.get("SCAN_API_BASE_URL") or "")
            if base.scheme != "https" or not base.hostname or base.path != "/api/v1/" or base.username or base.password or base.query or base.fragment:
                failures.append("API SCAN_API_BASE_URL must be the verified HTTPS scanner origin ending /api/v1/")
        except ValueError:
            failures.append("API SCAN_API_BASE_URL is malformed")
    if args.host_files:
        catalogue = load(Path(values.get("PLANETSCALE_ENV_FILE") or "/etc/scanapp-production/planetscale.env"))
        release = load(Path(values.get("CATALOGUE_RELEASE_ENV_FILE") or "/etc/scanapp-production/catalogue-release.env"))
        if not catalogue.get("PLANETSCALE_DATABASE_URL"):
            failures.append("Production read-only catalogue credential is missing")
        if not release.get("PLANETSCALE_SCHEMA") or not release.get("PLANETSCALE_IMPORT_ID"):
            failures.append("Production catalogue release selectors are missing")
    for failure in failures:
        print("PENDING:", failure)
    if not failures:
        print("Local configuration checks passed. Verify live roles, model artifacts, HTTPS, capacity and account cleanup separately.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
