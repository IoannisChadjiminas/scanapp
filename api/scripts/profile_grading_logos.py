"""Measure official-logo correlation on saved OCR proposals (offline only)."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
from PIL import Image
from app.recognition.label_vision import _logo_masks


def scores(image):
    array = np.asarray(image.convert('RGB'))
    scale = min(1.,800/image.width)
    if scale < 1:
        array = cv2.resize(array,None,fx=scale,fy=scale)
    gray = cv2.cvtColor(array,cv2.COLOR_RGB2GRAY)
    gray = cv2.createCLAHE(clipLimit=2.,tileGridSize=(8,8)).apply(gray)
    h,w = gray.shape
    results = {}
    for company,mask in _logo_masks().items():
        best = (0.,None)
        for angle in (0,-8,8):
            matrix = cv2.getRotationMatrix2D((w/2,h/2),angle,1.)
            rotated = cv2.warpAffine(gray,matrix,(w,h),borderMode=cv2.BORDER_REPLICATE)
            for height in range(8,min(100,h),2):
                for aspect in (.85,1.,1.15):
                    width = round(height*mask.shape[1]/mask.shape[0]*aspect)
                    if width >= w:
                        continue
                    template = cv2.resize(mask,(width,height),interpolation=cv2.INTER_AREA)
                    correlation = cv2.matchTemplate(rotated,template,cv2.TM_CCOEFF_NORMED)
                    _,score,_,location = cv2.minMaxLoc(np.abs(correlation))
                    if score > best[0]:
                        best = (score,dict(angle=angle,height=height,width=width,location=location))
        results[company] = best
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('images',nargs='+',type=Path)
    args = parser.parse_args()
    for path in args.images:
        with Image.open(path) as image:
            print(json.dumps(dict(path=str(path),size=image.size,scores=scores(image))),flush=True)


if __name__ == '__main__':
    main()
