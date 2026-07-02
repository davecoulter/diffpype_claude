-- Provision the isolated test database alongside the dev database.
-- This script runs once on a fresh Postgres data directory via
-- docker-entrypoint-initdb.d, so it is safe to run without IF NOT EXISTS.
CREATE DATABASE diffpype_test;
