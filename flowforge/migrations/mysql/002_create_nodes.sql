CREATE TABLE IF NOT EXISTS ff_nodes (
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

    CONSTRAINT fk_ff_nodes_flow
        FOREIGN KEY (flow_id) REFERENCES ff_flows(id)
        ON DELETE CASCADE,

    CONSTRAINT uq_ff_nodes_flow_step
        UNIQUE (flow_id, step_name)
);

CREATE INDEX IF NOT EXISTS idx_ff_nodes_flow_id ON ff_nodes (flow_id);
CREATE INDEX IF NOT EXISTS idx_ff_nodes_status  ON ff_nodes (status);
