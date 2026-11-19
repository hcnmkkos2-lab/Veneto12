DELETE FROM admin_sessions;

CREATE TABLE IF NOT EXISTS admin_otp_challenges (
    challenge_hash TEXT PRIMARY KEY,
    staff_user_id INTEGER NOT NULL REFERENCES staff_users(id) ON DELETE CASCADE,
    otp_hash TEXT NOT NULL,
    otp_salt TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts BETWEEN 0 AND 5),
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);