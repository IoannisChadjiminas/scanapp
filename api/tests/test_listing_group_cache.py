import sqlite3
from types import SimpleNamespace

import numpy as np
import pytest

from app.config import Settings
from app.db import init_catalog
from app.planetscale import CatalogueReadOnly, CloudCatalogConnection, protect_catalogue
from app.recognition.runtime import Runtime
import app.recognition.runtime as runtime_module


def catalogue(factory=sqlite3.Connection):
    conn = sqlite3.connect(':memory:', factory=factory)
    conn.row_factory = sqlite3.Row
    init_catalog(conn)
    conn.execute("INSERT INTO cardmarket_expansion_products(url,name,source,imported_at) VALUES (?,?,'test','test')",
                 ('https://www.cardmarket.com/en/Pokemon/Products/Singles/Scarlet-Violet/Fuecoco-V1-SVI036', 'Fuecoco'))
    conn.commit()
    return conn


def runtime():
    value = Runtime(Settings(_env_file=None))
    value.snapshot = SimpleNamespace(card_ids=np.array([], dtype=str))
    return value


def test_protected_snapshot_groups_built_once(monkeypatch):
    conn = catalogue(CloudCatalogConnection)
    protect_catalogue(conn)
    original = runtime_module.grouped_expansion_skus
    calls = []
    def counted(catalog):
        calls.append(catalog)
        return original(catalog)
    monkeypatch.setattr(runtime_module, 'grouped_expansion_skus', counted)
    value = runtime()
    value.bind_card_languages(conn)
    assert value.listing_groups(conn) == original(conn)
    assert value.listing_groups(conn) is value.listing_groups(conn)
    assert calls == [conn]
    with pytest.raises(CatalogueReadOnly):
        conn.execute('DELETE FROM cardmarket_expansion_products')
    conn.close()


def test_editable_catalogue_never_returns_stale_groups():
    conn = catalogue()
    value = runtime()
    value.bind_card_languages(conn)
    assert value.listing_groups(conn)
    conn.execute('DELETE FROM cardmarket_expansion_products')
    assert value.listing_groups(conn) == {}
    conn.rollback()
    assert value.listing_groups(conn)
    conn.close()


def test_rebind_drops_old_snapshot_and_connection_isolation():
    first = catalogue(CloudCatalogConnection)
    second = catalogue(CloudCatalogConnection)
    second.execute('DELETE FROM cardmarket_expansion_products')
    second.commit()
    protect_catalogue(first)
    protect_catalogue(second)
    value = runtime()
    value.bind_card_languages(first)
    assert value.listing_groups(first)
    assert value.listing_groups(second) == {}
    value.bind_card_languages(second)
    assert value.listing_groups(second) == {}
    assert value.listing_groups(first)
    first.close()
    second.close()
