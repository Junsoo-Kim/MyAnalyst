-- One database per service in the same PostgreSQL instance (MSA stage 6, decision D6).
-- Mounted into /docker-entrypoint-initdb.d, so it runs only when the data volume is created. For an existing volume
-- scripts/migrate/stage6_split_databases.sh creates the same databases (this file is idempotent) and copies the data.
-- Schemas are created by each service (Hibernate ddl-auto, Modulith event_publication).
SELECT format('CREATE DATABASE %I', db)
FROM unnest(ARRAY['user_db', 'report_db', 'generation_db', 'chat_db', 'dictionary_db']) AS db
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = db)
\gexec
