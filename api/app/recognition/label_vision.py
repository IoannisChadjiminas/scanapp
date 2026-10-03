"""Bounded label-region proposals and official logo shape verification.

Rectangles are OCR proposals, never slab/issuer proof. Logo matches may only
contribute an issuer when the caller independently verifies label text context.
No card IDs, certification numbers, label colours or benchmark images are used.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from app.recognition.detect import _order_points
from app.recognition.grading_control import check_grading_cancelled


def text_label_panel(image: Image.Image, lines, *, compact=False, strip_fraction=.36) -> Image.Image | None:
    """A localized OCR proposal from independent label-field locations.

    Input boxes refer to the top 36% strip; never create a proposal from only
    a seller logo, a card title or an incidental digit. All pixels are original.
    """
    import re
    from app.recognition.grading import MIN_CONFIDENCE, NUMBER, _condition, _label_identity, _text, brand_company
    reliable = [line for line in lines if line.box is not None and
                line.confidence is not None and line.confidence >= MIN_CONFIDENCE]
    company = next((brand_company(line.text) for line in reliable if brand_company(line.text)),None)
    markers, kinds = [], set()
    for line in reliable:
        text = _text(line.text)
        kind = ('brand' if brand_company(text) else 'identity' if _label_identity(text)
                else 'certificate' if re.fullmatch(r'\d{6,14}',text)
                else 'condition' if _condition(text,company)
                else 'grade' if re.fullmatch(NUMBER,text) else None)
        if kind:
            markers.append(line.box); kinds.add(kind)
    if not ({'condition','identity'} <= kinds or {'brand','certificate'} <= kinds
            or {'brand','identity'} <= kinds):
        return None
    if len(markers) < 2:
        return None
    left,top = np.min(np.asarray(markers)[:,:2],axis=0)
    right,bottom = np.max(np.asarray(markers)[:,2:],axis=0)
    if right-left < .07 or bottom-top > .90:
        return None
    height = bottom-top
    # Include an overhanging top logo and the bottom security mark. Dimensions
    # follow observed text, not a company-specific card/label lookup.
    left=max(0.,left-(.18 if compact else .30)); right=min(1.,right+(.12 if compact else .15))
    top=max(0.,top-(.40 if compact else 1.5 if len(markers)==2 else .90)*height)
    bottom=min(1.25,bottom+(.15 if compact else .45)*height)
    box=(round(left*image.width),round(top*strip_fraction*image.height),
         round(right*image.width),min(image.height,round(bottom*strip_fraction*image.height)))
    if box[2]-box[0] < 80 or box[3]-box[1] < 25:
        return None
    return image.crop(box)


def label_panels(image: Image.Image, limit: int = 2) -> list[Image.Image]:
    if min(image.size) < 100 or limit < 1:
        return []
    original = np.asarray(image.convert('RGB'))
    scale = min(1., 1000/max(image.size))
    array = cv2.resize(original,None,fx=scale,fy=scale) if scale < 1 else original
    h,w = array.shape[:2]
    gray = cv2.cvtColor(array,cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray,(3,3),0),35,100)
    edges = cv2.morphologyEx(edges,cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))
    contours,_ = cv2.findContours(edges,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if not .0008*w*h <= area <= .25*w*h:
            continue
        quad = cv2.approxPolyDP(contour,.025*cv2.arcLength(contour,True),True)
        if len(quad) == 4 and cv2.isContourConvex(quad):
            rect = _order_points(quad.reshape(4,2).astype(np.float32))
        else:
            # Rounded panels and a TAG logo breaking the top rule can create
            # extra vertices. Require the contour to fill its fitted rectangle.
            fitted = cv2.minAreaRect(contour)
            if fitted[1][0]*fitted[1][1] <= 0 or area/(fitted[1][0]*fitted[1][1]) < .80:
                continue
            rect = _order_points(cv2.boxPoints(fitted))
        tl,tr,br,bl = rect
        fw = max(np.linalg.norm(tr-tl),np.linalg.norm(br-bl))
        fh = max(np.linalg.norm(bl-tl),np.linalg.norm(br-tr))
        if fw < .10*w or fh < 12 or not 2.1 <= fw/fh <= 6.5:
            continue
        if rect[:,1].mean() > .67*h or area/(fw*fh) < .75:
            continue
        # Prefer upper, large, supported panels rather than attack text boxes.
        score = area/(w*h) - .12*rect[:,1].mean()/h
        candidates.append((score,rect,fw,fh))
    accepted, output = [], []
    for _,rect,fw,fh in sorted(candidates,key=lambda p:-p[0]):
        box = (*rect.min(axis=0),*rect.max(axis=0))
        def overlap(other):
            x0,y0 = np.maximum(box[:2],other[:2]); x1,y1 = np.minimum(box[2:],other[2:])
            inter = max(0,x1-x0)*max(0,y1-y0)
            return inter/max(1,min((box[2]-box[0])*(box[3]-box[1]),
                                 (other[2]-other[0])*(other[3]-other[1])))
        if any(overlap(old) > .65 for old in accepted):
            continue
        fw,fh = max(1,round(fw/scale)),max(1,round(fh/scale))
        # Small outward padding is added after warp, never fills invented text.
        target = np.float32([[0,0],[fw-1,0],[fw-1,fh-1],[0,fh-1]])
        matrix = cv2.getPerspectiveTransform(rect/scale,target)
        patch = cv2.warpPerspective(original,matrix,(fw,fh))
        # Hologram/company marks often protrude a little below the label's
        # inner rectangular rule. Include original pixels, not painted padding.
        extended = target.copy()
        extended[:,0] += .06*fw; extended[:,1] += .08*fh
        matrix = cv2.getPerspectiveTransform(rect/scale,extended)
        patch = cv2.warpPerspective(original,matrix,(round(1.12*fw),round(1.16*fh)),
                                    borderMode=cv2.BORDER_REPLICATE)
        output.append(Image.fromarray(patch))
        accepted.append(box)
        if len(output) >= limit:
            break
    return output


def contrast_label(image: Image.Image) -> Image.Image:
    gray = cv2.cvtColor(np.asarray(image.convert('RGB')),cv2.COLOR_RGB2GRAY)
    gray = cv2.createCLAHE(clipLimit=2.,tileGridSize=(8,8)).apply(gray)
    # Text recognizers usually prefer dark strokes on a light label. This is
    # only a pixel transform, never company inference from the background.
    if float(np.median(gray)) < 110:
        gray = 255-gray
    return Image.fromarray(gray).convert('RGB')


def grade_regions(image: Image.Image, lines, company: str, *, tight: bool = False):
    """Original-pixel numeral hypotheses near an observed descriptor.

    Components supply observed ink bounds, never an assumed numeric value.
    Both above/below are possible; the recognizer must actually read a digit.
    The default preserves the established broad proposal. The first-strip
    recovery may request tight original-pixel glyph bounds as an extra view.
    """
    from app.recognition.grading import MIN_CONFIDENCE, _condition, _text
    descriptors = [l for l in lines if l.box and l.confidence is not None
                   and np.isfinite(l.confidence) and l.confidence >= MIN_CONFIDENCE
                   and _condition(_text(l.text),company)]
    descriptors.sort(key=lambda l:-(l.box[2]-l.box[0])*(l.box[3]-l.box[1]))
    if not descriptors:
        return []
    x0,y0,x1,y1 = descriptors[0].box
    width,height = x1-x0,y1-y0
    left,right = max(0,x0-.2*width),min(1,x1+.2*width)
    regions = []
    for top,bottom in [(max(0,y0-5*height),y0),(y1,min(1,y1+6*height))]:
        box = (round(left*image.width),round(top*image.height),
               round(right*image.width),round(bottom*image.height))
        if box[2]-box[0] < 15 or box[3]-box[1] < 12:
            continue
        patch = image.crop(box)
        gray = cv2.cvtColor(np.asarray(patch.convert('RGB')),cv2.COLOR_RGB2GRAY)
        _,binary = cv2.threshold(gray,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
        border = np.concatenate((binary[0],binary[-1],binary[:,0],binary[:,-1]))
        if np.mean(border)>127:
            binary = 255-binary
        # Low-contrast foil may sit on the background side of Otsu's split.
        # Observed edges retain its outline without assigning a digit identity.
        binary = cv2.bitwise_or(binary,cv2.Canny(gray,15,60))
        # Link small foil-texture gaps, not distant printed characters.
        binary = cv2.morphologyEx(binary,cv2.MORPH_CLOSE,np.ones((3,2),np.uint8))
        _,_,stats,_ = cv2.connectedComponentsWithStats(binary)
        components = [s for s in stats[1:] if s[cv2.CC_STAT_HEIGHT] >= .20*patch.height
                      and s[cv2.CC_STAT_AREA] >= .005*patch.width*patch.height
                      and s[cv2.CC_STAT_WIDTH] < .95*patch.width]
        if not components:
            # Foil gradients and illustrated labels can connect a numeral to
            # the background. The component detector is a proposal aid, not
            # a prerequisite for a literal OCR read. Reject blank patches;
            # otherwise retain the full observed region (never a tight glyph).
            if float(np.std(gray)) < 3:
                continue
            observed = (box[0]/image.width,box[1]/image.height,
                        box[2]/image.width,box[3]/image.height)
            regions.append((patch,observed))
            continue
        # Retain strokes of similar-height glyphs; exclude border/rule fragments.
        tallest = max(s[cv2.CC_STAT_HEIGHT] for s in components)
        components = [s for s in components if s[cv2.CC_STAT_HEIGHT] >= .55*tallest]
        l=min(s[0] for s in components); t=min(s[1] for s in components)
        r=max(s[0]+s[2] for s in components); b=max(s[1]+s[3] for s in components)
        observed = ((box[0]+l)/image.width,(box[1]+t)/image.height,
                    (box[0]+r)/image.width,(box[1]+b)/image.height)
        if tight:
            # The observed components can occupy only part of this proposal.
            # Crop their ink bounds with a small original-pixel margin, not a
            # thresholded reconstruction or an assumed numeral shape.
            dx=(observed[2]-observed[0])*.05;dy=(observed[3]-observed[1])*.05
            glyph = image.crop((max(0,round((observed[0]-dx)*image.width)),
                                max(0,round((observed[1]-dy)*image.height)),
                                min(image.width,round((observed[2]+dx)*image.width)),
                                min(image.height,round((observed[3]+dy)*image.height))))
            regions.append((glyph,observed))
        else:
            regions.append((patch,observed))
    return regions[:2]


@lru_cache(maxsize=1)
def _logo_masks():
    templates = {}
    for company in ('ace','ace-outline','ags','tag','psa','beckett','beckett-emblem'):
        path = Path(__file__).parent/'assets/grading-logos'/f'{company}.png'
        if not path.is_file():
            continue
        with Image.open(path) as image:
            alpha = np.asarray(image.convert('RGBA'))[:,:,3]
        ys,xs = np.where(alpha > 150)
        if not len(xs):
            continue
        mask = alpha[ys.min():ys.max()+1,xs.min():xs.max()+1]
        templates[company] = mask
    return templates


def _logo_matches(image: Image.Image, *, aggregate=True, text_boxes=()):
    """Exact multi-scale contour similarity, not a calibrated probability.

    Only lower-central logo positions of a localized label are considered.
    Reject weak/small/ambiguous shapes; text context is enforced by the caller.
    """
    check_grading_cancelled()
    array = np.asarray(image.convert('RGB'))
    scale = min(1.,800/image.width)
    if scale < 1:
        array = cv2.resize(array,None,fx=scale,fy=scale)
    gray = cv2.cvtColor(array,cv2.COLOR_RGB2GRAY)
    gray = cv2.createCLAHE(clipLimit=2.,tileGridSize=(8,8)).apply(gray)
    h,w = gray.shape
    # A monogram can correlate with a glyph inside an already read word.
    # Logo evidence must occupy independent pixels, not reuse label text.
    occupied = np.zeros((h,w),np.uint8)
    for x0,y0,x1,y1 in text_boxes:
        occupied[max(0,int(y0*h)):min(h,int(np.ceil(y1*h))),
                 max(0,int(x0*w)):min(w,int(np.ceil(x1*w)))] = 1
    integral = cv2.integral(occupied)
    def independent_scores(correlation, left, top, width, height):
        if not text_boxes:
            return np.abs(correlation)
        rows,cols = correlation.shape
        area = (integral[top+height:top+height+rows,left+width:left+width+cols]
            - integral[top:top+rows,left+width:left+width+cols]
            - integral[top+height:top+height+rows,left:left+cols]
            + integral[top:top+rows,left:left+cols])
        return np.where(area <= .20*width*height,np.abs(correlation),0.)
    results = []
    for template_name,mask in _logo_masks().items():
        check_grading_cancelled()
        company = template_name.split('-')[0]
        left,top,right,bottom = ((round(.20*w),0,round(.80*w),round(.48*h)) if company == 'tag'
            else (0,0,round(.80*w),h) if template_name == 'beckett-emblem'
            else (0,round(.45*h),round(.80*w),h) if company == 'beckett'
            else (round(.20*w),round(.55*h),round(.80*w),h))
        roi = gray[top:bottom,left:right]
        if min(roi.shape) < 14:
            continue
        best,box,best_shape = 0.,None,None
        # A single-letter seal at a few pixels is indistinguishable from
        # barcode strokes. Require enough observed detail for a monogram;
        # multi-letter wordmarks retain the smaller-scale search.
        minimum_height = 20 if template_name == 'beckett-emblem' else 10
        for height in range(minimum_height,min(85,roi.shape[0])):
            check_grading_cancelled()
            for aspect in (.85,1.,1.15):
                width = round(height*mask.shape[1]/mask.shape[0]*aspect)
                if width >= roi.shape[1]:
                    continue
                template = cv2.resize(mask,(width,height),interpolation=cv2.INTER_AREA)
                correlation = cv2.matchTemplate(roi,template,cv2.TM_CCOEFF_NORMED)
                # Polarity-invariant shape verification; no colour evidence.
                _,score,_,location = cv2.minMaxLoc(independent_scores(correlation,left,top,width,height))
                if score > best:
                    best = float(score)
                    x,y = location
                    box = ((left+x)/scale,(top+y)/scale,
                           (left+x+width)/scale,(top+y+height)/scale)
                    best_shape = (width,height)
        # Slightly tilted/holographic labels need contour alignment. Refine
        # only an already plausible official shape, without lowering the
        # acceptance threshold or creating a photo-specific template.
        if .55 <= best < .72 and best_shape is not None:
            base_width,base_height = best_shape
            for delta in (-1,0,1):
                height = max(minimum_height,base_height+delta)
                width = max(2,round(base_width*height/base_height))
                template = cv2.resize(mask,(width,height),interpolation=cv2.INTER_AREA)
                for angle in (-6,-3,3,6):
                    check_grading_cancelled()
                    radians = np.deg2rad(angle)
                    rw = round(abs(width*np.cos(radians))+abs(height*np.sin(radians)))+2
                    rh = round(abs(height*np.cos(radians))+abs(width*np.sin(radians)))+2
                    if rw >= roi.shape[1] or rh >= roi.shape[0]:
                        continue
                    matrix = cv2.getRotationMatrix2D((width/2,height/2),angle,1.)
                    matrix[:,2] += ((rw-width)/2,(rh-height)/2)
                    rotated = cv2.warpAffine(template,matrix,(rw,rh))
                    correlation = cv2.matchTemplate(roi,rotated,cv2.TM_CCOEFF_NORMED)
                    _,score,_,location = cv2.minMaxLoc(independent_scores(correlation,left,top,rw,rh))
                    if score > best:
                        best = float(score)
                        x,y = location
                        box = ((left+x)/scale,(top+y)/scale,
                               (left+x+rw)/scale,(top+y+rh)/scale)
        results.append((best,company,box))
    # Multiple officially documented marks of one issuer are alternatives,
    # not independent competing companies.
    if aggregate:
        results = [max((r for r in results if r[1] == company),key=lambda r:r[0])
                   for company in {r[1] for r in results}]
    results.sort(key=lambda r:-r[0])
    return results


def logo_company(image: Image.Image, *, text_boxes=()) -> tuple[str,float] | None:
    """Strong official shape match; weak shapes are only OCR proposals."""
    results = _logo_matches(image,text_boxes=text_boxes)
    if not results or results[0][0] < .72:
        return None
    if len(results)>1 and results[1][0] >= .72 and results[0][0]-results[1][0] < .12:
        return None
    return results[0][1],results[0][0]


def logo_text_regions(image: Image.Image):
    """Weak wordmark shapes may propose original-pixel text reads, not issuers."""
    regions = []
    for score,company,box in _logo_matches(image,aggregate=False):
        if score < .55 or box is None or company not in {'ags','beckett','psa','tag'}:
            continue
        left,top,right,bottom = box
        # Never OCR a square monogram as a wordmark merely because it belongs
        # to the same issuer. Alternative official marks remain shape-only.
        if (right-left)/(bottom-top) < 1.8:
            continue
        padding = max(2,.12*(bottom-top))
        patch = image.crop((max(0,round(left-padding)),max(0,round(top-padding)),
                            min(image.width,round(right+padding)),min(image.height,round(bottom+padding))))
        regions.append(patch)
    return regions[:2]
