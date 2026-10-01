"""Validated cloud snapshot, cached in RAM; operational SQLite remains separate."""
from __future__ import annotations

import hashlib
import re
import sqlite3
import threading
from urllib.parse import urlsplit

import numpy as np

from app.config import Settings
from app.recognition.artifacts import ArtifactError, ArtifactSnapshot, sha256_file, validate_embeddings


class CatalogueReadOnly(RuntimeError):
    pass


class CloudCatalogCursor(sqlite3.Cursor):
    def __del__(self):
        # sqlite3 finalizes a cursor's last prepared statement during GC.
        # Close under the same lock before its C destructor runs; otherwise
        # even an apparently harmless temporary SELECT cursor can invert locks.
        try:
            self.close()
        except (sqlite3.Error, AttributeError):
            pass

    def _run(self, method, *args, **kwargs):
        # SQLite invokes the Python authorizer while holding its mutex. All
        # entry points must acquire this Python lock first, avoiding a GIL /
        # SQLite mutex inversion between API and recognition worker threads.
        with self.connection._cache_lock:
            try:
                return method(*args, **kwargs)
            except sqlite3.DatabaseError as exc:
                if getattr(exc, "sqlite_errorcode", None) == sqlite3.SQLITE_AUTH or "cannot modify" in str(exc):
                    raise CatalogueReadOnly("Catalogue is read-only; publish reviewed mapping changes separately.") from None
                raise

    def execute(self, *args, **kwargs):
        return self._run(super().execute, *args, **kwargs)

    def executemany(self, *args, **kwargs):
        return self._run(super().executemany, *args, **kwargs)

    def executescript(self, *args, **kwargs):
        return self._run(super().executescript, *args, **kwargs)

    def fetchone(self):
        return self._run(super().fetchone)

    def fetchall(self):
        return self._run(super().fetchall)

    def fetchmany(self, *args, **kwargs):
        return self._run(super().fetchmany, *args, **kwargs)

    def __next__(self):
        return self._run(super().__next__)

    def close(self):
        return self._run(super().close)


class CloudCatalogConnection(sqlite3.Connection):
    catalogue_readonly = True

    def __init__(self, *args, **kwargs):
        self._cache_lock = threading.RLock()
        super().__init__(*args, **kwargs)

    def cursor(self, factory=CloudCatalogCursor):
        # Custom factories could silently bypass serialization.
        if not issubclass(factory, CloudCatalogCursor):
            raise TypeError("Cloud catalogue cursors must be serialized")
        with self._cache_lock:
            return super().cursor(factory)

    def execute(self, *args, **kwargs):
        return self.cursor().execute(*args, **kwargs)

    def executemany(self, *args, **kwargs):
        return self.cursor().executemany(*args, **kwargs)

    def executescript(self, *args, **kwargs):
        return self.cursor().executescript(*args, **kwargs)

    def commit(self):
        with self._cache_lock:
            return super().commit()

    def rollback(self):
        with self._cache_lock:
            return super().rollback()

    def close(self):
        with self._cache_lock:
            return super().close()


def protect_catalogue(conn: sqlite3.Connection) -> None:
    writes = {sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE, sqlite3.SQLITE_DROP_TABLE, sqlite3.SQLITE_DROP_VIEW}
    protected = {"cards", "cards_fts", "cardmarket_expansion_products"}

    def authorize(action, table, column, database, trigger):
        if action in writes and table in protected:
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    conn.set_authorizer(authorize)


def _field_token(value) -> str:
    return "N" if value is None else "V" + str(value).encode().hex()


def load_cloud_catalogue(settings: Settings, local: sqlite3.Connection) -> ArtifactSnapshot:
    # Imports are lazy: the default SQLite path has no new connection behavior.
    import certifi
    import psycopg

    schema = settings.planetscale_schema
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", schema):
        raise ArtifactError("Invalid PlanetScale schema setting")
    url = settings.planetscale_database_url.get_secret_value()
    try:
        parts = urlsplit(url)
        if parts.scheme not in {"postgres", "postgresql"} or not parts.hostname or not parts.hostname.endswith(".psdb.cloud"):
            raise ArtifactError("A PlanetScale PostgreSQL connection URL is required")
        pg = psycopg.connect(url, port=6432, sslmode="verify-full", sslrootcert=certifi.where(), connect_timeout=15, autocommit=True, prepare_threshold=None, application_name="scanapp-staging-catalogue")
        with pg, pg.transaction():
            pg.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            pg.execute("SET LOCAL statement_timeout='50s'")
            pg.execute("SET LOCAL lock_timeout='5s'")
            if not pg.pgconn.ssl_in_use:
                raise ArtifactError("PlanetScale TLS is required")
            can_write = pg.execute("SELECT pg_has_role(current_user,'pg_write_all_data','USAGE') OR pg_has_role(current_user,'postgres','USAGE')").fetchone()[0]
            if can_write:
                raise ArtifactError("Use a dedicated read-only PlanetScale role, not the import/admin role")
            record = pg.execute(f"SELECT status,metadata FROM {schema}.import_manifest WHERE import_id=%s", (settings.planetscale_import_id,)).fetchone()
            if not record or record[0] != "validated":
                raise ArtifactError("PlanetScale import is not validated")
            metadata = record[1]
            if metadata["target"]["schema"] != schema:
                raise ArtifactError("PlanetScale import target mismatch")
            manifest_row = pg.execute(f"SELECT metadata FROM {schema}.reference_metadata WHERE source_key=%s", ("vector-manifest:"+settings.preprocess_config,)).fetchone()
            if not manifest_row:
                raise ArtifactError("PlanetScale vector manifest is missing")
            manifest = manifest_row[0]
            if manifest["preprocess_config"] != settings.preprocess_config or manifest["embedding_dim"] != 384:
                raise ArtifactError("PlanetScale preprocessing/dimension mismatch")
            if not settings.dinov2_path.is_file() or sha256_file(settings.dinov2_path) != manifest["dinov2_sha256"]:
                raise ArtifactError("Local DINOv2 model does not match PlanetScale snapshot")
            models = pg.execute(f"SELECT metadata FROM {schema}.reference_metadata WHERE source_key='models'").fetchone()[0]["sha256"]
            if settings.use_ocr:
                for name in ("PP-OCRv6_det_small.onnx", "PP-OCRv6_rec_small.onnx", "ch_ppocr_mobile_v2.0_cls_mobile.onnx"):
                    path = settings.models_dir / name
                    if not path.is_file() or sha256_file(path) != models[name]:
                        raise ArtifactError("Local OCR model does not match PlanetScale model metadata")
            local.commit()
            local.execute("ATTACH DATABASE ':memory:' AS cloud")
            for target, source in (("cards", "cards"), ("cardmarket_expansion_products", "cardmarket_products")):
                digest = metadata["digests"][source]
                columns = digest["columns"]
                names = ",".join(columns)
                local.execute(f"CREATE TABLE cloud.{target} AS SELECT {names} FROM main.{target} WHERE 0")
                row_hashes = []
                with pg.cursor(name="cloud_"+source) as cursor:
                    cursor.execute(f"SELECT {names} FROM {schema}.{source} ORDER BY {digest['keys'][0]} COLLATE \"C\"")
                    while rows := cursor.fetchmany(1000):
                        local.executemany(f"INSERT INTO cloud.{target}({names}) VALUES ({','.join('?' for _ in columns)})", rows)
                        row_hashes.extend(hashlib.md5("|".join(_field_token(v) for v in row).encode()).hexdigest() for row in rows)
                if len(row_hashes) != metadata["counts"][source] or hashlib.md5("".join(row_hashes).encode()).hexdigest() != digest["md5"]:
                    raise ArtifactError("PlanetScale catalogue checksum mismatch")
            local.execute("CREATE UNIQUE INDEX cloud.cards_id ON cards(id)")
            local.execute("CREATE INDEX cloud.cards_language ON cards(language)")
            local.execute("CREATE INDEX cloud.cards_url ON cards(cardmarket_url)")
            local.execute("CREATE INDEX cloud.products_card ON cardmarket_expansion_products(card_id)")
            local.execute("CREATE INDEX cloud.products_url ON cardmarket_expansion_products(url)")
            local.execute("CREATE TEMP VIEW cards AS SELECT * FROM cloud.cards")
            local.execute("CREATE TEMP VIEW cardmarket_expansion_products AS SELECT * FROM cloud.cardmarket_expansion_products")
            local.execute("CREATE VIRTUAL TABLE temp.cards_fts USING fts5(name,set_name,collector_number,id UNINDEXED)")
            local.execute("INSERT INTO temp.cards_fts SELECT name,set_name,collector_number,id FROM cloud.cards")
            ids = [str(cid) for cid in manifest["indexed_ids"]]
            stats = metadata["vectors"][settings.preprocess_config]
            if len(ids) != len(set(ids)) or len(ids) != stats["count"]:
                raise ArtifactError("PlanetScale vector IDs mismatch")
            positions = {cid:i for i,cid in enumerate(ids)}
            embeddings = np.empty((len(ids),384), dtype=np.float32)
            hashes = {}
            with pg.cursor(name="cloud_vectors") as cursor:
                cursor.execute(f"SELECT card_id,snapshot_id,source_vector_sha256,public.vector_send(embedding) FROM {schema}.card_embeddings WHERE mode=%s", (settings.preprocess_config,))
                while rows := cursor.fetchmany(1000):
                    for cid, snapshot, claimed, binary in rows:
                        raw = bytes(binary)
                        actual = hashlib.sha256(raw[4:]).hexdigest()
                        if cid not in positions or cid in hashes or snapshot != stats["snapshot"] or len(raw) != 1540 or raw[:4] != b'\x01\x80\x00\x00' or claimed != actual:
                            raise ArtifactError("PlanetScale vector checksum/identity mismatch")
                        embeddings[positions[cid]] = np.frombuffer(raw[4:], dtype=">f4")
                        hashes[cid] = actual
            aggregate = hashlib.md5("".join(hashes[cid] for cid in sorted(hashes,key=lambda c:c.encode())).encode()).hexdigest()
            if set(hashes) != set(ids) or aggregate != stats["aggregate_md5"]:
                raise ArtifactError("PlanetScale vector aggregate mismatch")
            card_ids = np.array(ids)
            validate_embeddings(embeddings, card_ids)
            present = {row[0] for row in local.execute("SELECT id FROM cloud.cards")}
            if not set(ids) <= present:
                raise ArtifactError("PlanetScale vectors reference missing cards")
            embeddings.flags.writeable = False
            card_ids.flags.writeable = False
            local.commit()
            protect_catalogue(local)
            return ArtifactSnapshot(preprocess_config=settings.preprocess_config, use_ocr=settings.use_ocr, catalogue_version=str(manifest["catalogue_version"]), model_revision=str(manifest["model_revision"]), model_name=str(manifest["model_name"]), embedding_dim=384, card_count=int(manifest["card_count"]), indexed_count=len(ids), missing_images=int(manifest["missing_images"]), embeddings_sha256=str(manifest["embeddings_sha256"]), ids_sha256=str(manifest["ids_sha256"]), embeddings=embeddings, card_ids=card_ids, manifest=manifest, bundle_dir=settings.vectors_dir)
    except ArtifactError:
        raise
    except Exception:
        # Driver exceptions can contain connection secrets. Never emit their text.
        raise ArtifactError("PlanetScale snapshot unavailable; local catalogue fallback is disabled") from None
