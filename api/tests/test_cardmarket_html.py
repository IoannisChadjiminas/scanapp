from app.cardmarket_html import parse_cardmarket_html

URL = (
    "https://www.cardmarket.com/en/Pokemon/Products/Singles/151/Bulbasaur-V1-MEW001"
)


def _page(body: str, title: str = "Bulbasaur") -> str:
    return (
        "<html><head><title>"
        + title
        + '</title><link rel="canonical" href="'
        + URL
        + '"></head><body>'
        + body
        + "</body></html>"
    )


def test_parses_visible_offer_rows():
    html = _page(
        """
        <div class="article-row">
          <span class="article-condition">NM English</span>
          <span data-bs-original-title="English"></span>
          <span title="Holo"></span>
          <div class="col-offer">2,50 € + shipping</div>
        </div>
        <div class="article-row" style="display: none">
          <span class="article-condition">EX</span>
          <div class="price-container">9,00 €</div>
        </div>
        <div class="article-row">
          <span class="badge">GD</span>
          <div class="col-offer">1,10 €</div>
        </div>
        """
    )
    parsed = parse_cardmarket_html(URL, html)
    assert parsed["blocked"] is False
    assert parsed["empty"] is False
    assert parsed["pending"] is False
    assert parsed["url"] == URL
    assert parsed["rows"] == [
        {"price": "2,50 €", "condition": "NM", "language": "English", "variant": "Holo"},
        {"price": "1,10 €", "condition": "GD", "language": "", "variant": ""},
    ]
    assert parsed["parser"] == "offers-html-v1"


def test_comment_and_quantity_counts_are_not_part_of_the_price():
    html = _page(
        """
        <div class="article-row">
          <span class="article-condition">NM</span>
          <span data-bs-original-title="English"></span>
          <div class="mobile-offer-container">
            <a class="comments"><span class="badge">1</span></a>
            <div class="price-container"><span>23,36 €</span></div>
            <span class="item-count">12</span>
          </div>
        </div>
        <div class="article-row">
          <span class="article-condition">NM</span>
          <div class="mobile-offer-container">
            <span class="comments">8</span><span>24,98 €</span>
          </div>
        </div>
        <div class="article-row">
          <span class="article-condition">NM</span>
          <div class="price-container d-none">99,00 €</div>
          <div class="mobile-offer-container">
            <span class="available">12</span><span>24,99 €</span>
          </div>
        </div>
        """
    )
    parsed = parse_cardmarket_html(URL, html)
    assert [row["price"] for row in parsed["rows"]] == ["23,36 €", "24,98 €", "24,99 €"]


def test_challenge_html_is_blocked_without_rows():
    html = _page(
        '<div id="challenge-form">Just a moment...</div>',
        title="Just a moment...",
    )
    parsed = parse_cardmarket_html(URL, html)
    assert parsed["blocked"] is True
    assert parsed["rows"] == []
    assert parsed["url"] == URL


def test_empty_listing_state():
    html = _page('<div class="no-articles">There are currently no articles.</div>')
    parsed = parse_cardmarket_html(URL, html)
    assert parsed["empty"] is True
    assert parsed["pending"] is False
    assert parsed["rows"] == []


def test_unloaded_table_stays_pending():
    parsed = parse_cardmarket_html(URL, _page("<div>Loading</div>"))
    assert parsed["pending"] is True
    assert parsed["rows"] == []


def test_professional_power_seller_is_kept_on_the_listing():
    html = _page(
        """
        <div class="article-row">
          <span class="article-condition">NM</span>
          <span data-bs-original-title="Professional"></span>
          <span class="fonticon-powerseller" data-bs-original-title="Power Seller"></span>
          <span data-bs-original-title="1.245 sales"></span>
          <div class="col-offer">2,50 €</div>
        </div>
        <div class="article-row">
          <span class="article-condition">EX</span>
          <span data-bs-original-title="Professional"></span>
          <div class="col-offer">3,00 €</div>
        </div>
        """
    )
    rows = parse_cardmarket_html(URL, html)["rows"]
    assert rows[0]["seller"] == "Professional Power Seller"
    assert rows[0]["sales"] == "1245"
    assert rows[1]["seller"] == "Professional"
    assert "sales" not in rows[1]


def test_available_count_comes_from_the_page_not_the_sample():
    rows = "\n".join(
        f'<div class="article-row"><div class="col-offer">{index},00 €</div></div>'
        for index in range(1, 8)
    )
    html = _page(
        rows
        + """
        <dl>
          <dt>Available items</dt><dd>14</dd>
          <dt>From</dt><dd>1,00 €</dd>
          <dt>Price Trend</dt><dd>2,50 €</dd>
        </dl>
        """
    )
    parsed = parse_cardmarket_html(URL, html)
    assert len(parsed["rows"]) == 7
    assert parsed["header"]["Available"] == 14
    assert parsed["header"]["From"] == 1
    assert parsed["header"]["Trend"] == 2.5


def test_desktop_row_keeps_sales_professional_and_daily_averages():
    html = _page(
        """
        <div id="articleRow2165455976" class="row g-0 article-row">
          <div class="col-seller">
            <span class="badge sell-count" data-bs-original-title="175&nbsp;Sales&nbsp;|&nbsp;204&nbsp;Available items">175</span>
            <span class="icon" data-bs-original-title="Item location: Italy"></span>
            <span class="fonticon-users-professional" data-bs-original-title="Professional"></span>
          </div>
          <a class="article-condition" data-bs-original-title="Near Mint"><span class="badge">NM</span></a>
          <span class="icon" data-bs-original-title="Italian"></span>
          <div class="price-container d-none d-md-flex"><span>0,95 €</span></div>
          <div class="mobile-offer-container d-flex d-md-none">
            <span class="item-count">2</span><span>0,95 €</span>
          </div>
        </div>
        <div class="tab-pane d-none" id="tabContent-chart">
          <script class="chart-init-script">
            var chart = new Chart(ctx,{"type":"line","data":{"labels":["23.09.2026","24.09.2026"],"datasets":[{"label":"Avg. Sell Price","data":[2.91,2.58]}]}});
          </script>
        </div>
        <script class="chart-init-script">
          var chart = new Chart(ctx,{"type":"line","data":{"labels":["23.09.2026","24.09.2026"],"datasets":[{"label":"Avg. Sell Price","data":[2.91,2.58]}]}});
        </script>
        """
    )
    parsed = parse_cardmarket_html(URL, html)
    assert parsed["rows"] == [
        {
            "price": "0,95 €",
            "condition": "NM",
            "language": "Italian",
            "variant": "",
            "sales": "175",
            "seller": "Professional",
            "country": "Italy",
        }
    ]
    assert parsed["chart"] == [
        {"date": "24.09.2026", "price": 2.58},
        {"date": "23.09.2026", "price": 2.91},
    ]


def test_canonical_for_another_product_is_not_this_page():
    other = (
        "https://www.cardmarket.com/en/Pokemon/Products/Singles/"
        "151/Ivysaur-V1-MEW002"
    )
    html = (
        '<html><head><link rel="canonical" href="'
        + other
        + '"></head><body>'
        '<div class="article-row"><div class="col-offer">3,00 €</div></div>'
        "</body></html>"
    )
    parsed = parse_cardmarket_html(URL, html)
    assert parsed["url"] == other
    assert parsed["rows"] == []
