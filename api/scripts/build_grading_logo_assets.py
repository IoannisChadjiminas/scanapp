"""Build small issuer-logo templates from official sites, never test labels.

Offline runtime consumes these packaged PNGs; it makes no certificate requests.
"""
import base64
import hashlib
import io
import json
from pathlib import Path
import re

import httpx
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'api/app/recognition/assets/grading-logos'

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    records = []
    for company,url in [('ace','https://acegrading.com/apple-touch-icon.png'),
                        ('ags','https://agscard.com/logo.svg'),
                        ('tag','https://taggrading.com/cdn/shop/files/TAG_Logo_Official__NoText_Black_Outlined_260x.png?v=1674795543'),
                        ('psa','https://store.psacard.com/cdn/shop/files/PSA_Classic_Logo_red_text.png?v=1777044132&width=1013'),
                        ('beckett','https://maintenance.beckett.com/assets/slab-1.png')]:
        response = httpx.get(url,timeout=20,follow_redirects=False)
        response.raise_for_status()
        assert len(response.content) < 1_000_000
        data = response.content
        if company == 'ags':
            match = re.search(r'data:image/png;base64,([A-Za-z0-9+/=]+)',response.text)
            assert match, 'official logo no longer contains expected embedded PNG'
            data = base64.b64decode(match[1],validate=True)
        image = Image.open(io.BytesIO(data)).convert('RGBA')
        transform = 'embedded PNG' if company == 'ags' else 'RGBA conversion'
        if company == 'psa':
            # Exclude the detached registration symbol from the official
            # classic wordmark; no photographed label is used as a reference.
            image = image.crop((0,0,round(.93*image.width),image.height))
            transform = 'trim right 7% registration mark'
        if company == 'beckett':
            # Issuer's public example slab, NOT any benchmark photo. This is
            # the wordmark only: no numerical grades/certificates retained.
            assert image.size == (438,382), 'official asset layout changed'
            crop = np.asarray(image.crop((40,99,100,114)).convert('RGB'))
            rgba = np.full((*crop.shape[:2],4),255,np.uint8)
            rgba[:,:,3] = np.where(crop.min(axis=2)>170,255,0)
            image = Image.fromarray(rgba)
            transform = 'official wordmark box [40,99,100,114], white-stroke alpha mask'
        image.save(OUT/(company+'.png'))
        records.append({'company':company,'source_url':url,
            'transform':transform,
            'source_sha256':hashlib.sha256(response.content).hexdigest(),
            'asset_sha256':hashlib.sha256((OUT/(company+'.png')).read_bytes()).hexdigest()})
    # The foil outline seal differs from the filled website favicon. Use only
    # the issuer's own public example: no grades, cards or test photos retained.
    url = 'https://framerusercontent.com/images/SmhZfktrNiGLwzlPVnoHQOYUeQ.webp?height=1398&width=834'
    response = httpx.get(url,timeout=20,follow_redirects=False)
    response.raise_for_status()
    source = Image.open(io.BytesIO(response.content)).convert('RGB')
    assert source.size == (834,1398), 'official example layout changed'
    crop = np.asarray(source.crop((389,305,425,339)))
    rgba = np.full((*crop.shape[:2],4),255,np.uint8)
    rgba[:,:,3] = np.where(crop.min(axis=2)<125,255,0)
    asset = OUT/'ace-outline.png'
    Image.fromarray(rgba).save(asset)
    records.append({'company':'ace','source_page':'https://acegrading.com/',
        'source_url':url,'transform':'official seal only [389,305,425,339], dark-stroke alpha mask',
        'source_sha256':hashlib.sha256(response.content).hexdigest(),
        'asset_sha256':hashlib.sha256(asset.read_bytes()).hexdigest()})
    url = 'https://maintenance.beckett.com/assets/slab-1.png'
    response = httpx.get(url,timeout=20,follow_redirects=False)
    response.raise_for_status()
    source = Image.open(io.BytesIO(response.content)).convert('RGB')
    assert source.size == (438,382), 'official example layout changed'
    crop = np.asarray(source.crop((39,36,101,94)))
    rgba = np.full((*crop.shape[:2],4),255,np.uint8)
    rgba[:,:,3] = np.where(crop.min(axis=2)>175,255,0)
    asset = OUT/'beckett-emblem.png'
    Image.fromarray(rgba).save(asset)
    records.append({'company':'beckett','source_url':url,
        'transform':'official wreath/B emblem only [39,36,101,94], white-stroke alpha mask',
        'source_sha256':hashlib.sha256(response.content).hexdigest(),
        'asset_sha256':hashlib.sha256(asset.read_bytes()).hexdigest()})
    (OUT/'sources.json').write_text(json.dumps({'assets':records},indent=2)+'\n')
    print(json.dumps(records,indent=2))

if __name__ == '__main__': main()
