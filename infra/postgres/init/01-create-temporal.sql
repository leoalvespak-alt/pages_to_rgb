DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'temporal') THEN
        CREATE ROLE temporal LOGIN PASSWORD 'temporal_dev';
    END IF;
END
$$;

SELECT 'CREATE DATABASE temporal OWNER temporal'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'temporal')\gexec
