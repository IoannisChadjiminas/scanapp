"""Offline label OCR probe; no catalogue access or authentication calls.

Use --preview only to generate private review sheets from existing test photos.
Human-reviewed company/grade annotations must be collected independently of OCR.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw, ImageOps
from app.recognition.images import decode_image
from app.recognition.ocr import CardOcr


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--photos',type=Path,required=True)
    parser.add_argument('--sources',type=Path,required=True)
    parser.add_argument('--models',type=Path)
    parser.add_argument('--preview',type=Path)
    parser.add_argument('--code-snapshot',type=Path)
    args = parser.parse_args()
    records = json.loads(args.sources.read_text())['photos']
    if args.preview:
        args.preview.mkdir(parents=True,exist_ok=False)
        slabs = [record for record in records if 'slab' in record.get('conditions',[])]
        for start in range(0,len(slabs),6):
            sheet = Image.new('RGB',(1500,1000),'#eeeeee')
            draw = ImageDraw.Draw(sheet)
            for i,record in enumerate(slabs[start:start+6]):
                x,y = (i%3)*500,(i//3)*500
                with Image.open(args.photos/(record['id']+'.jpg')) as raw:
                    original = ImageOps.exif_transpose(raw).convert('RGB')
                    patch = original.crop((0,0,original.width,round(.36*original.height)))
                    patch = ImageOps.contain(patch,(490,460))
                    sheet.paste(patch,(x+(500-patch.width)//2,y+25))
                draw.text((x+10,y+6),record['id'],fill='black')
            path = args.preview/f'label-sheet-{start//6+1:02}.jpg'
            sheet.save(path,quality=95)
            print(json.dumps({'preview':str(path)}))
        return
    if not args.models:
        parser.error('--models is required for OCR')
    root = Path(__file__).resolve().parents[2]
    paths = ['app/recognition/grading.py','app/recognition/label_vision.py',
             'app/recognition/ocr.py','app/recognition/detect.py','app/schemas.py',
             'scripts/probe_grading_labels.py']
    paths += [str(p.relative_to(root/'api')) for p in
              sorted((root/'api/app/recognition/assets/grading-logos').glob('*')) if p.is_file()]
    def hashes():
        return {p:hashlib.sha256((root/'api'/p).read_bytes()).hexdigest() for p in paths}
    before = hashes()
    if args.code_snapshot:
        if args.code_snapshot.exists():
            parser.error('snapshot already exists; use a new output')
        args.code_snapshot.write_text(json.dumps({'code_hashes':before,
            'unchanged_after_run':False},indent=2)+'\n')
    # RapidOCR otherwise tries downloading an unused visualization font on
    # every call in network-isolated diagnostics. OCR itself is unchanged.
    from rapidocr.utils.vis_res import VisRes
    VisRes.get_font_path = lambda *a, **k: 'unused-label-audit-font'
    reader = CardOcr(str(args.models/'PP-OCRv6_det_small.onnx'),
        str(args.models/'PP-OCRv6_rec_small.onnx'),
        str(args.models/'ch_ppocr_mobile_v2.0_cls_mobile.onnx'),1,1)
    for record in records:
        image = decode_image((args.photos/(record['id']+'.jpg')).read_bytes(),12_000_000).image
        started = time.perf_counter()
        result = reader.read_grading(image)
        print(json.dumps({'id':record['id'],'conditions':record.get('conditions',[]),
            'grading_ms':round((time.perf_counter()-started)*1000,2),
            'grading':result.model_dump(mode='json')}),flush=True)
    assert before == hashes(), 'source changed during probe; discard this run'
    if args.code_snapshot:
        args.code_snapshot.write_text(json.dumps({'code_hashes':before,
            'unchanged_after_run':True},indent=2)+'\n')


if __name__ == '__main__':
    main()
