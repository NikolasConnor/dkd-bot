CREATE TABLE subjects (
    id SERIAL PRIMARY KEY,
    user_id BIGINT UNIQUE,
    username TEXT UNIQUE,
    full_name TEXT NOT NULL,       -- ФИО
    is_citizen BOOLEAN DEFAULT FALSE,
    reputation INTEGER DEFAULT 0,
    joined_at TIMESTAMP DEFAULT NOW()
);
CREATE TABLE roles (
    id SERIAL PRIMARY KEY,
    code TEXT UNIQUE,              -- president / premier / cbank / etc.
    name TEXT NOT NULL,            -- «Президент»
    emoji TEXT DEFAULT '👤',
    description TEXT DEFAULT '',
    max_holders INTEGER DEFAULT 1, -- 1 = только один, NULL = сколько угодно
    is_default BOOLEAN DEFAULT FALSE
);
CREATE TABLE subject_roles (
    id SERIAL PRIMARY KEY,
    subject_id INTEGER REFERENCES subjects(id) ON DELETE CASCADE,
    role_id INTEGER REFERENCES roles(id) ON DELETE CASCADE,
    assigned_by BIGINT,
    assigned_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(subject_id, role_id)
);
