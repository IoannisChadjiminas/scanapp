from pathlib import Path

import pytest

from app.config import Settings
from app.db import connect, init_catalog
from app.planetscale import CloudCatalogConnection, CatalogueReadOnly, load_cloud_catalogue, protect_catalogue
from app.recognition.artifacts import ArtifactError


def test_cloud_secret_not_in_settings_repr():
    settings = Settings(planetscale_database_url="postgresql://user:very-secret@host.psdb.cloud/postgres")
    assert "very-secret" not in repr(settings)


def test_invalid_cloud_url_does_not_fall_back(tmp_path):
    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    with pytest.raises(ArtifactError, match="connection URL"):
        load_cloud_catalogue(Settings(data_dir=tmp_path, catalogue_backend="planetscale", planetscale_database_url="postgresql://user:secret@example.com/postgres"), conn)


def _cache(tmp_path):
    conn = connect(tmp_path / "catalog.sqlite", factory=CloudCatalogConnection)
    init_catalog(conn)
    conn.commit()
    conn.execute("ATTACH DATABASE ':memory:' AS cloud")
    conn.execute("CREATE TABLE cloud.cards AS SELECT * FROM main.cards WHERE 0")
    conn.execute("INSERT INTO cloud.cards(id,name,set_name,collector_number,language) VALUES ('new','Pikachu','Base','25','en')")
    conn.execute("CREATE TEMP VIEW cards AS SELECT * FROM cloud.cards")
    conn.execute("CREATE VIRTUAL TABLE temp.cards_fts USING fts5(name,set_name,collector_number,id UNINDEXED)")
    conn.execute("INSERT INTO temp.cards_fts SELECT name,set_name,collector_number,id FROM cloud.cards")
    conn.commit()
    protect_catalogue(conn)
    return conn


def test_cache_reads_cloud_not_disk_and_fts_works(tmp_path):
    conn = _cache(tmp_path)
    assert conn.execute("SELECT count(*) FROM main.cards").fetchone()[0] == 0
    assert conn.execute("SELECT id FROM cards").fetchone()[0] == "new"
    assert conn.execute("SELECT cards.id FROM cards_fts JOIN cards ON cards.id=cards_fts.id WHERE cards_fts MATCH ?",("Pika*",)).fetchone()[0] == "new"


@pytest.mark.parametrize("query", ["UPDATE cards SET name='wrong'", "DELETE FROM main.cards", "DELETE FROM cloud.cards", "DROP VIEW cards"])
def test_catalogue_cache_cannot_be_mutated(tmp_path, query):
    conn = _cache(tmp_path)
    with pytest.raises(CatalogueReadOnly):
        conn.execute(query)
    assert conn.execute("SELECT name FROM cards").fetchone()[0] == "Pikachu"


def test_operational_price_writes_still_persist(tmp_path):
    conn = _cache(tmp_path)
    conn.execute("INSERT INTO cardmarket_snapshots(sample_key,url,prices_json,fetched_at) VALUES ('key','url','[]','now')")
    conn.commit()
    conn.close()
    original = connect(tmp_path / "catalog.sqlite")
    assert original.execute("SELECT fetched_at FROM cardmarket_snapshots WHERE sample_key='key'").fetchone()[0] == "now"
