"""Private labelled contact sheets for independent visual benchmark review."""
import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--photos',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    records=[r for r in json.loads((args.photos/'downloads.json').read_text())['photos']
             if r['download_status']=='downloaded']
    for start in range(0,len(records),6):
        sheet=Image.new('RGB',(1440,1500),'#eeeeee')
        draw=ImageDraw.Draw(sheet)
        selected=records[start:start+6]
        for i,record in enumerate(selected):
            x,y=(i%3)*480,(i//3)*750
            with Image.open(args.photos/(record['id']+'.jpg')) as original:
                pixels=ImageOps.contain(ImageOps.exif_transpose(original).convert('RGB'),(460,715))
            sheet.paste(pixels,(x+(480-pixels.width)//2,y+25))
            draw.text((x+10,y+6),record['id'],fill='black')
        path=args.output/f'sheet-{start//6+1:02}.jpg'
        sheet.save(path,quality=94)
        print(json.dumps({'sheet':str(path),'photos':[r['id'] for r in selected]}),flush=True)


if __name__=='__main__':
    main()
