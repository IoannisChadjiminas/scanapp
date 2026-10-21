"""Loose foreground proposals for broken card outlines, never printing proof.

These are bounded retrieval hypotheses. They may contain holders/background or
omit metadata, so callers must retain normal verification/ambiguity safeguards.
"""
from __future__ import annotations

import cv2
import numpy as np
from PIL import Image

from app.recognition.detect import _frame_score, _order_points


def line_frame_candidates(image: Image.Image, limit: int = 2) -> list[Image.Image]:
    """Join supported edge segments when glare breaks a closed outline.

    Work at a bounded resolution and retain at most twelve distinct lines per
    axis. These upright portrait proposals are retrieval hypotheses only: a
    holder can have exactly the same geometry as a card.
    """
    if limit < 1 or min(image.size) < 120:
        return []
    original = np.asarray(image.convert('RGB'))
    scale = min(1., 720 / max(image.size))
    array = cv2.resize(original, None, fx=scale, fy=scale) if scale < 1 else original
    h, w = array.shape[:2]
    gray = cv2.cvtColor(array, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 35, 100)
    segments = cv2.HoughLinesP(edges, 1, np.pi/360, threshold=35,
                               minLineLength=round(.20*min(w,h)),
                               maxLineGap=round(.035*min(w,h)))
    if segments is None:
        return []
    buckets: list[list[tuple[float, np.ndarray]]] = [[], []]
    for x1,y1,x2,y2 in segments.reshape(-1,4):
        start, end = np.array([x1,y1], float), np.array([x2,y2], float)
        delta = end-start
        length = float(np.linalg.norm(delta))
        direction = delta/length
        # Exclude diagonal artwork/rules strokes, but permit moderate tilt.
        axis = 0 if abs(direction[0]) > .94 else 1 if abs(direction[1]) > .94 else None
        if axis is None:
            continue
        normal = np.array([-direction[1], direction[0]])
        if normal[axis ^ 1] < 0:
            normal = -normal
        line = np.r_[normal, -normal.dot(start)]
        buckets[axis].append((length, line))
    lines = []
    for bucket in buckets:
        distinct = []
        for _, line in sorted(bucket, key=lambda item: -item[0]):
            if any(np.dot(line[:2], old[:2]) > .995 and
                   abs(line[2]-old[2]) < .02*min(w,h) for old in distinct):
                continue
            distinct.append(line)
            if len(distinct) == 12:
                break
        lines.append(distinct)
    distance = cv2.distanceTransform(255-edges, cv2.DIST_L2, 3)
    proposals = []
    from itertools import combinations
    for top,bottom in combinations(lines[0],2):
        if top[:2].dot(bottom[:2]) < .97:
            continue
        for left,right in combinations(lines[1],2):
            if left[:2].dot(right[:2]) < .97:
                continue
            points = []
            for horizontal,vertical in ((top,left),(top,right),(bottom,right),(bottom,left)):
                matrix = np.array([horizontal[:2], vertical[:2]])
                points.append(np.linalg.solve(matrix, -np.array([horizontal[2],vertical[2]])))
            rect = _order_points(np.float32(points))
            if rect[:,0].min()<0 or rect[:,1].min()<0 or rect[:,0].max()>=w or rect[:,1].max()>=h:
                continue
            tl,tr,br,bl = rect
            fw = max(np.linalg.norm(tr-tl),np.linalg.norm(br-bl))
            fh = max(np.linalg.norm(bl-tl),np.linalg.norm(br-tr))
            # A landscape rules panel must not masquerade as an upright card.
            if not .54 <= fw/fh <= .84:
                continue
            score = _frame_score(rect,(w,h))
            if score is None:
                continue
            supports = []
            for start,end in zip(rect,np.roll(rect,-1,axis=0)):
                samples = np.linspace(start,end,48).round().astype(int)
                samples[:,0] = np.clip(samples[:,0],0,w-1)
                samples[:,1] = np.clip(samples[:,1],0,h-1)
                supports.append(float(np.mean(distance[samples[:,1],samples[:,0]] <= max(2,.005*min(w,h)))))
            if min(supports) >= .25 and np.mean(supports) >= .55:
                proposals.append((score+.40*float(np.mean(supports)),rect/scale))
    frames, accepted = [], []
    for _,rect in sorted(proposals,key=lambda item:-item[0]):
        if any(np.linalg.norm(rect-old,axis=1).mean() < .05*min(image.size) for old in accepted):
            continue
        tl,tr,br,bl = rect
        fw = int(max(np.linalg.norm(tr-tl),np.linalg.norm(br-bl)))
        fh = int(max(np.linalg.norm(bl-tl),np.linalg.norm(br-tr)))
        target = np.float32([[0,0],[fw-1,0],[fw-1,fh-1],[0,fh-1]])
        transform = cv2.getPerspectiveTransform(rect,target)
        frames.append(Image.fromarray(cv2.warpPerspective(original,transform,(fw,fh))))
        accepted.append(rect)
        if len(frames) >= limit:
            break
    return frames


def portrait_window_candidates(image: Image.Image) -> list[tuple[str, Image.Image]]:
    """Two generic centered portrait windows for outlines broken by sleeves.

    These are search hypotheses, not detected cards or evidence of completeness.
    Neither coordinates nor scales depend on a catalogue ID or benchmark label.
    """
    w, h = image.size
    max_height = min(h, w / (63/88))
    output = []
    for scale in (.70, .85):
        height = round(scale * max_height)
        width = round(height * 63/88)
        if min(width, height) < 80:
            continue
        left, top = (w-width)//2, (h-height)//2
        output.append((f'window_{scale:.2f}', image.crop((left,top,left+width,top+height))))
    return output


def slab_interior_candidate(image: Image.Image) -> tuple[str, Image.Image] | None:
    """A lower portrait region for tall holders; never certify slab geometry."""
    w, h = image.size
    if not .50 <= w/h <= .80 or min(w,h) < 120:
        return None
    # Portrait-aspect lower window, excluding the upper grading label. A slab
    # can occupy a square/near-card-shaped photo rather than fill a tall frame.
    height = round(.68*h)
    width = min(w, round(height*63/88))
    left, top = (w-width)//2, round(.24*h)
    return ('slab_interior', image.crop((left,top,left+width,top+height)))


def loose_frame_candidates(image: Image.Image, limit: int = 2) -> list[Image.Image]:
    if limit < 1:
        return []
    array = np.asarray(image.convert('RGB'))
    h, w = array.shape[:2]
    gray = cv2.cvtColor(array, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray,(5,5),0),35,100)
    saturation = cv2.cvtColor(array,cv2.COLOR_RGB2HSV)[:,:,1]
    masks = [edges, np.uint8(saturation>55)*255]
    # Colour-distance foreground helps on plain tables, not every background.
    n = max(1,round(min(w,h)*.06))
    corners = np.concatenate([array[:n,:n].reshape(-1,3),array[-n:,-n:].reshape(-1,3),
                              array[:n,-n:].reshape(-1,3),array[-n:,:n].reshape(-1,3)])
    background = np.median(corners,axis=0)
    distance = np.linalg.norm(array.astype(np.float32)-background,axis=2)
    masks.append(np.uint8(distance>65)*255)
    proposals = []
    for mask in masks:
        mask = cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((7,7),np.uint8))
        contours,_ = cv2.findContours(mask,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
        hulls = [cv2.convexHull(c) for c in contours if len(c)>=4]
        for hull in sorted(hulls,key=cv2.contourArea,reverse=True)[:30]:
            area = float(cv2.contourArea(hull))
            if area < .12*w*h:
                continue
            rect = _order_points(cv2.boxPoints(cv2.minAreaRect(hull)))
            box_area = float(cv2.contourArea(rect))
            if box_area <= 0 or area/box_area < .7:
                continue
            if (rect[:,0].min()<0 or rect[:,1].min()<0 or rect[:,0].max()>=w or rect[:,1].max()>=h):
                continue
            score = _frame_score(rect,(w,h))
            if score is not None:
                proposals.append((score,rect))
    frames, accepted = [], []
    for score,rect in sorted(proposals,key=lambda p:-p[0]):
        if any(np.linalg.norm(rect-old,axis=1).mean()<.05*min(w,h) for old in accepted):
            continue
        tl,tr,br,bl = rect
        fw=int(max(np.linalg.norm(tr-tl),np.linalg.norm(br-bl)))
        fh=int(max(np.linalg.norm(bl-tl),np.linalg.norm(br-tr)))
        if min(fw,fh)<80:
            continue
        dest=np.float32([[0,0],[fw-1,0],[fw-1,fh-1],[0,fh-1]])
        matrix=cv2.getPerspectiveTransform(rect,dest)
        frames.append(Image.fromarray(cv2.warpPerspective(array,matrix,(fw,fh))))
        accepted.append(rect)
        if len(frames)>=limit:
            break
    return frames
