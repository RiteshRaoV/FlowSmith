CREATE TABLE IF NOT EXISTS fs_nodes (
    id            VARCHAR(36)     NOT NULL PRIMARY KEY DEFAULT (UUID()),
    flow_id       VARCHAR(255)    NOT NULL,
    step_name     VARCHAR(255)    NOT NULL,
    status        VARCHAR(50)     NOT NULL DEFAULT 'RUNNING',
    input_data    JSON,
    output_data   JSON,
    error         TEXT,
    attempt_count INT             NOT NULL DEFAULT 1,
    started_at    DATETIME(6),
    ended_at      DATETIME(6),

    CONSTRAINT fk_fs_nodes_flow
        FOREIGN KEY (flow_id) REFERENCES fs_flows(id)
        ON DELETE CASCADE,

    CONSTRAINT uq_fs_nodes_flow_step
        UNIQUE (flow_id, step_name)
);

-- Create indexes only if they don't already exist
DROP PROCEDURE IF EXISTS fs_create_indexes_nodes;

CREATE PROCEDURE fs_create_indexes_nodes()
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.statistics
        WHERE table_schema = DATABASE()
          AND table_name   = 'fs_nodes'
          AND index_name   = 'idx_fs_nodes_flow_id'
    ) THEN
        CREATE INDEX idx_fs_nodes_flow_id ON fs_nodes (flow_id);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.statistics
        WHERE table_schema = DATABASE()
          AND table_name   = 'fs_nodes'
          AND index_name   = 'idx_fs_nodes_status'
    ) THEN
        CREATE INDEX idx_fs_nodes_status ON fs_nodes (status);
    END IF;
END;

CALL fs_create_indexes_nodes();
DROP PROCEDURE IF EXISTS fs_create_indexes_nodes;