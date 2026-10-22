-- Schema version 1. Later changes go in new migrations (database.MIGRATIONS).

-- Offers, written by the pipeline only.
CREATE TABLE offers (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    reference TEXT NOT NULL,
    title TEXT NOT NULL,
    company TEXT,
    country TEXT,
    city TEXT,
    contract_type TEXT,
    duration_months INTEGER,
    published_on TEXT,           -- ISO date
    url TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    candidate_profile TEXT NOT NULL DEFAULT '',
    search_name TEXT,            -- first search that found the offer
    raw TEXT NOT NULL DEFAULT '{}',  -- JSON
    first_seen TEXT NOT NULL,    -- ISO date and time
    last_seen TEXT NOT NULL,
    online INTEGER NOT NULL DEFAULT 1 CHECK (online IN (0, 1)),
    UNIQUE (source, source_id),
    UNIQUE (source, reference)
);

-- User's follow-up, written only from what the user entered.
CREATE TABLE tracking (
    offer_id INTEGER PRIMARY KEY REFERENCES offers (id),
    status TEXT,
    applied_on TEXT,
    notes TEXT,
    updated_at TEXT NOT NULL
);

-- One evaluation per offer and method, replaced at each computation.
CREATE TABLE evaluations (
    id INTEGER PRIMARY KEY,
    offer_id INTEGER NOT NULL REFERENCES offers (id),
    method TEXT NOT NULL CHECK (method IN ('keywords', 'claude')),
    score INTEGER,
    justification TEXT,
    prompt_version TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (offer_id, method)
);

-- One row per source and per run.
CREATE TABLE runs (
    id INTEGER PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    source TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('ok', 'error')),
    found INTEGER,
    added INTEGER,
    removed INTEGER,
    error TEXT
);
