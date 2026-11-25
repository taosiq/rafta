-- Least-privilege role for the AI assistant: it can SELECT and nothing else.
-- Runs once, when the Postgres volume is first initialised.
CREATE ROLE rafta_readonly LOGIN PASSWORD 'rafta_readonly';
GRANT CONNECT ON DATABASE rafta TO rafta_readonly;
GRANT USAGE ON SCHEMA public TO rafta_readonly;
-- Tables are created later by Alembic (as role "rafta"), so grant on future tables too.
ALTER DEFAULT PRIVILEGES FOR ROLE rafta IN SCHEMA public GRANT SELECT ON TABLES TO rafta_readonly;
ALTER ROLE rafta_readonly SET default_transaction_read_only = on;
ALTER ROLE rafta_readonly SET statement_timeout = '5s';
