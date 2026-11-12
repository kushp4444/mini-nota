-- PRE-MIGRATION immutable catalog role; new Neon result-write roles need explicit migration.
-- Run as the release database owner after explicit immutable imports.
-- Supply -v database_name=mini_nota -v schema_name=public to psql.
-- Provider-managed login/password/TLS settings belong in its secret manager.
BEGIN;
CREATE ROLE mini_nota_catalog_reader NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
GRANT CONNECT ON DATABASE :"database_name" TO mini_nota_catalog_reader;
GRANT USAGE ON SCHEMA :"schema_name" TO mini_nota_catalog_reader;
GRANT SELECT ON TABLE :"schema_name".patient_catalog, :"schema_name".catalog_metadata,
  :"schema_name".model_metadata, :"schema_name".model_evaluation TO mini_nota_catalog_reader;
ALTER ROLE mini_nota_catalog_reader SET default_transaction_read_only = on;
COMMIT;
-- Grant this role to the separate serving login. Do not grant owner/admin roles,
-- CREATE on a shared schema, sequence access, or future-table write defaults.
