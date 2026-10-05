"""Offline recovery experiments on original label pixels; never infers grades."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
from PIL import Image
from app.recognition.ocr import CardOcr


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--direct-only',action='store_true')
    parser.add_argument('images',nargs='+',type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    from rapidocr.utils.vis_res import VisRes
    VisRes.get_font_path = lambda *a,**k:'unused-audit-font'
    reader = CardOcr(str(args.models/'PP-OCRv6_det_small.onnx'),
        str(args.models/'PP-OCRv6_rec_small.onnx'),
        str(args.models/'ch_ppocr_mobile_v2.0_cls_mobile.onnx'),1,1)
    for index,path in enumerate(args.images):
        with Image.open(path) as image:
            array = np.asarray(image.convert('RGB'))
        # Same right-column hypothesis for every label, no truth/case lookup.
        array = array[:,round(.55*array.shape[1]):]
        gray = cv2.cvtColor(array,cv2.COLOR_RGB2GRAY)
        variants = {'original':array,'gray':gray,
                    'median5':cv2.medianBlur(gray,5),'median9':cv2.medianBlur(gray,9),
                    'close3x7':cv2.morphologyEx(gray,cv2.MORPH_CLOSE,np.ones((7,3),np.uint8)),
                    'open3x7':cv2.morphologyEx(gray,cv2.MORPH_OPEN,np.ones((7,3),np.uint8))}
        for name,pixels in ([] if args.direct_only else variants.items()):
            patch = Image.fromarray(pixels).convert('RGB')
            scale = 1000/patch.width
            patch = patch.resize((1000,round(patch.height*scale)))
            file = args.output/f'{index}-{name}.png';patch.save(file)
            lines = reader._grading_lines(patch)
            print(json.dumps(dict(source=str(path),variant=name,image=str(file),
                lines=[dict(text=l.text,confidence=l.confidence,box=l.box) for l in lines])),flush=True)
        # Direct recognition around an observed condition heading. This tests
        # whether the detector (not the recognizer) drops large stylized glyphs.
        with Image.open(path) as raw:
            raw = raw.convert('RGB')
            from app.recognition.label_vision import contrast_label
            lines = [*reader._grading_lines(raw),*reader._grading_lines(contrast_label(raw))]
            from app.recognition.grading import _condition,_text
            for line in lines:
                if not line.box or not _condition(_text(line.text),None):
                    continue
                x0,y0,x1,y1 = line.box; height=y1-y0; width=x1-x0
                for side,top,bottom in [('above',max(0,y0-5*height),y0),
                                        ('below',y1,min(1,y1+6*height))]:
                    tile = raw.crop((round(max(0,x0-.2*width)*raw.width),round(top*raw.height),
                        round(min(1,x1+.2*width)*raw.width),round(bottom*raw.height)))
                    if min(tile.size)<5:
                        continue
                    for kind,pixels in [('rgb',np.asarray(tile)),('gray',cv2.cvtColor(np.asarray(tile),cv2.COLOR_RGB2GRAY))]:
                        patch = Image.fromarray(pixels).convert('RGB')
                        patch.save(args.output/f'{index}-direct-{side}-{kind}.png')
                        output = reader.engine.get_rec_res([np.asarray(patch)])
                        print(json.dumps(dict(source=str(path),variant='direct-'+side+'-'+kind,
                            result=reader._parse_output(output))),flush=True)


if __name__ == '__main__':
    main()
