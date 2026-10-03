"""Bounded crop fallback: local geometry verifies artwork, never a printing."""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from threading import RLock

import cv2
import numpy as np
from PIL import Image

from app.recognition.printing import ART_BOX
from app.recognition.artwork import PROFILES, crop_profile
from app.recognition.reference_features import extract_reference

FULL_ART_BOX = (.08, .18, .92, .56)
FULL_ART_RARITIES = {'ultra rare','secret rare','illustration rare','special illustration rare',
                    'full art trainer','holo rare vmax','hyper rare','character rare',
                    'character super rare','shiny ultra rare','shiny rare vmax'}


@dataclass(frozen=True)
class LocalArtworkMatch:
    card_id: str
    inliers: int
    artwork_inliers: int
    query_coverage: float
    query_profile: str = "as_supplied"
    reference_profile: str = 'conventional_window'


def _pixels(image: Image.Image) -> np.ndarray:
    image = image.convert("RGB")
    image.thumbnail((720, 720), Image.Resampling.LANCZOS)
    return cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2GRAY)


def verify_geometry(query_points: np.ndarray, reference_points: np.ndarray,
                    query_size: tuple[int, int], reference_size: tuple[int, int],
                    art_box: tuple[float,float,float,float] = ART_BOX) -> tuple[int, int, float] | None:
    if len(query_points) < 16:
        return None
    matrix, mask = cv2.findHomography(reference_points, query_points, cv2.RANSAC, 3.0)
    if matrix is None or mask is None or not np.isfinite(matrix).all():
        return None
    keep = mask.ravel().astype(bool)
    count = int(keep.sum())
    if count < 14 or count / len(keep) < .55:
        return None
    w, h = reference_size
    x0, y0, x1, y1 = art_box
    ref = reference_points[keep]
    art = (ref[:, 0] >= x0*w) & (ref[:, 0] <= x1*w) & (ref[:, 1] >= y0*h) & (ref[:, 1] <= y1*h)
    if int(art.sum()) < 10:
        return None
    # A repeated attack/title line is not spatial artwork evidence, even with
    # many descriptors. Require support across both dimensions of the region.
    spread = np.ptp(ref[art],axis=0)
    if spread[0] < .30*(x1-x0)*w or spread[1] < .30*(y1-y0)*h:
        return None
    art_area = float(cv2.contourArea(cv2.convexHull(ref[art].astype(np.float32))))
    if art_area / ((x1-x0)*w*(y1-y0)*h) < .08:
        return None
    qw, qh = query_size
    query_area = float(cv2.contourArea(cv2.convexHull(query_points[keep].astype(np.float32))))
    coverage = query_area / (qw*qh)
    if coverage < .1:
        return None
    corners = np.float32([[0,0],[w,0],[w,h],[0,h]]).reshape(-1,1,2)
    projected = cv2.perspectiveTransform(corners, matrix).reshape(-1,2)
    if not np.isfinite(projected).all() or not cv2.isContourConvex(projected):
        return None
    area = cv2.contourArea(projected, oriented=True)
    if area <= 0 or not .25 <= area / (qw*qh) <= 30:
        return None
    return count, int(art.sum()), coverage


class LocalArtworkVerifier:
    def __init__(self, data_dir: Path, max_references: int = 64, feature_store=None) -> None:
        self.root = (data_dir / "reference-images").resolve()
        self.max_references = max_references
        self._cache = OrderedDict()
        self._lock = RLock()
        self.reference_boxes: dict[str, tuple[float,float,float,float]] = {}
        self.feature_store = feature_store

    def _reference_features(self, card_id, raw_path, art_box, features, contrast):
        key = (card_id, raw_path, art_box, features, contrast)
        if key not in self._cache:
            if self.feature_store is not None:
                reference = self.feature_store.features(card_id, raw_path, art_box, features, contrast)
            else:
                path = Path(raw_path).resolve()
                if not path.is_relative_to(self.root) or not path.is_file():
                    return None
                try:
                    with Image.open(path) as image:
                        reference = extract_reference(image, art_box, features, contrast)
                except (OSError, ValueError, cv2.error):
                    return None
            self._cache[key] = reference
            while len(self._cache) > self.max_references:
                self._cache.popitem(last=False)
        self._cache.move_to_end(key)
        return self._cache[key]

    def propose_frame(self, image: Image.Image, reference: tuple[str,str],
                      diagnostics: list | None = None) -> Image.Image | None:
        """Project a verified artwork reference back to the original photo.

        This recovers footer/title pixels lost by holder-edge proposals. It is
        a framing hypothesis, not proof that the reference's printing is right.
        All projected corners must be inside the upload; never invent pixels.
        """
        from app.recognition.detect import _order_points
        from app.recognition.frame_fallback import portrait_window_candidates, slab_interior_candidate
        with self._lock:
            card_id,raw_path=reference
            art_box=self.reference_boxes.get(card_id,ART_BOX)
            stored = self._reference_features(card_id, raw_path, art_box, 1000, .04)
            if stored is None:
                return None
            rw,rh=stored.size
            detector=cv2.SIFT_create(nfeatures=1000)
            rpoints,rdesc=stored.points,stored.descriptors
            if rdesc is None or len(rdesc)<2:
                return None
            windows=portrait_window_candidates(image)
            hypotheses=[(image,(0,0))]
            hypotheses.extend((patch,((image.width-patch.width)//2,(image.height-patch.height)//2))
                              for _,patch in windows)
            slab=slab_interior_candidate(image)
            if slab:
                patch=slab[1]
                hypotheses.append((patch,((image.width-patch.width)//2,round(.24*image.height))))
            # Local verification already uses artwork-region hypotheses to
            # avoid spending descriptors on holder labels/rules. Keep their
            # offsets so the recovered outline remains in upload coordinates.
            for patch,offset in list(hypotheses):
                for profile,box in PROFILES.items():
                    region=crop_profile(patch,profile)
                    origin=(offset[0]+round(box[0]*patch.width),offset[1]+round(box[1]*patch.height))
                    hypotheses.append((region,origin))
            best=None
            for patch,offset in hypotheses:
                query=_pixels(patch.copy())
                qh,qw=query.shape
                qkeys,qdesc=detector.detectAndCompute(query,None)
                if qdesc is None or len(qkeys)<16:
                    continue
                pairs=cv2.BFMatcher().knnMatch(qdesc,rdesc,k=2)
                good=[a for pair in pairs if len(pair)==2 for a,b in [pair] if a.distance<.75*b.distance]
                good=list({m.trainIdx:m for m in sorted(good,key=lambda m:-m.distance)}.values())
                qpts=np.float32([qkeys[m.queryIdx].pt for m in good]).reshape(-1,2)
                rpts=np.float32([rpoints[m.trainIdx] for m in good]).reshape(-1,2)
                proof=verify_geometry(qpts,rpts,(qw,qh),(rw,rh),art_box)
                if not proof:
                    continue
                matrix,_=cv2.findHomography(rpts,qpts,cv2.RANSAC,3.)
                corners=np.float32([[0,0],[rw,0],[rw,rh],[0,rh]]).reshape(-1,1,2)
                projected=cv2.perspectiveTransform(corners,matrix).reshape(-1,2)
                projected=projected*np.array([patch.width/qw,patch.height/qh])+offset
                rect=_order_points(projected.astype(np.float32))
                tl,tr,br,bl=rect
                widths=np.array([np.linalg.norm(tr-tl),np.linalg.norm(br-bl)])
                heights=np.array([np.linalg.norm(bl-tl),np.linalg.norm(br-tr)])
                area=float(cv2.contourArea(rect,oriented=True))
                # Artwork homography permits foreshortening that the blind
                # contour detector cannot trust. Still reject tiny, folded,
                # extreme or out-of-image projections.
                plausible=bool(cv2.isContourConvex(rect) and
                    .10 <= area/(image.width*image.height) <= .995 and
                    .40 <= widths.mean()/max(heights.mean(),1.) <= 1.25 and
                    widths.min()/max(widths.max(),1.) >= .55 and
                    heights.min()/max(heights.max(),1.) >= .55 and
                    area/max(widths.mean()*heights.mean(),1.) >= .70)
                if diagnostics is not None:
                    diagnostics.append({'inliers':proof[1],'projected_corners':projected.tolist(),
                        'plausible':plausible})
                if (not np.isfinite(projected).all() or projected.min()<0
                        or projected[:,0].max()>=image.width or projected[:,1].max()>=image.height
                        or not plausible):
                    continue
                if best is None or proof[1]>best[0]:
                    best=(proof[1],rect)
            if best is None:
                return None
            tl,tr,br,bl=best[1]
            # Preserve the better-sampled axis under foreshortening rather
            # than shrinking a sufficiently wide card below the quality floor.
            observed_width=max(np.linalg.norm(tr-tl),np.linalg.norm(br-bl))
            observed_height=max(np.linalg.norm(bl-tl),np.linalg.norm(br-tr))
            width=round(max(observed_width,observed_height*rw/rh))
            height=round(width*rh/rw)
            if min(width,height)<80:
                return None
            target=np.float32([[0,0],[width-1,0],[width-1,height-1],[0,height-1]])
            matrix=cv2.getPerspectiveTransform(best[1],target)
            return Image.fromarray(cv2.warpPerspective(np.asarray(image.convert('RGB')),matrix,(width,height)))

    def verify(self, image: Image.Image, references: list[tuple[str, str]],
               limit: int = 8) -> list[LocalArtworkMatch]:
        # Preserve established geometry before increasing the texture budget.
        # A denser matcher is recovery only, not a competing printing vote.
        with self._lock:
            first=self._verify(image,references,limit,1000,.04,False)
            return first or self._verify(image,references,limit,2000,.02,True)

    def _verify(self, image, references, limit, features, contrast, lower_regions):
        with self._lock:
            detector = cv2.SIFT_create(nfeatures=features,contrastThreshold=contrast)
            # A full photograph can spend its keypoint budget on sleeves,
            # stands and rules text. Probe at most two unwarped region crops
            # too. These are verification hypotheses, never framing/printing
            # proof; coverage is explicitly relative to the chosen patch.
            hypotheses = [("as_supplied", image)]
            if .60 <= image.width / image.height <= 1.0:
                hypotheses.extend((p, crop_profile(image,p)) for p in PROFILES)
            if lower_regions and .50 <= image.width/image.height <= 1.10:
                # Holder text can consume most keypoints on a partial photo.
                # These unwarped original-pixel patches exclude the upper
                # label without inventing card corners. Identical geometric
                # artwork checks still apply; they never prove a printing.
                for start in (.30,.45):
                    patch=image.crop((round(.04*image.width),round(start*image.height),
                                      round(.96*image.width),image.height))
                    if min(patch.size)>=100:
                        hypotheses.append((f'lower_photo_{start:.2f}',patch))
            queries = []
            for profile, pixels in hypotheses:
                query = _pixels(pixels.copy())
                qkeys, qdesc = detector.detectAndCompute(query, None)
                if qdesc is not None and len(qkeys) >= 16:
                    queries.append((profile, query, qkeys, qdesc))
            if not queries:
                return []
            matches = []
            for card_id, raw_path in references[:limit]:
                art_box = self.reference_boxes.get(card_id, ART_BOX)
                reference_profile = 'broad_full_art' if art_box == FULL_ART_BOX else 'conventional_window'
                stored = self._reference_features(card_id, raw_path, art_box, features, contrast)
                if stored is None:
                    continue
                points, desc, size = stored.points, stored.descriptors, stored.size
                if desc is None or len(desc) < 2:
                    continue
                best = None
                for profile, query, qkeys, qdesc in queries:
                    pairs = cv2.BFMatcher().knnMatch(qdesc, desc, k=2)
                    good = [a for pair in pairs if len(pair) == 2
                            for a,b in [pair] if a.distance < .75*b.distance]
                    # Repeated query features must not manufacture consensus by
                    # pointing to the same reference landmark.
                    unique = {m.trainIdx: m for m in sorted(good, key=lambda m: -m.distance)}
                    good = list(unique.values())
                    qpts = np.float32([qkeys[m.queryIdx].pt for m in good]).reshape(-1,2)
                    rpts = np.float32([points[m.trainIdx] for m in good]).reshape(-1,2)
                    proof = verify_geometry(qpts, rpts, (query.shape[1], query.shape[0]), size, art_box)
                    if proof and (best is None or proof[1] > best.artwork_inliers):
                        best = LocalArtworkMatch(card_id, proof[0], proof[1], round(proof[2], 3), profile, reference_profile)
                if best is not None:
                    matches.append(best)
            return sorted(matches, key=lambda m: (m.artwork_inliers, m.inliers), reverse=True)
