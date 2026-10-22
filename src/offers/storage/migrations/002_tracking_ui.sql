-- Schema version 2: what the interface records for each offer (lot 3).

ALTER TABLE tracking ADD COLUMN letter_status TEXT
    CHECK (letter_status IN ('to_write', 'written'));
ALTER TABLE tracking ADD COLUMN favorite INTEGER NOT NULL DEFAULT 0
    CHECK (favorite IN (0, 1));
ALTER TABLE tracking ADD COLUMN read_at TEXT;  -- ISO date and time, NULL = not read
-- Trash: the offer is hidden, never deleted.
ALTER TABLE tracking ADD COLUMN hidden INTEGER NOT NULL DEFAULT 0
    CHECK (hidden IN (0, 1));

-- The letter is no longer a status.
UPDATE tracking SET letter_status = 'to_write', status = 'interesting'
    WHERE status = 'to_write';
UPDATE tracking SET letter_status = 'written', status = 'interesting'
    WHERE status = 'letter_ready';
