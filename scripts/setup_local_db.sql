-- One-time setup of the local PostgreSQL for the HR Recruiter Platform.
-- Safe to run again: every step checks whether it is already done.
--
--   sudo -u postgres psql < scripts/setup_local_db.sql
--
-- (Feed it on stdin: the postgres OS user cannot read files in your home folder.)
-- Override any value with -v, e.g.  sudo -u postgres psql -v app_pw=secret < ...
--
-- Two roles, on purpose:
--   hr_owner  owns the schema and runs migrations. The app never connects as it.
--   hr_app    the runtime role: DML only, not the table owner, no BYPASSRLS,
--             so Row-Level Security applies to every query the app makes.
-- hr_owner is a member of hr_app so the test suite can `SET ROLE hr_app`.

\set ON_ERROR_STOP on

\if :{?db}       \else \set db       hr_platform \endif
\if :{?owner}    \else \set owner    hr_owner    \endif
\if :{?owner_pw} \else \set owner_pw hr_owner_dev \endif
\if :{?app}      \else \set app      hr_app      \endif
\if :{?app_pw}   \else \set app_pw   hr_app_dev  \endif

SELECT format('CREATE ROLE %I LOGIN CREATEDB NOSUPERUSER NOBYPASSRLS PASSWORD %L', :'owner', :'owner_pw')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'owner') \gexec

SELECT format('CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD %L', :'app', :'app_pw')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app') \gexec

SELECT format('GRANT %I TO %I', :'app', :'owner')
WHERE NOT EXISTS (
  SELECT 1 FROM pg_auth_members m
  JOIN pg_roles r ON r.oid = m.roleid AND r.rolname = :'app'
  JOIN pg_roles u ON u.oid = m.member AND u.rolname = :'owner'
) \gexec

SELECT format('CREATE DATABASE %I OWNER %I', :'db', :'owner')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'db') \gexec

-- pgvector is needed from phase 2 (resume embeddings). Installed with
--   sudo apt install postgresql-16-pgvector
-- It is added to template1 too, so test databases get it. Skipped if not installed.
\connect :db
SELECT 'CREATE EXTENSION IF NOT EXISTS vector' FROM pg_available_extensions WHERE name = 'vector' \gexec
\connect template1
SELECT 'CREATE EXTENSION IF NOT EXISTS vector' FROM pg_available_extensions WHERE name = 'vector' \gexec

\echo
SELECT rolname, rolsuper, rolbypassrls, rolcreatedb FROM pg_roles WHERE rolname IN (:'owner', :'app') ORDER BY 1;
SELECT CASE WHEN EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'vector')
            THEN 'pgvector: installed'
            ELSE 'pgvector: not installed yet (needed from phase 2)' END AS note;
