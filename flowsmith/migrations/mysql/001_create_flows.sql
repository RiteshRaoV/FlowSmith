CREATE TABLE IF NOT EXISTS fs_flows (
    id          VARCHAR(255)    NOT NULL PRIMARY KEY,
    name        VARCHAR(255)    NOT NULL,
    status      VARCHAR(50)     NOT NULL DEFAULT 'RUNNING',
    input_data  JSON            NOT NULL,
    output_data JSON,
    error       TEXT,
    created_at  DATETIME(6)     NOT NULL DEFAULT NOW(6),
    updated_at  DATETIME(6)     NOT NULL DEFAULT NOW(6) ON UPDATE NOW(6)
);

-- Create indexes only if they don't already exist
-- (MySQL does not support CREATE INDEX IF NOT EXISTS)
DROP PROCEDURE IF EXISTS fs_create_indexes_flows;

CREATE PROCEDURE fs_create_indexes_flows()
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.statistics
        WHERE table_schema = DATABASE()
          AND table_name   = 'fs_flows'
          AND index_name   = 'idx_fs_flows_status'
    ) THEN
        CREATE INDEX idx_fs_flows_status ON fs_flows (status);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.statistics
        WHERE table_schema = DATABASE()
          AND table_name   = 'fs_flows'
          AND index_name   = 'idx_fs_flows_name'
    ) THEN
        CREATE INDEX idx_fs_flows_name ON fs_flows (name);
    END IF;
END;

CALL fs_create_indexes_flows();
DROP PROCEDURE IF EXISTS fs_create_indexes_flows;