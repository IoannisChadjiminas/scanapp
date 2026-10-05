"""Private framing/keypoint diagnostic; generated previews stay outside Git."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.recognition.detect import detect_and_rectify
from app.recognition.images import decode_image, blur_variance
from app.recognition.local_match import LocalArtworkVerifier
from app.recognition.frame_fallback import line_frame_candidates, portrait_window_candidates, slab_interior_candidate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--photos',type=Path,required=True)
    parser.add_argument('--sources',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--only',action='append',default=[])
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    catalog=sqlite3.connect('file:/data/catalog.sqlite?mode=ro',uri=True)
    verifier=LocalArtworkVerifier(Path('/data'))
    for photo in json.loads(args.sources.read_text())['photos']:
        if args.only and photo['id'] not in args.only:
            continue
        raw=decode_image((args.photos / (photo['id']+'.jpg')).read_bytes(),12_000_000).image
        rectified,detected=detect_and_rectify(raw)
        reference=catalog.execute('SELECT image_path FROM cards WHERE id=?',(photo['expected_card_id'],)).fetchone()[0]
        rarity=catalog.execute('SELECT rarity FROM cards WHERE id=?',(photo['expected_card_id'],)).fetchone()[0]
        from app.recognition.local_match import FULL_ART_RARITIES, FULL_ART_BOX
        if (rarity or '').lower() in FULL_ART_RARITIES:
            verifier.reference_boxes[photo['expected_card_id']]=FULL_ART_BOX
        alignment=[]
        aligned=verifier.propose_frame(raw,(photo['expected_card_id'],reference),alignment)
        print(json.dumps({'photo':photo['id'],'forced_truth_alignment':alignment,'alignment_returned':aligned is not None}),flush=True)
        if aligned is not None:
            aligned.save(args.output/(photo['id']+'-aligned.jpg'))
        proposals=[('raw',raw),('detected',rectified)]
        proposals.extend(portrait_window_candidates(raw))
        slab=slab_interior_candidate(raw)
        if slab:
            proposals.append(slab)
        proposals.extend((f'line_{i}',p) for i,p in enumerate(line_frame_candidates(raw,limit=8)))
        for profile,image in proposals:
            proof=verifier.verify(image,[(photo['expected_card_id'],reference)])
            image.save(args.output / (photo['id']+'-'+profile+'.jpg'))
            print(json.dumps({'photo':photo['id'],'profile':profile,'raw_size':raw.size,'query_size':image.size,
                'detected':detected,'blur':blur_variance(image),
                'forced_truth_geometry':[vars(m) for m in proof]}),flush=True)
    catalog.close()


if __name__=='__main__':
    main()
