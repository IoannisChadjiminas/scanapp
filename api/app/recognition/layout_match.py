"""Full-card layout corroboration after exact title/fraction OCR.

Text landmarks across both ends can survive holo glare that defeats artwork
features. This evidence permits a review result only. It never substitutes for
artwork proof, certifies a finish, or changes a similarity score.
"""
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from threading import RLock

import cv2
import numpy as np
from PIL import Image

from app.recognition.artifacts import sha256_file
from app.recognition.local_match import _pixels, verify_geometry
from app.recognition.reference_features import extract_reference

FULL_CARD = (0., 0., 1., 1.)


@dataclass(frozen=True)
class LayoutMatch:
    card_id: str
    inliers: int
    header_inliers: int
    footer_inliers: int
    query_coverage: float


class CardLayoutVerifier:
    def __init__(self, data_dir: Path, max_references: int = 64):
        self.root = (data_dir / 'reference-images').resolve()
        self.feature_store = None
        self.max_references = max_references
        self._cache = OrderedDict()
        self._lock = RLock()

    def _reference(self, card_id, raw_path):
        path = Path(raw_path).resolve()
        if not path.is_relative_to(self.root) or not path.is_file():
            return None
        # Existing artwork bundles remain immutable. Extract this distinct
        # layout profile from the actual reference, bound to its source hash.
        expected_hash = None
        if self.feature_store is not None:
            record = self.feature_store.manifest['records'].get(card_id)
            if not record or not record['available'] or record['image_path'] != raw_path:
                return None
            expected_hash = record['source_sha256']
        signature = (card_id, raw_path, path.stat().st_mtime_ns, path.stat().st_size, expected_hash)
        # Concurrent scan lanes share this cache. Extract outside the lock;
        # a duplicate extraction yields the same reference.
        with self._lock:
            if signature in self._cache:
                self._cache.move_to_end(signature)
                return self._cache[signature]
        if expected_hash is not None and sha256_file(path) != expected_hash:
            return None
        with Image.open(path) as image:
            reference = extract_reference(image, FULL_CARD, 1000, .04)
        with self._lock:
            self._cache[signature] = reference
            self._cache.move_to_end(signature)
            while len(self._cache) > self.max_references:
                self._cache.popitem(last=False)
        return reference

    def verify(self, image: Image.Image, references: list[tuple[str, str]]) -> list[LayoutMatch]:
        # A partial/oversized hypothesis set is not reduced to a false winner.
        if not references or len(references) > 4 or not .62 <= image.width/image.height <= .80:
            return []
        query = _pixels(image)
        keys, descriptors = cv2.SIFT_create(nfeatures=1000).detectAndCompute(query, None)
        if descriptors is None or len(keys) < 30:
            return []
        matches = []
        for card_id, raw_path in references:
            try:
                reference = self._reference(card_id, raw_path)
                if reference is None or reference.descriptors is None or len(reference.points) < 30:
                    continue
                pairs = cv2.BFMatcher().knnMatch(descriptors, reference.descriptors, k=2)
                good = [a for pair in pairs if len(pair) == 2
                        for a, b in [pair] if a.distance < .75*b.distance]
                unique = {m.trainIdx: m for m in sorted(good, key=lambda m: -m.distance)}
                good = list(unique.values())
                qpts = np.float32([keys[m.queryIdx].pt for m in good]).reshape(-1, 2)
                rpts = np.float32([reference.points[m.trainIdx] for m in good]).reshape(-1, 2)
                proof = verify_geometry(qpts, rpts, (query.shape[1], query.shape[0]),
                                        reference.size, FULL_CARD)
                if proof is None or proof[0] < 30 or proof[2] < .30:
                    continue
                _, mask = cv2.findHomography(rpts, qpts, cv2.RANSAC, 3.)
                if mask is None:
                    continue
                retained = rpts[mask.ravel().astype(bool)]
                header = int((retained[:, 1] < .22*reference.size[1]).sum())
                footer = int((retained[:, 1] > .78*reference.size[1]).sum())
                if header >= 8 and footer >= 8:
                    matches.append(LayoutMatch(card_id, proof[0], header, footer, round(proof[2], 3)))
            except (OSError, ValueError, cv2.error):
                continue
        return matches
