from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from offline_reference_archive import parse_single_article_archive

PAGE = 'https://pkmncards.com/set/observed-deck/'
SET = 'Observed Deck'
HTML = f'''<link rel="canonical" href="{PAGE}">
<meta property="og:url" content="{PAGE}">
<meta property="og:description" content="Raichu · {SET} (TK4R) #19">
<meta property="og:image" content="https://pkmncards.com/wp-content/uploads/observed.jpg">
<a title="Permalink / Title" href="https://pkmncards.com/card/observed-card/"></a>
<img class="card-image" src="https://pkmncards.com/wp-content/uploads/observed.jpg">'''


def test_single_article_is_only_an_observed_candidate():
    record = parse_single_article_archive(HTML, PAGE, SET)
    assert record['collector_raw'] == '19' and record['name'] == 'Raichu'
    assert record['source_page'] == 'https://pkmncards.com/card/observed-card/'
    assert record['exact_print_approved'] is False and record['stamp'] is None


@pytest.mark.parametrize('bad', [
    HTML.replace('rel="canonical"', 'rel="alternate"'),
    HTML.replace('class="card-image"', 'class="thumbnail"'),
    HTML.replace('title="Permalink / Title"', 'title="Unverified"'),
    HTML.replace('Observed Deck (TK4R)', 'Other Deck (TK4R)'),
    HTML.replace('pkmncards.com/card/', 'pkmncards.com.evil.invalid/card/'),
    HTML + '<meta property="og:image" content="https://pkmncards.com/wrong.jpg">',
    HTML.replace('#19', '#19/30'),
])
def test_incomplete_conflicting_or_unrecognized_articles_are_held(bad):
    with pytest.raises(ValueError):
        parse_single_article_archive(bad, PAGE, SET)
