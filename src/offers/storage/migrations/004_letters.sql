-- Schema version 4: the cover letter of each offer (lot 5).
-- One letter per offer at most: generating it again replaces the row.
CREATE TABLE letters (
    id INTEGER PRIMARY KEY,
    offer_id INTEGER NOT NULL UNIQUE REFERENCES offers (id),
    path TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    created_at TEXT NOT NULL     -- ISO date and time
);
