"""Offline positive Play! Pokemon logo template; no photographed query inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import cv2
import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.recognition.stamp_printing import VERSION

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference',type=Path,required=True)
    p.add_argument('--source-url',required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    # Verified logo occupies this area on the source reference, not a runtime
    # layout assumption. Only the common logo's keypoints are stored.
    image=Image.open(a.reference).convert('RGB')
    box=(.77,.409,.969,.515)
    patch=image.crop(tuple(round(v*(image.width if i%2==0 else image.height)) for i,v in enumerate(box)))
    pixels=cv2.cvtColor(np.asarray(patch),cv2.COLOR_RGB2GRAY)
    keys,descriptors=cv2.SIFT_create(nfeatures=200,contrastThreshold=.02).detectAndCompute(pixels,None)
    assert descriptors is not None and len(keys)>=12
    a.output.mkdir(parents=True,exist_ok=True)
    binary=a.output/'play_stamp.npz'
    assert not binary.exists(), 'Never overwrite a reviewed template'
    np.savez_compressed(binary,points=np.float32([k.pt for k in keys]),descriptors=descriptors,
                        size=np.int32(patch.size))
    (a.output/'play_stamp.json').write_text(json.dumps(dict(version=VERSION,
        sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
        source_sha256=hashlib.sha256(a.reference.read_bytes()).hexdigest(),
        source_url=a.source_url,source_box=box,source_kind='independent_catalogue_not_official',
        use='positive logo observation and review-only ordering; never proof of absence'),indent=2)+'\n')

if __name__=='__main__':main()
