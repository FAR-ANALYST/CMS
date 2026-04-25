-- ══════════════════════════════════════════════════════════════════
-- Get My Coach Uganda — Supabase Postgres schema
-- Run this in: Supabase Dashboard → SQL Editor → New Query
-- ══════════════════════════════════════════════════════════════════

-- Clean rebuild (uncomment if redeploying)
-- DROP TABLE IF EXISTS event_images CASCADE;
-- DROP TABLE IF EXISTS events       CASCADE;
-- DROP TABLE IF EXISTS coaches      CASCADE;
-- DROP TABLE IF EXISTS users        CASCADE;

-- ── USERS (auth) ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id          SERIAL PRIMARY KEY,
    username    TEXT NOT NULL,
    email       TEXT UNIQUE NOT NULL,
    password    TEXT NOT NULL,
    role        TEXT NOT NULL DEFAULT 'student'
                CHECK (role IN ('student','coach','admin')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── COACH PROFILES ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS coaches (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER REFERENCES users(id) ON DELETE CASCADE,
    full_name       TEXT,
    phone           TEXT,
    category        TEXT,
    location        TEXT,
    bio             TEXT,
    image_url       TEXT,
    is_verified     BOOLEAN NOT NULL DEFAULT FALSE,
    payment_status  TEXT NOT NULL DEFAULT 'pending',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_coaches_verified ON coaches(is_verified);
CREATE INDEX IF NOT EXISTS idx_coaches_category ON coaches(category);
CREATE INDEX IF NOT EXISTS idx_coaches_location ON coaches(location);

-- ── EVENTS ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS events (
    id           SERIAL PRIMARY KEY,
    title        TEXT NOT NULL,
    description  TEXT,
    location     TEXT,
    event_date   DATE,
    is_active    BOOLEAN NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS event_images (
    id        SERIAL PRIMARY KEY,
    event_id  INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    image_url TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_event_images_event ON event_images(event_id);

-- ══════════════════════════════════════════════════════════════════
-- SEED THE FIRST ADMIN
-- After running once, log in with these credentials and change the password.
-- Default password below is "admin123" (werkzeug pbkdf2:sha256 hash).
-- Email: admin@getmycoach.ug
-- ══════════════════════════════════════════════════════════════════
INSERT INTO users (username, email, password, role)
VALUES (
    'admin',
    'admin@getmycoach.ug',
    'pbkdf2:sha256:600000$Vh6mB7k3$9b1c6f7e0d2a4b8f5c9e2d7a3b6f1e8d4c5a9b0e7f3d2c1b8a5e4d7c6b9a8f3e',
    'admin'
)
ON CONFLICT (email) DO NOTHING;

-- ──────────────────────────────────────────────────────────────────
-- ⚠️  IMPORTANT: the hash above is a placeholder. Generate your own:
--   python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('YOUR_PASSWORD'))"
-- Then either:
--   UPDATE users SET password = '<paste-hash-here>' WHERE email='admin@getmycoach.ug';
-- Or sign up a normal account, then promote it:
--   UPDATE users SET role='admin' WHERE email='you@example.com';
-- ──────────────────────────────────────────────────────────────────

-- ══════════════════════════════════════════════════════════════════
-- SUPABASE STORAGE BUCKET
-- In Supabase Dashboard → Storage → New bucket:
--   Name:   uploads
--   Public: YES (toggle on)
-- That's it. The app uploads files via the REST API using SUPABASE_ANON_KEY.
-- ══════════════════════════════════════════════════════════════════
