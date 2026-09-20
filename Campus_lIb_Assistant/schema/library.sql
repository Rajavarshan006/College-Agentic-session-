-- events.db: business data. Queue and agent memory live in agent.db.
CREATE TABLE IF NOT EXISTS member (
    id INTEGER PRIMARY KEY,
    roll_no TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    dept TEXT NOT NULL,
    max_registrations INTEGER NOT NULL DEFAULT 3
);

CREATE TABLE IF NOT EXISTS event (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    venue TEXT NOT NULL,
    starts_at TEXT NOT NULL,
    seats_total INTEGER NOT NULL CHECK (seats_total > 0),
    seats_available INTEGER NOT NULL CHECK (seats_available >= 0),
    version INTEGER NOT NULL DEFAULT 0
);

-- Business rules are data, not prompt text.
CREATE TABLE IF NOT EXISTS policy (name TEXT PRIMARY KEY, value INTEGER NOT NULL);

CREATE TABLE IF NOT EXISTS registration (
    id INTEGER PRIMARY KEY,
    member_id INTEGER NOT NULL REFERENCES member(id),
    event_id INTEGER NOT NULL REFERENCES event(id),
    created_at REAL NOT NULL,
    UNIQUE(member_id, event_id)
);

CREATE TABLE IF NOT EXISTS notification (
    id INTEGER PRIMARY KEY,
    roll_no TEXT NOT NULL,
    message TEXT NOT NULL,
    dedupe_key TEXT NOT NULL UNIQUE,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS idempotency (
    key TEXT PRIMARY KEY,
    tool_name TEXT NOT NULL,
    result TEXT NOT NULL,
    created_at REAL NOT NULL
);
