"""Print the API's recognition settings as KEY=value lines, without any secret.

Reads the API's own Settings object (not the process environment) and prints only
booleans and numbers, a short allowlist of non-secret strings, and the folder names
of the selected artifact bundles. String settings outside the allowlist (URLs, tokens,
keys) and SecretStr fields are never printed. Scraper, price and phone-config lanes
are left out because they do not change recognition answers.

  python - < recognition_settings.py              # print (e.g. via docker exec -i)
  python - --check staging.env < recognition_settings.py   # exit 1 on any difference
"""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]) if '__file__' in globals() else '/app')
sys.path.insert(0, '/app')
from app.config import Settings  # noqa: E402

STRINGS = {'catalogue_backend', 'planetscale_import_id', 'preprocess_config', 'ranking_version',
           'ocr_version', 'model_name'}
BUNDLES = {'artwork_bundle_dir', 'reference_features_dir'}
SKIP_PREFIXES = ('scraper_', 'daily_', 'scan_price_', 'cardmarket_', 'tcgdex_', 'price_guide_', 'app_',
                 'session_', 'photo_scrape', 'config_ttl', 'scan_wait_limit', 'store_captures')


def recognition_settings(settings):
    values = {}
    for name in sorted(type(settings).model_fields):
        value = getattr(settings, name)
        if name in BUNDLES:
            values[name] = Path(value).name if value else ''
        elif name.startswith(SKIP_PREFIXES):
            continue
        elif isinstance(value, (bool, int, float)) or name in STRINGS:
            values[name] = value
    return {k.upper(): str(v).lower() if isinstance(v, bool) else str(v) for k, v in values.items()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', type=Path, help='file printed by this script on the reference host')
    parser.add_argument('--ignore', action='append', default=[],
                        help='key allowed to differ (repeatable), e.g. CATALOGUE_BACKEND')
    args = parser.parse_args()
    ours = recognition_settings(Settings())
    if not args.check:
        print('\n'.join(f'{k}={v}' for k, v in ours.items()))
        return
    theirs = dict(line.split('=', 1) for line in args.check.read_text().splitlines() if '=' in line)
    ignored = {k.upper() for k in args.ignore}
    differ = sorted(k for k in set(ours) | set(theirs) if k not in ignored and ours.get(k) != theirs.get(k))
    for key in differ:
        print(f'{key}: reference={theirs.get(key)!r} here={ours.get(key)!r}')
    print(f'{len(differ)} differing recognition settings')
    raise SystemExit(1 if differ else 0)


if __name__ == '__main__':
    main()
