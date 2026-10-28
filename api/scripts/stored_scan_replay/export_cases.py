"""Read-only export of stored scans for the ranking replay. Runs inside the API
container, fed over stdin (it is not in the image):

    ssh <staging-host> "docker exec -i <api-container> python3 -" \
        < api/scripts/stored_scan_replay/export_cases.py > <work>/cases.jsonl

Writes one JSON line per stored scan with a visual top 20 to stdout. The first
line is {"_settings": {...}}: the container's own ranking switches and
thresholds (booleans and numbers only), so the replay ranks as staging does.
The output holds OCR text: keep it outside Git and delete it when done.
"""
import glob
import json

KEEP = ('card_id', 'name', 'collector_number', 'language', 'visual_score', 'set_name')
SETTING_PREFIXES = ('ocr_', 'rank_', 'printing_', 'threshold_')


def settings_line():
    try:
        from app.config import get_settings
    except Exception:
        return {}
    values = get_settings().model_dump()
    return {k: v for k, v in values.items()
            if k.startswith(SETTING_PREFIXES) and isinstance(v, (bool, int, float))}


print(json.dumps({'_settings': settings_line()}))
for path in glob.glob('/data/review/cases/*.json'):
    try:
        d = json.load(open(path))
    except Exception:
        continue
    if not d.get('visual_top20'):
        continue
    o = d.get('ocr') or {}
    plausible = (o.get('printing_review') or {}).get('plausible_printings') or []
    print(json.dumps({
        'id': d.get('scan_id'), 'created': (d.get('created_at') or '')[:10], 'status': d.get('status'),
        'pred': [{k: p.get(k) for k in KEEP} for p in (d.get('predicted') or [])[:2] if isinstance(p, dict)],
        'vis': [{k: v.get(k) for k in KEEP} for v in d['visual_top20']],
        'hits': o.get('hits') or [], 'lines': o.get('lines') or [],
        'collector': o.get('collector_text'), 'name': o.get('name_text'),
        'failed': o.get('failed'), 'lang': o.get('detected_language'),
        'review': [p.get('card_id') for p in plausible],
        'confirmed': d.get('confirmed_card_id'), 'feedback': d.get('feedback_action'),
    }))
