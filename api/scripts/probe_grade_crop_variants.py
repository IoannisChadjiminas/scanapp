"""Diagnostic only: test bounded original-pixel grade crops without truth inputs."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
from app.recognition.grading import LabelLine, parse_label
from app.recognition.label_vision import grade_regions
from app.recognition.ocr import CardOcr


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--traces',type=Path,action='append',required=True)
    p.add_argument('--models',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();args.output.mkdir(exist_ok=False)
    from rapidocr.utils.vis_res import VisRes
    VisRes.get_font_path=lambda *a,**k:'unused-diagnostic-font'
    reader=CardOcr(str(args.models/'PP-OCRv6_det_small.onnx'),
        str(args.models/'PP-OCRv6_rec_small.onnx'),
        str(args.models/'ch_ppocr_mobile_v2.0_cls_mobile.onnx'),1,1)
    for trace_dir in args.traces:
        for path in sorted(trace_dir.glob('*/trace.json')):
            trace=json.loads(path.read_text());panels=0
            for call in trace['calls']:
                if call.get('mode')=='direct_recognition':continue
                lines=[LabelLine(l['text'],l['confidence'],tuple(l['box']) if l['box'] else None)
                       for l in call['lines']]
                parsed=parse_label(lines)
                if not parsed.company or parsed.grade is not None:continue
                panel=Image.open(path.parent/call['image']).convert('RGB')
                regions=grade_regions(panel,lines,parsed.company)
                if not regions:continue
                panels+=1
                # Existing component bounds are observed, not an assumed digit.
                for index,(patch,box) in enumerate(regions):
                    l,t,r,b=box
                    for padding in (.05,.15,.30):
                        dx=(r-l)*padding;dy=(b-t)*padding
                        tile=panel.crop((max(0,round((l-dx)*panel.width)),max(0,round((t-dy)*panel.height)),
                            min(panel.width,round((r+dx)*panel.width)),min(panel.height,round((b+dy)*panel.height))))
                        if min(tile.size)<5:continue
                        file=args.output/f'{trace["id"]}-{panels}-{index}-{padding}.png';tile.save(file)
                        token=reader._grading_tokens([tile])
                        print(json.dumps(dict(id=trace['id'],panel=call['image'],box=box,padding=padding,
                            file=str(file),lines=[dict(text=l.text,confidence=l.confidence) for l in token])),flush=True)
                if panels>=2:break


if __name__=='__main__':main()
