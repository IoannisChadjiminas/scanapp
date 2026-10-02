from __future__ import annotations

import cv2
import math
import numpy as np
from PIL import Image


def _order_points(pts: np.ndarray) -> np.ndarray:
    rect = np.zeros((4, 2), dtype=np.float32)
    s = pts.sum(axis=1)
    diff = np.diff(pts, axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect


def _frame_score(points: np.ndarray, image_size: tuple[int, int]) -> float | None:
    """Geometry-only card-frame hypothesis; not evidence of card identity.

    Prefer a card-shaped inner rectangle over a large square desk or elongated
    grading slab. Rounded corners and moderate perspective remain supported.
    No catalogue IDs, OCR labels or recognition scores enter this selection.
    """
    rect = _order_points(points)
    if len(np.unique(rect, axis=0)) != 4 or not cv2.isContourConvex(rect):
        return None
    tl, tr, br, bl = rect
    sides = np.array([np.linalg.norm(tr-tl), np.linalg.norm(br-bl),
                      np.linalg.norm(bl-tl), np.linalg.norm(br-tr)])
    w, h = float(sides[:2].mean()), float(sides[2:].mean())
    if min(w, h) < 65 or min(sides[:2])/max(sides[:2]) < .60 or min(sides[2:])/max(sides[2:]) < .60:
        return None
    # Check the actual output dimensions too: extreme trapezoids can have a
    # plausible average aspect but warp into a square/landscape text fragment.
    output_w, output_h = float(max(sides[:2])), float(max(sides[2:]))
    aspect = min(output_w/output_h, output_h/output_w)
    if not .54 <= aspect <= .84:
        return None
    area = float(cv2.contourArea(rect))
    width, height = image_size
    fraction = area / (width*height)
    if not .10 <= fraction <= .995 or not .70 <= area/(w*h) <= 1.15:
        return None
    shape = math.exp(-6 * abs(math.log(aspect/(63/88))))
    return shape + .30*math.sqrt(fraction)


def card_frame_candidates(image: Image.Image, limit: int = 3) -> list[Image.Image]:
    array = np.asarray(image)
    height, width = array.shape[:2]
    gray = cv2.cvtColor(array, cv2.COLOR_RGB2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    # External-only contours hide the card inside a sleeve/slab/stand. Inspect
    # nested outlines, at two fixed edge scales, without cropping by label.
    candidates: list[tuple[float, np.ndarray]] = []
    for low, high in ((35, 100), (70, 180)):
        edges = cv2.Canny(blur, low, high)
        edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
        contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:80]:
            if cv2.contourArea(contour) < width*height*.10:
                continue
            peri = cv2.arcLength(contour, True)
            for epsilon in (.015, .025, .04):
                approx = cv2.approxPolyDP(contour, epsilon * peri, True)
                if len(approx) != 4:
                    continue
                points = approx.reshape(4, 2).astype(np.float32)
                score = _frame_score(points, (width, height))
                if score is not None:
                    candidates.append((score, _order_points(points)))
    frames, accepted = [], []
    for score, rect in sorted(candidates, key=lambda c: -c[0]):
        # Inner/outer sides of the same border must not consume all slots.
        if any(float(np.linalg.norm(rect-old, axis=1).mean()) < .04*min(width,height) for old in accepted):
            continue
        tl, tr, br, bl = rect
        max_w = int(max(np.linalg.norm(br-bl),np.linalg.norm(tr-tl)))
        max_h = int(max(np.linalg.norm(tr-br),np.linalg.norm(tl-bl)))
        if min(max_w,max_h) < 80:
            continue
        dest = np.array([[0,0],[max_w-1,0],[max_w-1,max_h-1],[0,max_h-1]],dtype=np.float32)
        matrix = cv2.getPerspectiveTransform(rect,dest)
        frames.append(Image.fromarray(cv2.warpPerspective(array,matrix,(max_w,max_h))))
        accepted.append(rect)
        if len(frames) >= limit:
            break
    return frames


def detect_and_rectify(image: Image.Image) -> tuple[Image.Image, bool]:
    frames = card_frame_candidates(image, limit=1)
    return (frames[0], True) if frames else (image, False)
