"""Pristine OCR observations, memoized only within one upload request."""
from copy import deepcopy
import hashlib


class RequestOcrCache:
    def __init__(self):
        self._observations = {}
        self.hits = 0
        self.reads = 0

    def read(self, engine, image, *, collector_retry_policy=None):
        # Geometry/rotation and every pixel must agree. Never reuse a title or
        # footer from a different crop, a previous upload, or the grading OCR.
        pixels = (image.mode, image.size, hashlib.sha256(image.tobytes()).digest())
        # A pruned read cannot satisfy a later request for complete evidence.
        # Complete observations can satisfy either policy without rereading.
        key = (*pixels, 'adaptive' if collector_retry_policy is not None else 'full')
        complete_key = (*pixels, 'full')
        if complete_key in self._observations:
            key = complete_key
        if key in self._observations:
            self.hits += 1
            return deepcopy(self._observations[key]), True
        observed = (engine.read(image, collector_retry_policy=collector_retry_policy)
                    if collector_retry_policy is not None else engine.read(image))
        self.reads += 1
        # Ranking supplements observations. Neither the saved result nor its
        # mutable lines/hits/passes may contaminate the pristine cache entry.
        self._observations[key] = deepcopy(observed)
        return observed, False
