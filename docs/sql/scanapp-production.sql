-- Prepared for review; NOT applied. Scanner tables in pokesingle-product-prod only.
-- Use a pre-existing dedicated user-defined runtime role without broad data roles.
-- Connect with a private libpq service definition, not a URL in shell arguments.
-- PGSERVICE=scanapp-production-admin psql -v ON_ERROR_STOP=1 -v scanapp_role=<name> -f docs/sql/scanapp-production.sql
\set ON_ERROR_STOP on
\if :{?scanapp_role}
\else
  \echo 'Missing scanapp_role variable; no changes applied.'
  \quit 2
\endif
BEGIN;
DO $$ BEGIN
  IF current_database() <> 'pokesingle-product-prod' THEN
    RAISE EXCEPTION 'Wrong database for ScanApp production schema';
  END IF;
END $$;
SELECT set_config('scanapp.production_role', :'scanapp_role', true);
DO $$
DECLARE target_role record; relation record;
BEGIN
  SELECT oid, rolsuper, rolbypassrls INTO target_role FROM pg_roles
    WHERE rolname = current_setting('scanapp.production_role');
  IF NOT FOUND THEN RAISE EXCEPTION 'Create the dedicated ScanApp runtime role first'; END IF;
  IF target_role.rolsuper OR target_role.rolbypassrls
     OR pg_has_role(target_role.oid, 'pg_read_all_data', 'MEMBER')
     OR pg_has_role(target_role.oid, 'pg_write_all_data', 'MEMBER')
     OR has_schema_privilege(target_role.oid, 'public', 'CREATE') THEN
    RAISE EXCEPTION 'Runtime role has broad privileges; provision a restricted role';
  END IF;
  FOR relation IN SELECT c.oid FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
    WHERE n.nspname='public' AND c.relname IN ('user', 'session', 'account', 'verification')
  LOOP
    IF has_table_privilege(target_role.oid, relation.oid, 'SELECT,INSERT,UPDATE,DELETE') THEN
      RAISE EXCEPTION 'Runtime role can access auth tables; provision a restricted role';
    END IF;
  END LOOP;
END $$;
SET LOCAL search_path TO public;

CREATE TABLE IF NOT EXISTS portfolio_products (
    session_id text NOT NULL,
    sample_key text NOT NULL,
    opened_at timestamptz NOT NULL,
    PRIMARY KEY (session_id, sample_key)
);
CREATE INDEX IF NOT EXISTS portfolio_products_opened_idx
    ON portfolio_products (opened_at);

ALTER TABLE portfolio_products ADD COLUMN IF NOT EXISTS synced_at timestamptz NOT NULL DEFAULT now();
CREATE INDEX IF NOT EXISTS portfolio_products_synced_idx ON portfolio_products (synced_at);
CREATE TABLE IF NOT EXISTS price_guide_import_days (
        day TEXT PRIMARY KEY
    );
CREATE TABLE IF NOT EXISTS price_history_daily (
        id_product INTEGER NOT NULL,
        day TEXT NOT NULL,
        avg DOUBLE PRECISION, low DOUBLE PRECISION, trend DOUBLE PRECISION,
        avg1 DOUBLE PRECISION, avg7 DOUBLE PRECISION, avg30 DOUBLE PRECISION,
        avg_holo DOUBLE PRECISION, low_holo DOUBLE PRECISION, trend_holo DOUBLE PRECISION,
        avg1_holo DOUBLE PRECISION, avg7_holo DOUBLE PRECISION, avg30_holo DOUBLE PRECISION,
        PRIMARY KEY (id_product, day)
    );
CREATE INDEX IF NOT EXISTS price_history_day ON price_history_daily(day, id_product);
CREATE TABLE IF NOT EXISTS price_sales_daily (
        product_url TEXT NOT NULL,
        day TEXT NOT NULL,
        price DOUBLE PRECISION NOT NULL,
        PRIMARY KEY (product_url, day)
    );
GRANT USAGE ON SCHEMA public TO :"scanapp_role";
GRANT SELECT, INSERT, DELETE ON public.portfolio_products TO :"scanapp_role";
GRANT SELECT, INSERT, UPDATE ON
    public.price_guide_import_days,
    public.price_history_daily, public.price_sales_daily TO :"scanapp_role";
COMMIT;
-- No grants to auth/user tables, no CREATE grant, and no password is stored here.
-- Do not give this role pg_read_all_data, pg_write_all_data, or migration privileges.
