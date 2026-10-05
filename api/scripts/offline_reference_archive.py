"""Parse saved PkmnCards set pages into source candidates, never approvals."""
from html.parser import HTMLParser
import re
from urllib.parse import urlparse


class SetArchiveParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.current = None
        self.cards = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'a':
            self.current = a if 'card-image-link' in a.get('class', '').split() else None
        if tag == 'img' and self.current and 'card-image' in a.get('class', '').split():
            page, image = self.current.get('href', ''), a.get('src', '')
            if any(urlparse(u).scheme != 'https' or urlparse(u).hostname != 'pkmncards.com'
                   for u in (page, image)):
                raise ValueError('Unexpected archive source host')
            title = self.current.get('title', '')
            match = re.fullmatch(r'(.+?) · (.+?) \(([^)]+)\) #([A-Za-z0-9]+|[!?])', title)
            if not match:
                raise ValueError('Unrecognized card title')
            self.cards.append(dict(name=match[1], set_name=match[2], set_code=match[3],
                collector_raw=match[4], source_page=page, image_url=image,
                source_kind='independent_catalogue_not_official',
                exact_print_approved=False, public_redistribution_approved=False,
                language=None, finish=None, stamp=None, title=title))

    def handle_endtag(self, tag):
        if tag == 'a':
            self.current = None


def parse_set(html, expected_set):
    p = SetArchiveParser()
    p.feed(html)
    if not p.cards or any(c['set_name'] != expected_set for c in p.cards):
        raise ValueError('Archive set scope mismatch or empty page')
    keys = [(c['name'], c['collector_raw']) for c in p.cards]
    if len(set(keys)) != len(keys):
        raise ValueError('Duplicate archive identity')
    return p.cards


def parse_single_article_archive(html, expected_page, expected_set):
    """Some one-card set archives render an article instead of a gallery.

    Require the observed archive canonical, explicit title description, actual
    permalink, and the same declared image in the rendered card image element.
    This returns a source proposal only; a deck circle is still visual evidence.
    """
    class Article(HTMLParser):
        def __init__(self):
            super().__init__()
            self.metadata = {}
            self.canonicals = []
            self.permalinks = []
            self.images = []

        def handle_starttag(self, tag, attrs):
            a = dict(attrs)
            if tag == 'meta' and a.get('property', '').startswith('og:'):
                key = a['property']
                if key in self.metadata and self.metadata[key] != a.get('content'):
                    raise ValueError('Conflicting article metadata')
                self.metadata[key] = a.get('content')
            if tag == 'link' and a.get('rel') == 'canonical':
                self.canonicals.append(a.get('href'))
            if tag == 'a' and a.get('title') == 'Permalink / Title':
                self.permalinks.append(a.get('href'))
            if tag == 'img' and 'card-image' in a.get('class', '').split():
                self.images.append(a.get('src'))

    p = Article(); p.feed(html)
    if p.canonicals != [expected_page] or p.metadata.get('og:url') != expected_page:
        raise ValueError('Article archive canonical mismatch')
    if len(set(p.permalinks)) != 1:
        raise ValueError('Article needs one explicit card permalink')
    page = p.permalinks[0]; image = p.metadata.get('og:image')
    for url in (expected_page, page, image):
        parsed = urlparse(url or '')
        if parsed.scheme != 'https' or parsed.hostname != 'pkmncards.com':
            raise ValueError('Unexpected article source host')
    if not urlparse(page).path.startswith('/card/') or image not in p.images:
        raise ValueError('Article permalink/image not rendered')
    match = re.fullmatch(r'(.+?) · (.+?) \(([^)]+)\) #([A-Za-z0-9]+|[!?])',
                         p.metadata.get('og:description', ''))
    if not match or match[2] != expected_set:
        raise ValueError('Article identity/set scope mismatch')
    return dict(name=match[1], set_name=match[2], set_code=match[3], collector_raw=match[4],
                source_page=page, image_url=image, archive_url=expected_page,
                source_kind='independent_catalogue_not_official',
                exact_print_approved=False, public_redistribution_approved=False,
                language=None, finish=None, stamp=None, title=match[0])
