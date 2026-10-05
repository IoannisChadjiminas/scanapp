"""Private geometric/official-logo diagnostics; no grade prediction tuning."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw, ImageOps
from app.recognition.label_vision import label_panels, logo_company

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sources',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); a.output.mkdir(exist_ok=False)
    root=Path(__file__).resolve().parents[2]
    records=json.loads(a.sources.read_text())['photos']; results=[]
    for start in range(0,len(records),6):
        sheet=Image.new('RGB',(1500,900),'#eee'); draw=ImageDraw.Draw(sheet)
        for j,r in enumerate(records[start:start+6]):
            image=ImageOps.exif_transpose(Image.open(root/r['path'])).convert('RGB')
            panels=label_panels(image)
            logo=logo_company(panels[0]) if panels else None
            results.append({'id':r['id'],'panels':len(panels),'logo':logo})
            patch=ImageOps.contain(panels[0] if panels else image.crop((0,0,image.width,.36*image.height)),(490,410))
            x,y=(j%3)*500,(j//3)*450
            sheet.paste(patch,(x,y+30));draw.text((x+3,y+3),f"{r['id']} {logo}",fill='black')
        sheet.save(a.output/f'regions-{start//6+1:02}.jpg',quality=95)
    (a.output/'regions.json').write_text(json.dumps(results,indent=2))
    print(json.dumps({'panels':sum(r['panels']>0 for r in results),'logos':sum(r['logo'] is not None for r in results)}))

if __name__=='__main__':main()
