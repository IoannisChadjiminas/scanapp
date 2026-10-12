-- PlanetScale Postgres, database pokesingle-product. Prepared, NOT applied.
--
-- Adds the time each install last synced its holdings, so the nightly price
-- job can skip installs that stopped syncing (DAILY_INSTALL_MAX_AGE_DAYS,
-- default 30). Safe to run while the API is live: the API checks for the
-- column and keeps every holding until it exists.
--
-- Existing rows get the time of this migration, so nothing is dropped on the
-- first night. Each later sync (replace_portfolio) refreshes it.
--
-- Run as a role that can alter portfolio_products (the API's own role is
-- read/insert only on purpose).

ALTER TABLE portfolio_products
    ADD COLUMN IF NOT EXISTS synced_at timestamptz NOT NULL DEFAULT now();

CREATE INDEX IF NOT EXISTS portfolio_products_synced_idx
    ON portfolio_products (synced_at);

-- Rollback (the API goes back to keeping every holding):
-- DROP INDEX IF EXISTS portfolio_products_synced_idx;
-- ALTER TABLE portfolio_products DROP COLUMN IF EXISTS synced_at;
