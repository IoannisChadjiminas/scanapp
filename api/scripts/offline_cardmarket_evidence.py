"""Catalogue evidence adapter for already captured pages. Performs no requests.

This adapter cannot reserve or launch paid navigation, approve an identity,
interpret foil V-numbers, or infer card language from the website locale.
"""
import argparse
from datetime import datetime
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import urljoin, urlsplit, urlunsplit


def product_url(value):
    p=urlsplit(value)
    if p.scheme!='https' or p.hostname!='www.cardmarket.com' or p.username or p.password or p.port:
        return None
    if not re.fullmatch(r'/[a-z]{2}/Pokemon/Products/Singles/[^/]+/[^/]+',p.path):
        return None
    return urlunsplit((p.scheme,p.netloc,p.path,'',''))


class Page(HTMLParser):
    def __init__(self):
        super().__init__();self.canonicals=[];self.links=[];self.images=[];self.titles=[];self.ids=set()
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='link' and 'canonical' in a.get('rel','').split():self.canonicals.append(a.get('href',''))
        if tag=='a' and a.get('href'):self.links.append(a['href'])
        if tag=='meta' and a.get('property')=='og:image':self.images.append(a.get('content',''))
        if tag=='meta' and a.get('property')=='og:title':self.titles.append(a.get('content',''))
        if a.get('data-idproduct','').isdigit():self.ids.add(int(a['data-idproduct']))
        if a.get('name')=='idProduct' and a.get('value','').isdigit():self.ids.add(int(a['value']))


def capture(raw,source_url,fetched_at):
    if not fetched_at or not datetime.fromisoformat(fetched_at.replace('Z','+00:00')).tzinfo:
        raise ValueError('Timezone-qualified original capture time required')
    p=urlsplit(source_url)
    if p.scheme!='https' or p.hostname!='www.cardmarket.com' or p.username or p.password or p.port:
        raise ValueError('Expected public Cardmarket source URL')
    text=raw.decode('utf-8');page=Page();page.feed(text)
    expected=product_url(source_url)
    canonical={product_url(urljoin(source_url,u)) for u in page.canonicals}
    canonical.discard(None)
    blocked=any(marker in text.lower() for marker in ('cf-chl-', 'just a moment', 'access denied', 'too many requests'))
    issues=[]
    if blocked:issues.append('blocked_or_unavailable_capture')
    if len(canonical)>1:issues.append('conflicting_canonical_urls')
    if expected and canonical!={expected}:issues.append('canonical_missing_or_mismatch')
    if len(page.ids)>1:issues.append('conflicting_product_ids')
    listing_urls=sorted({u for href in page.links if (u:=product_url(urljoin(source_url,href)))})
    return dict(schema_version='offline-catalogue-evidence-v1',source_url=source_url,
        original_fetched_at=fetched_at,html_sha256=hashlib.sha256(raw).hexdigest(),
        canonical_urls=sorted(canonical),product_ids=sorted(page.ids),titles=page.titles,
        listing_urls=listing_urls,image_urls=page.images,image_bytes_verified=False,
        language=None,finish=None,identity_verified=False,live_access_verified=False,
        evidence_state='blocked_or_unavailable' if blocked else 'saved_page_candidate',
        issues=issues,paid_pages_used_by_adapter=0,paid_bytes_used_by_adapter=0)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--html',type=Path,required=True)
    p.add_argument('--source-url',required=True)
    p.add_argument('--original-fetched-at',required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();result=capture(a.html.read_bytes(),a.source_url,a.original_fetched_at)
    with a.output.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2)


if __name__=='__main__':main()
