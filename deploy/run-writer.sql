-- Execute as schema owner after migrations/001_runs.sql, using psql variables:
--   -v run_schema=run_store -v writer_role=mini_nota_run_writer
--   -v catalog_role=mini_nota_catalog_reader
-- Provision roles/logins separately; passwords must never appear in this file.
REVOKE ALL ON SCHEMA :"run_schema" FROM PUBLIC, :"catalog_role";
GRANT USAGE ON SCHEMA :"run_schema" TO :"writer_role";
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA :"run_schema" TO :"writer_role";
REVOKE ALL ON ALL TABLES IN SCHEMA :"run_schema" FROM PUBLIC, :"catalog_role";
ALTER DEFAULT PRIVILEGES IN SCHEMA :"run_schema" REVOKE ALL ON TABLES FROM PUBLIC, :"catalog_role";
