"""Review-only ordering of ordinary versus Play! Pokemon stamped printings.

Not observing a logo is NOT proof that the card is unstamped. Without a
positive observation, an otherwise near-tied ordinary printing is a display
prior; every stamped alternative and the ambiguity state remain intact.
"""
from functools import lru_cache
from pathlib import Path
import hashlib
import json
import re

import cv2
import numpy as np

from app.recognition.rank import artwork_evidence_compatible, normalize_text

ASSETS = Path(__file__).with_name('assets')
VERSION = 'play-stamp-review-v1'


def prize_pack(row):
    return bool(re.search(r'play.?\s*pok[eé]mon\s+prize\s+pack',
                         str(row.get('set_name') or ''), re.I))


@lru_cache(maxsize=1)
def _template():
    metadata = json.loads((ASSETS / 'play_stamp.json').read_text())
    path = ASSETS / 'play_stamp.npz'
    if metadata['version'] != VERSION or hashlib.sha256(path.read_bytes()).hexdigest() != metadata['sha256']:
        raise ValueError('Stamp template checksum mismatch')
    with np.load(path, allow_pickle=False) as data:
        return data['points'], data['descriptors'], data['size']


def observe_play_stamp(image):
    """Bounded positive logo geometry; no absence claim or extra OCR pass."""
    points, descriptors, size = _template()
    # Search the selected frame, including the artwork's lower-right edge.
    # Scale is bounded and local features tolerate moderate camera perspective.
    frame = image.convert('RGB')
    frame.thumbnail((720, 1000))
    # Limit extraction to the conventional lower-right illustration region.
    # This prevents high-detail artwork consuming the keypoint budget before
    # the small logo is considered. Other layouts retain an unknown stamp.
    if not .62 <= frame.width/frame.height <= .80:
        return dict(observed=False, inliers=0)
    frame = frame.crop((round(.55*frame.width), round(.30*frame.height),
                        frame.width, round(.60*frame.height)))
    pixels = cv2.cvtColor(np.asarray(frame), cv2.COLOR_RGB2GRAY)
    keys, query = cv2.SIFT_create(nfeatures=700, contrastThreshold=.03).detectAndCompute(pixels, None)
    if query is None or len(query) < 2:
        return dict(observed=False, inliers=0)
    pairs = cv2.BFMatcher().knnMatch(descriptors, query, k=2)
    good = [a for a, b in pairs if a.distance < .70*b.distance]
    if len(good) < 8:
        return dict(observed=False, inliers=0)
    source = np.float32([points[m.queryIdx] for m in good])
    target = np.float32([keys[m.trainIdx].pt for m in good])
    transform, mask = cv2.findHomography(source, target, cv2.RANSAC, 3.)
    count = int(mask.sum()) if mask is not None else 0
    if transform is None or count < 8 or count/len(good) < .65:
        return dict(observed=False, inliers=count)
    w, h = size
    corners = cv2.perspectiveTransform(np.float32([[[0,0],[w,0],[w,h],[0,h]]]), transform)[0]
    area = abs(cv2.contourArea(corners))
    inside = bool(np.all(corners >= 0) and np.all(corners[:,0] <= frame.width)
                  and np.all(corners[:,1] <= frame.height))
    spread = cv2.convexHull(source[mask.ravel().astype(bool)])
    supported = (inside and cv2.isContourConvex(corners) and 150 <= area <= .60*pixels.size
                 and cv2.contourArea(spread)/(w*h) >= .12)
    return dict(observed=bool(supported), inliers=count)


def stamp_printing_hint(ranked, members, image, *, ocr_name, name_confidence,
                        numbers, languages, observer=observe_play_stamp):
    if not ranked:
        return None
    top = ranked[0]
    member_ids = {r.get('card_id', r.get('id')) for r in members}
    eligible = [r for r in ranked if r['card_id'] in member_ids
        and normalize_text(r['name']) == normalize_text(top['name'])
        and r.get('language') == top.get('language')
        and r.get('collector_number') == top.get('collector_number')
        and abs(float(r['visual_score'])-float(top['visual_score'])) <= .04
        and artwork_evidence_compatible(r, ocr_name=ocr_name,
            name_confidence=name_confidence, numbers=numbers, languages=languages)]
    ordinary = [r for r in eligible if not prize_pack(r)]
    stamped = [r for r in eligible if prize_pack(r)]
    if not ordinary or not stamped:
        return None
    observation = observer(image)
    choices = stamped if observation['observed'] else ordinary
    preferred = max(choices, key=lambda r: float(r['combined_score']))
    return dict(preferred_card_id=preferred['card_id'], **observation, version=VERSION,
        policy='display order only; not observing a stamp does not prove its absence; printing remains ambiguous')
