"""Create an immutable-copy diagnostic manifest, including three reviewed phone photos."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--corpus',type=Path)
    p.add_argument('--captures',type=Path,required=True)
    args=p.parse_args()
    cases=[]
    if args.corpus:
        cases=json.loads((args.corpus/'cases.json').read_text())
        for case in cases:
            photo=args.output/case['photo_file']
            photo.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(args.corpus/case['photo_file'],photo)
    # Truth taken from visible printed number/art/stamp, never passed into OCR.
    truths={
        '5085926a-1afb-4505-88a9-c2f23fae34ba':'en:base1-24',
        '42d6de99-1ff8-4243-a728-214052715726':'en:xy12-35',
        'ed6e6f2e-a6eb-4100-861d-810fa2f65a5b':'en:30th-077',
    }
    for scan_id,truth in truths.items():
        source=args.captures/'images'/f'{scan_id}.input.jpg'
        target=args.output/'images'/source.name
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,target)
        cases.append(dict(id='phone_'+scan_id,kind='phone_capture',
            photo_file=str(target.relative_to(args.output)),expected_card_ids=[truth],
            sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
    with (args.output/'cases.json').open('x') as handle:
        json.dump(cases,handle,indent=2)


if __name__=='__main__':
    main()
