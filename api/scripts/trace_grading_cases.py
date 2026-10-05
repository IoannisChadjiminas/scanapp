"""Offline, per-pass label diagnostics; no truth data enters the OCR parser."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.recognition.images import decode_image
from app.recognition.ocr import CardOcr
import app.recognition.label_vision as vision


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results',type=Path,required=True)
    parser.add_argument('--sources',type=Path,required=True)
    parser.add_argument('--models',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    root = Path(__file__).resolve().parents[2]
    sources = {p['id']:p for p in json.loads(args.sources.read_text())['photos']}
    cases = [p for p in json.loads(args.results.read_text())['cases']
             if not(p['company_correct'] and p['grade_correct'])]
    from rapidocr.utils.vis_res import VisRes
    VisRes.get_font_path = lambda *a, **k: 'unused-audit-font'
    reader = CardOcr(str(args.models/'PP-OCRv6_det_small.onnx'),
        str(args.models/'PP-OCRv6_rec_small.onnx'),
        str(args.models/'ch_ppocr_mobile_v2.0_cls_mobile.onnx'),1,1)
    original_read,original_logo = reader._grading_lines,vision.logo_company
    original_tokens = reader._grading_tokens
    for case in cases:
        folder = args.output/case['id']; folder.mkdir()
        calls,logos = [],[]
        def trace_read(image):
            name = f'ocr-{len(calls)+1}.png'; image.save(folder/name)
            lines = original_read(image)
            calls.append({'image':name,'size':image.size,'lines':[
                {'text':l.text,'confidence':l.confidence,
                 'box':list(l.box) if l.box else None} for l in lines]})
            return lines
        def trace_logo(image, **kwargs):
            name = f'logo-{len(logos)+1}.png'; image.save(folder/name)
            result = original_logo(image, **kwargs)
            logos.append({'image':name,'size':image.size,'result':result})
            return result
        def trace_tokens(patches):
            result = original_tokens(patches)
            for index,patch in enumerate(patches):
                name = f'ocr-{len(calls)+1}.png';patch.save(folder/name)
                line = result[index] if index<len(result) else None
                calls.append({'image':name,'size':patch.size,'mode':'direct_recognition',
                    'lines':[{'text':line.text,'confidence':line.confidence,'box':None}] if line else []})
            return result
        reader._grading_lines = trace_read; vision.logo_company = trace_logo
        reader._grading_tokens = trace_tokens
        image = decode_image((root/sources[case['id']]['path']).read_bytes(),12_000_000).image
        result = reader.read_grading(image)
        record = {'id':case['id'],'input_size':image.size,'calls':calls,'logos':logos,
                  'grading':result.model_dump(mode='json')}
        (folder/'trace.json').write_text(json.dumps(record,indent=2)+'\n')
        print(json.dumps(record),flush=True)


if __name__ == '__main__':
    main()
