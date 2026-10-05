import asyncio
import os
import json
from datetime import datetime, timedelta, timezone

import asyncpg
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

# ================= НАСТРОЙКИ =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_ID = 7934244888

MSK = timezone(timedelta(hours=3))

ELECTION_START = datetime(2026, 10, 4, 14, 0, tzinfo=MSK)
ELECTION_END = datetime(2026, 10, 7, 20, 0, tzinfo=MSK)

TEST_USERNAMES = {"@Nikolas_Connor"}
TEST_MODE_END = datetime(2026, 10, 4, 13, 0, tzinfo=MSK)

VIDEO_FILE_ID = "BAACAgIAAxkBAANLasIfw2IcWeZwXgiPqm4Ne1fHeRAAAsapAAKmCxFKxM0YkvpfMeA9BA"

CANDIDATES = {
    "1": {"name": "Блошихин Кирилл Вадимович", "bio": "Перепил Горохова, и тот передал ему власть.", "type": "main"},
    "2": {"name": "Косарев Сергей Сергеевич", "bio": "Главный генератор сбора шашлычных банкетов.", "type": "main"},
    "3": {"name": "Проселков Кирилл Романович", "bio": "Единственный имеет девушку.", "type": "main"},
    "4": {"name": "Горохов Никита Александрович", "bio": "Был президентом.", "type": "additional"},
    "5": {"name": "ПРОТИВ ВСЕХ", "bio": "Выборы, выборы, кандидаты пидоры...\nPS. Группа «Ленинград».", "type": "against"},
}

VOTERS = {
    "@Haiser101": {"id": None, "name": "Яровой Иван Сергеевич"},
    "@vozduhanprimee": {"id": None, "name": "Бородин Тимофей Сергеевич"},
    "@spar9d": {"id": None, "name": "Глазков Владислав Юрьевич"},
    "@Cakcer_12": {"id": None, "name": "Головин Максим Сергеевич"},
    "@Dronus01": {"id": None, "name": "Морев Андрей Олегович"},
    "@Nikolas_Connor": {"id": 7934244888, "name": "Горохов Никита Александрович"},
    "@wwwLenGrad": {"id": None, "name": "Никита (2-й аккаунт)"},
}

PRELOADED_VOTES = [
    {"username": "@Cakcer_12", "voter_name": "Головин Максим Сергеевич", "candidate_id": "3"},
    {"username": "@Dronus01", "voter_name": "Морев Андрей Олегович", "candidate_id": "3"},
    {"username": "@vozduhanprimee", "voter_name": "Бородин Тимофей Сергеевич", "candidate_id": "3"},
]

SUBJECTS_INITIAL = [
    {"full_name": "Блошихин Кирилл Вадимович", "username": "@Bloha_71"},
    {"full_name": "Проселков Кирилл Романович", "username": "@G12_inthehearts"},
    {"full_name": "Косарев Сергей Сергеевич", "username": "@Sergooo_71"},
    {"full_name": "Яровой Иван Сергеевич", "username": "@Haiser101"},
    {"full_name": "Бородин Тимофей Сергеевич", "username": "@vozduhanprimee"},
    {"full_name": "Глазков Владислав Юрьевич", "username": "@spar9d"},
    {"full_name": "Головин Максим Сергеевич", "username": "@Cakcer_12"},
    {"full_name": "Морев Андрей Олегович", "username": "@Dronus01"},
    {"full_name": "Горохов Никита Александрович", "username": "@Nikolas_Connor"},
]

ROLES_INITIAL = [
    {"code": "president", "name": "Президент", "emoji": "👑", "max_holders": 1},
    {"code": "premier", "name": "Премьер-министр", "emoji": "🏛", "max_holders": 1},
    {"code": "cbank", "name": "Глава ЦБ", "emoji": "💰", "max_holders": 1},
    {"code": "advisor", "name": "Советник Президента", "emoji": "🎓", "max_holders": None},
    {"code": "minister", "name": "Министр", "emoji": "⚖️", "max_holders": None},
    {"code": "deputy", "name": "Депутат ГосДумы", "emoji": "📜", "max_holders": None},
    {"code": "party_leader", "name": "Лидер партии", "emoji": "🎭", "max_holders": None},
    {"code": "subject", "name": "Субъект", "emoji": "👤", "max_holders": None},
]

INITIAL_ROLES = [
    {"username": "@G12_inthehearts", "role_code": "president"},
    {"username": "@Nikolas_Connor", "role_code": "premier"},
]

PARTIES_INITIAL = [
    {"name": "Шашлык", "emoji": "🍖", "description": "За встречи на природе и мясо.", "leader_username": "@Bloha_71"},
    {"name": "Диван", "emoji": "🛋", "description": "За домашние посиделки и уют.", "leader_username": "@Cakcer_12"},
    {"name": "Хаос", "emoji": "🎲", "description": "За спонтанность и движ.", "leader_username": "@Nikolas_Connor"},
]

REP_RULES = {
    "vote": 1,
    "application": 2,
    "application_approved": 5,
    "application_rejected": -2,
    "law_approved": 10,
    "law_rejected": -3,
    "party_created": 15,
    "party_dissolved": -10,
    "overdue": -5,
}

db_pool = None
flags = {"test_end_notified": False, "election_end_notified": False}
# =============================================


class PartyForm(StatesGroup):
    waiting_name = State()
    waiting_emoji = State()
    waiting_description = State()


class LawForm(StatesGroup):
    waiting_title = State()
    waiting_description = State()


class DecreeForm(StatesGroup):
    waiting_title = State()
    waiting_text = State()
    waiting_secret = State()


class NewsForm(StatesGroup):
    waiting_text = State()


class ElectionForm(StatesGroup):
    waiting_date_end = State()


class DumaSessionForm(StatesGroup):
    waiting_law_id = State()


dp = Dispatcher()


# ===== УТИЛИТЫ =====
def normalize_username(username):
    if not username:
        return None
    if not username.startswith("@"):
        return "@" + username
    return username


def now_msk():
    return datetime.now(MSK)


def get_election_status():
    n = now_msk()
    if n < ELECTION_START:
        return "before"
    elif n <= ELECTION_END:
        return "during"
    else:
        return "after"


def format_delta(delta):
    total = int(delta.total_seconds())
    if total < 0:
        return "0 сек"
    days = total // 86400
    hours = (total % 86400) // 3600
    minutes = (total % 3600) // 60
    parts = []
    if days:
        parts.append(f"{days} дн.")
    if hours:
        parts.append(f"{hours} ч.")
    if minutes and not days:
        parts.append(f"{minutes} мин.")
    return " ".join(parts) if parts else "меньше минуты"


def is_tester(username):
    if username not in TEST_USERNAMES:
        return False
    if now_msk() >= TEST_MODE_END:
        return False
    return True


def is_allowed_to_vote(user_id, username):
    uname = normalize_username(username)
    if uname in VOTERS:
        return True
    for u, info in VOTERS.items():
        if info.get("id") == user_id and user_id > 0:
            return True
    return False


def get_voter_name(user_id, username):
    uname = normalize_username(username)
    if uname in VOTERS:
        return VOTERS[uname]["name"]
    for u, info in VOTERS.items():
        if info.get("id") == user_id and user_id > 0:
            return info["name"]
    return "Субъект"


def check_secret_word(text):
    if not text:
        return False
    t = text.lower().strip()
    t = " ".join(t.split())
    parts = t.split()
    if len(parts) == 2:
        w1, w2 = parts
        if len(w1) == 3 and w1[0] == "б" and w1[1] == "о" and w1[2] == "г":
            if w2.startswith("эфиоп") or w2.startswith("ефиоп"):
                if w2.endswith("и") or w2.endswith("ия"):
                    return True
    return False


# ===== БАЗА ДАННЫХ =====
async def init_db():
    async with db_pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS votes (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                username TEXT,
                voter_name TEXT,
                candidate_id TEXT NOT NULL,
                voted_at TIMESTAMP DEFAULT NOW(),
                added_by_admin BOOLEAN DEFAULT FALSE
            )
        """)
        await conn.execute("ALTER TABLE votes ADD COLUMN IF NOT EXISTS added_by_admin BOOLEAN DEFAULT FALSE")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS service_flags (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS subjects (
                id SERIAL PRIMARY KEY,
                user_id BIGINT UNIQUE,
                username TEXT UNIQUE,
                full_name TEXT NOT NULL,
                is_citizen BOOLEAN DEFAULT FALSE,
                reputation INTEGER DEFAULT 0,
                joined_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS roles (
                id SERIAL PRIMARY KEY,
                code TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                emoji TEXT DEFAULT '👤',
                description TEXT DEFAULT '',
                max_holders INTEGER,
                is_default BOOLEAN DEFAULT FALSE
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS subject_roles (
                id SERIAL PRIMARY KEY,
                subject_id INTEGER REFERENCES subjects(id) ON DELETE CASCADE,
                role_id INTEGER REFERENCES roles(id) ON DELETE CASCADE,
                assigned_by BIGINT,
                assigned_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(subject_id, role_id)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS parties (
                id SERIAL PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                emoji TEXT DEFAULT '🎭',
                description TEXT DEFAULT '',
                founder_username TEXT,
                leader_username TEXT,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS party_members (
                id SERIAL PRIMARY KEY,
                party_id INTEGER REFERENCES parties(id) ON DELETE CASCADE,
                username TEXT UNIQUE NOT NULL,
                joined_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS applications (
                id SERIAL PRIMARY KEY,
                type TEXT NOT NULL,
                author_username TEXT NOT NULL,
                author_name TEXT,
                target_username TEXT,
                data JSONB DEFAULT '{}',
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT NOW(),
                decided_at TIMESTAMP,
                decided_by BIGINT,
                reason TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS admin_sessions (
                user_id BIGINT PRIMARY KEY,
                is_active BOOLEAN DEFAULT FALSE,
                activated_at TIMESTAMP
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS laws (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT,
                author_username TEXT,
                status TEXT DEFAULT 'duma',
                duma_votes_for INTEGER DEFAULT 0,
                duma_votes_against INTEGER DEFAULT 0,
                gov_approved BOOLEAN DEFAULT FALSE,
                president_signed BOOLEAN DEFAULT FALSE,
                deadline TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS law_votes (
                id SERIAL PRIMARY KEY,
                law_id INTEGER REFERENCES laws(id) ON DELETE CASCADE,
                voter_username TEXT NOT NULL,
                vote TEXT NOT NULL,
                voted_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(law_id, voter_username)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS decrees (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                text TEXT,
                author_username TEXT,
                is_secret BOOLEAN DEFAULT FALSE,
                secret_for TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS news (
                id SERIAL PRIMARY KEY,
                text TEXT NOT NULL,
                source TEXT DEFAULT 'auto',
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS duma_elections (
                id SERIAL PRIMARY KEY,
                started_at TIMESTAMP DEFAULT NOW(),
                ends_at TIMESTAMP,
                status TEXT DEFAULT 'active',
                results JSONB DEFAULT '{}'
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS duma_votes (
                id SERIAL PRIMARY KEY,
                election_id INTEGER REFERENCES duma_elections(id) ON DELETE CASCADE,
                voter_username TEXT NOT NULL,
                party_id INTEGER NOT NULL,
                voted_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(election_id, voter_username)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS president_term (
                id SERIAL PRIMARY KEY,
                username TEXT NOT NULL,
                started_at TIMESTAMP DEFAULT NOW(),
                ends_at TIMESTAMP,
                status TEXT DEFAULT 'active'
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS duma_session (
                id SERIAL PRIMARY KEY,
                law_id INTEGER REFERENCES laws(id) ON DELETE CASCADE,
                started_by TEXT,
                started_at TIMESTAMP DEFAULT NOW(),
                deadline TIMESTAMP,
                status TEXT DEFAULT 'active'
            )
        """)
        async def preload_roles():
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT value FROM service_flags WHERE key = 'roles_loaded'")
        if row is not None:
            return
        for r in ROLES_INITIAL:
            await conn.execute("""
                INSERT INTO roles (code, name, emoji, max_holders)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (code) DO NOTHING
            """, r["code"], r["name"], r["emoji"], r["max_holders"])
        await conn.execute("INSERT INTO service_flags (key, value) VALUES ('roles_loaded', 'done')")


async def preload_subjects():
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT value FROM service_flags WHERE key = 'subjects_loaded'")
        if row is not None:
            return
        for s in SUBJECTS_INITIAL:
            uname = normalize_username(s["username"])
            await conn.execute("""
                INSERT INTO subjects (username, full_name, is_citizen)
                VALUES ($1, $2, TRUE)
                ON CONFLICT (username) DO NOTHING
            """, uname, s["full_name"])
        await conn.execute("INSERT INTO service_flags (key, value) VALUES ('subjects_loaded', 'done')")


async def preload_initial_roles():
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT value FROM service_flags WHERE key = 'initial_roles_loaded'")
        if row is not None:
            return
        for ir in INITIAL_ROLES:
            uname = normalize_username(ir["username"])
            subj = await conn.fetchrow("SELECT id FROM subjects WHERE username = $1", uname)
            role = await conn.fetchrow("SELECT id FROM roles WHERE code = $1", ir["role_code"])
            if subj and role:
                await conn.execute("""
                    INSERT INTO subject_roles (subject_id, role_id, assigned_by)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (subject_id, role_id) DO NOTHING
                """, subj["id"], role["id"], ADMIN_ID)
        await conn.execute("INSERT INTO service_flags (key, value) VALUES ('initial_roles_loaded', 'done')")


async def preload_parties():
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT value FROM service_flags WHERE key = 'parties_loaded'")
        if row is not None:
            return
        for p in PARTIES_INITIAL:
            uname = normalize_username(p["leader_username"])
            await conn.execute("""
                INSERT INTO parties (name, emoji, description, founder_username, leader_username)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (name) DO NOTHING
            """, p["name"], p["emoji"], p["description"], uname, uname)
            party = await conn.fetchrow("SELECT id FROM parties WHERE name = $1", p["name"])
            if party:
                await conn.execute("""
                    INSERT INTO party_members (party_id, username)
                    VALUES ($1, $2)
                    ON CONFLICT (username) DO NOTHING
                """, party["id"], uname)
        await conn.execute("INSERT INTO service_flags (key, value) VALUES ('parties_loaded', 'done')")


async def preload_votes():
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT value FROM service_flags WHERE key = 'preloaded_votes'")
        if row is not None:
            return
        for v in PRELOADED_VOTES:
            await conn.execute("""
                INSERT INTO votes (user_id, username, voter_name, candidate_id)
                VALUES ($1, $2, $3, $4)
            """, -1, normalize_username(v["username"]), v["voter_name"], v["candidate_id"])
        await conn.execute("INSERT INTO service_flags (key, value) VALUES ('preloaded_votes', 'done')")


# ===== ГОЛОСА =====
async def save_vote(user_id, username, voter_name, candidate_id, added_by_admin=False):
    username = normalize_username(username)
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO votes (user_id, username, voter_name, candidate_id, added_by_admin)
            VALUES ($1, $2, $3, $4, $5)
        """, user_id, username, voter_name, candidate_id, added_by_admin)


async def get_all_votes():
    async with db_pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM votes ORDER BY voted_at")


async def user_has_voted(user_id):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT id FROM votes WHERE user_id = $1", user_id)
        return row is not None


async def username_has_voted(username):
    username = normalize_username(username)
    if not username:
        return False
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT id FROM votes WHERE username = $1", username)
        return row is not None


async def delete_vote_by_username(username):
    username = normalize_username(username)
    if not username:
        return
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM votes WHERE username = $1", username)


async def clear_votes():
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM votes")
        await conn.execute("DELETE FROM service_flags WHERE key = 'preloaded_votes'")


# ===== СУБЪЕКТЫ =====
async def get_subject_by_user_id(user_id):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM subjects WHERE user_id = $1", user_id)


async def get_subject_by_username(username):
    username = normalize_username(username)
    if not username:
        return None
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM subjects WHERE username = $1", username)


async def get_all_subjects():
    async with db_pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM subjects ORDER BY id")


async def update_subject_user_id(username, user_id):
    username = normalize_username(username)
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE subjects SET user_id = $1 WHERE username = $2", user_id, username)


async def add_reputation(username, amount):
    username = normalize_username(username)
    if not username:
        return
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE subjects SET reputation = reputation + $1 WHERE username = $2", amount, username)


async def get_subject_roles(subject_id):
    async with db_pool.acquire() as conn:
        return await conn.fetch("""
            SELECT r.* FROM roles r
            JOIN subject_roles sr ON sr.role_id = r.id
            WHERE sr.subject_id = $1
            ORDER BY r.id
        """, subject_id)


async def assign_role(subject_id, role_id, assigned_by):
    async with db_pool.acquire() as conn:
        cnt = await conn.fetchval("SELECT COUNT(*) FROM subject_roles WHERE subject_id = $1", subject_id)
        if cnt >= 2:
            return False, "Максимум 2 должности"
        role = await conn.fetchrow("SELECT * FROM roles WHERE id = $1", role_id)
        if not role:
            return False, "Роль не найдена"
        if role["max_holders"] is not None:
            holders = await conn.fetchval("SELECT COUNT(*) FROM subject_roles WHERE role_id = $1", role_id)
            if holders >= role["max_holders"]:
                return False, f"Роль «{role['name']}» занята"
        await conn.execute("""
            INSERT INTO subject_roles (subject_id, role_id, assigned_by)
            VALUES ($1, $2, $3)
            ON CONFLICT (subject_id, role_id) DO NOTHING
        """, subject_id, role_id, assigned_by)
        return True, "OK"


async def remove_role(subject_id, role_id):
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM subject_roles WHERE subject_id = $1 AND role_id = $2", subject_id, role_id)


async def get_all_roles():
    async with db_pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM roles ORDER BY id")


async def get_subject(user_id, username):
    username = normalize_username(username)
    if username:
        s = await get_subject_by_username(username)
        if s:
            return s
    if user_id:
        return await get_subject_by_user_id(user_id)
    return None


async def has_role(user_id, role_code):
    if not user_id:
        return False
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT 1 FROM subjects s
            JOIN subject_roles sr ON sr.subject_id = s.id
            JOIN roles r ON r.id = sr.role_id
            WHERE s.user_id = $1 AND r.code = $2
        """, user_id, role_code)
        return row is not None


async def has_role_by_username(username, role_code):
    username = normalize_username(username)
    if not username:
        return False
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT 1 FROM subjects s
            JOIN subject_roles sr ON sr.subject_id = s.id
            JOIN roles r ON r.id = sr.role_id
            WHERE s.username = $1 AND r.code = $2
        """, username, role_code)
        return row is not None


# ===== ПАРТИИ =====
async def get_all_parties(active_only=True):
    async with db_pool.acquire() as conn:
        if active_only:
            return await conn.fetch("SELECT * FROM parties WHERE status = 'active' ORDER BY id")
        return await conn.fetch("SELECT * FROM parties ORDER BY id")


async def get_party(party_id):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM parties WHERE id = $1", party_id)


async def get_party_members(party_id):
    async with db_pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM party_members WHERE party_id = $1 ORDER BY joined_at", party_id)


async def get_party_by_name(name):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM parties WHERE name = $1", name)


async def create_party(name, emoji, description, leader_username):
    leader_username = normalize_username(leader_username)
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO parties (name, emoji, description, founder_username, leader_username)
            VALUES ($1, $2, $3, $4, $5)
        """, name, emoji, description, leader_username, leader_username)
        party = await conn.fetchrow("SELECT id FROM parties WHERE name = $1", name)
        if party:
            await conn.execute("""
                INSERT INTO party_members (party_id, username)
                VALUES ($1, $2)
                ON CONFLICT (username) DO NOTHING
            """, party["id"], leader_username)
        return party


async def get_user_party(username):
    username = normalize_username(username)
    if not username:
        return None
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT p.* FROM parties p
            JOIN party_members pm ON pm.party_id = p.id
            WHERE pm.username = $1 AND p.status = 'active'
        """, username)
        return row


async def add_party_member(party_id, username):
    username = normalize_username(username)
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO party_members (party_id, username)
            VALUES ($1, $2)
            ON CONFLICT (username) DO NOTHING
        """, party_id, username)


async def remove_party_member(username):
    username = normalize_username(username)
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM party_members WHERE username = $1", username)


async def dissolve_party(party_id):
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE parties SET status = 'dissolved' WHERE id = $1", party_id)


async def change_party_leader(party_id, new_leader_username):
    new_leader_username = normalize_username(new_leader_username)
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE parties SET leader_username = $1 WHERE id = $2", new_leader_username, party_id)


# ===== ЗАЯВКИ =====
async def create_application(app_type, author_username, author_name, target_username, data):
    author_username = normalize_username(author_username)
    target_username = normalize_username(target_username) if target_username else None
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO applications (type, author_username, author_name, target_username, data)
            VALUES ($1, $2, $3, $4, $5)
        """, app_type, author_username, author_name, target_username, json.dumps(data))


async def get_pending_applications(target_username=None):
    async with db_pool.acquire() as conn:
        if target_username:
            target_username = normalize_username(target_username)
            return await conn.fetch("""
                SELECT * FROM applications WHERE status = 'pending' AND target_username = $1
                ORDER BY created_at
            """, target_username)
        return await conn.fetch("SELECT * FROM applications WHERE status = 'pending' ORDER BY created_at")


async def get_application(app_id):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM applications WHERE id = $1", app_id)


async def approve_application(app_id, decided_by):
    async with db_pool.acquire() as conn:
        await conn.execute("""
            UPDATE applications SET status = 'approved', decided_at = NOW(), decided_by = $1
            WHERE id = $2
        """, decided_by, app_id)


async def reject_application(app_id, decided_by, reason):
    async with db_pool.acquire() as conn:
        await conn.execute("""
            UPDATE applications SET status = 'rejected', decided_at = NOW(), decided_by = $1, reason = $2
            WHERE id = $3
        """, decided_by, reason, app_id)


async def transfer_applications(old_target, new_target):
    old_target = normalize_username(old_target)
    new_target = normalize_username(new_target)
    if not old_target or not new_target:
        return
    async with db_pool.acquire() as conn:
        await conn.execute("""
            UPDATE applications SET target_username = $1
            WHERE target_username = $2 AND status = 'pending'
        """, new_target, old_target)


# ===== АДМИН-СЕССИИ =====
async def is_admin_active(user_id):
    if user_id != ADMIN_ID:
        return False
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT is_active FROM admin_sessions WHERE user_id = $1", user_id)
        return row and row["is_active"]


async def activate_admin(user_id):
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO admin_sessions (user_id, is_active, activated_at)
            VALUES ($1, TRUE, NOW())
            ON CONFLICT (user_id) DO UPDATE SET is_active = TRUE, activated_at = NOW()
        """, user_id)


async def deactivate_admin(user_id):
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE admin_sessions SET is_active = FALSE WHERE user_id = $1", user_id)


# ===== ЗАКОНЫ =====
async def create_law(title, description, author_username, deadline=None):
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO laws (title, description, author_username, status, deadline)
            VALUES ($1, $2, $3, 'duma', $4)
        """, title, description, normalize_username(author_username), deadline)
        return await conn.fetchrow("SELECT * FROM laws WHERE title = $1 ORDER BY id DESC LIMIT 1", title)


async def get_law(law_id):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM laws WHERE id = $1", law_id)


async def get_all_laws(status=None):
    async with db_pool.acquire() as conn:
        if status:
            return await conn.fetch("SELECT * FROM laws WHERE status = $1 ORDER BY id DESC", status)
        return await conn.fetch("SELECT * FROM laws ORDER BY id DESC")


async def vote_law(law_id, username, vote):
    username = normalize_username(username)
    async with db_pool.acquire() as conn:
        existing = await conn.fetchrow("SELECT id FROM law_votes WHERE law_id = $1 AND voter_username = $2", law_id, username)
        if existing:
            return False, "Ты уже голосовал"
        await conn.execute("""
            INSERT INTO law_votes (law_id, voter_username, vote)
            VALUES ($1, $2, $3)
        """, law_id, username, vote)
        if vote == "for":
            await conn.execute("UPDATE laws SET duma_votes_for = duma_votes_for + 1 WHERE id = $1", law_id)
        else:
            await conn.execute("UPDATE laws SET duma_votes_against = duma_votes_against + 1 WHERE id = $1", law_id)
        return True, "OK"


async def update_law_status(law_id, status):
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE laws SET status = $1 WHERE id = $2", status, law_id)


# ===== УКАЗЫ =====
async def create_decree(title, text, author_username, is_secret=False, secret_for=None):
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO decrees (title, text, author_username, is_secret, secret_for)
            VALUES ($1, $2, $3, $4, $5)
        """, title, text, normalize_username(author_username), is_secret, secret_for)


async def get_all_decrees():
    async with db_pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM decrees ORDER BY id DESC")


# ===== ГАЗЕТА =====
async def add_news(text, source="auto"):
    async with db_pool.acquire() as conn:
        await conn.execute("INSERT INTO news (text, source) VALUES ($1, $2)", text, source)


async def get_news(limit=20):
    async with db_pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM news ORDER BY id DESC LIMIT $1", limit)


# ===== ПРЕЗИДЕНТСКИЙ СРОК =====
async def get_active_president_term():
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM president_term WHERE status = 'active' ORDER BY id DESC LIMIT 1")


async def start_president_term(username, ends_at):
    username = normalize_username(username)
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE president_term SET status = 'finished' WHERE status = 'active'")
        await conn.execute("""
            INSERT INTO president_term (username, ends_at, status) VALUES ($1, $2, 'active')
        """, username, ends_at)


async def end_president_term():
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE president_term SET status = 'finished' WHERE status = 'active'")


# ===== ГОСДУМА =====
async def start_duma_election(ends_at):
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO duma_elections (ends_at, status) VALUES ($1, 'active')
        """, ends_at)
        return await conn.fetchrow("SELECT * FROM duma_elections ORDER BY id DESC LIMIT 1")


async def get_active_duma_election():
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM duma_elections WHERE status = 'active' ORDER BY id DESC LIMIT 1")


async def vote_duma(election_id, voter_username, party_id):
    voter_username = normalize_username(voter_username)
    async with db_pool.acquire() as conn:
        existing = await conn.fetchrow("""
            SELECT id FROM duma_votes WHERE election_id = $1 AND voter_username = $2
        """, election_id, voter_username)
        if existing:
            return False, "Ты уже голосовал"
        await conn.execute("""
            INSERT INTO duma_votes (election_id, voter_username, party_id)
            VALUES ($1, $2, $3)
        """, election_id, voter_username, party_id)
        return True, "OK"


async def finish_duma_election(election_id):
    """Считает места, выдаёт роли депутатов."""
    async with db_pool.acquire() as conn:
        # Считаем голоса по партиям
        rows = await conn.fetch("""
            SELECT party_id, COUNT(*) as cnt
            FROM duma_votes WHERE election_id = $1
            GROUP BY party_id ORDER BY cnt DESC LIMIT 3
        """, election_id)
        # Убираем роли депутатов у всех
        await conn.execute("""
            DELETE FROM subject_roles WHERE role_id IN (SELECT id FROM roles WHERE code = 'deputy')
        """)
        role = await conn.fetchrow("SELECT id FROM roles WHERE code = 'deputy'")
        winners_info = []
        for idx, r in enumerate(rows):
            party = await conn.fetchrow("SELECT * FROM parties WHERE id = $1", r["party_id"])
            if not party:
                continue
            members = await conn.fetch("SELECT username FROM party_members WHERE party_id = $1", party["id"])
            # Место: 0 → все, 1 → -1, 2 → -2
            deduct = idx
            allowed = max(0, len(members) - deduct)
            deputies = [m["username"] for m in members[:allowed]]
            winners_info.append({
                "party": party["name"],
                "votes": r["cnt"],
                "deputies": deputies,
                "place": idx + 1
            })
            # Назначаем роль депутата
            for d in deputies:
                subj = await conn.fetchrow("SELECT id FROM subjects WHERE username = $1", d)
                if subj and role:
                    await conn.execute("""
                        INSERT INTO subject_roles (subject_id, role_id, assigned_by)
                        VALUES ($1, $2, $3)
                        ON CONFLICT (subject_id, role_id) DO NOTHING
                    """, subj["id"], role["id"], ADMIN_ID)
        await conn.execute("""
            UPDATE duma_elections SET status = 'finished', results = $1 WHERE id = $2
        """, json.dumps(winners_info), election_id)
        return winners_info


async def get_duma_session():
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM duma_session WHERE status = 'active' ORDER BY id DESC LIMIT 1")


async def create_duma_session(law_id, started_by, deadline):
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO duma_session (law_id, started_by, deadline, status)
            VALUES ($1, $2, $3, 'active')
        """, law_id, normalize_username(started_by), deadline)


async def close_duma_session(session_id):
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE duma_session SET status = 'closed' WHERE id = $1", session_id)
        # ===== ТЕКСТЫ =====
def build_subject_profile_text_sync(subject, roles, user_party, admin_mode=False):
    roles_text = "\n".join([f"{r['emoji']} {r['name']}" for r in roles]) if roles else "👤 Субъект"
    joined = subject["joined_at"].strftime("%d.%m.%Y") if subject["joined_at"] else "—"
    citizen_text = "✅ Есть" if subject["is_citizen"] else "❌ Нет"
    party_text = f"{user_party['emoji']} {user_party['name']}" if user_party else "—"
    text = "━━━━━━━━━━━━━━━━━━━━━\n👤 ПРОФИЛЬ СУБЪЕКТА\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    text += f"{subject['full_name']}\n"
    text += f"Username: {subject['username'] or '—'}\n\n"
    text += f"Должности:\n{roles_text}\n\n"
    text += f"Партия: {party_text}\n"
    text += f"Гражданство: {citizen_text}\n"
    text += f"В ДКД с: {joined}\n"
    text += f"Репутация: {subject['reputation']}"
    if admin_mode:
        text += "\n\n🔓 АДМИН-РЕЖИМ АКТИВЕН"
    return text


def build_ballot_text():
    status = get_election_status()
    n = now_msk()
    date = n.strftime("%d.%m.%Y %H:%M")
    if status == "before":
        delta = ELECTION_START - n
        return ("━━━━━━━━━━━━━━━━━━━━━\n🗳 БЮЛЛЕТЕНЬ ДКД\nВыборы Президента\n━━━━━━━━━━━━━━━━━━━━━\n\n"
                "⏳ Выборы ещё не начались.\n\n"
                "Старт: 04.10.2026, 14:00 МСК\nКонец: 07.10.2026, 20:00 МСК\n\n"
                f"До старта: {format_delta(delta)}")
    if status == "during":
        delta = ELECTION_END - n
        return ("━━━━━━━━━━━━━━━━━━━━━\n🗳 БЮЛЛЕТЕНЬ ДКД\nВыборы Президента\n"
                f"Дата: {date} МСК\n━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"⏳ До конца голосования: {format_delta(delta)}\n\n"
                "Нажми на кнопку, чтобы отдать голос.\nОдин субъект — один голос.")
    return "━━━━━━━━━━━━━━━━━━━━━\n🗳 БЮЛЛЕТЕНЬ ДКД\n━━━━━━━━━━━━━━━━━━━━━\n\n🔒 Выборы завершены.\n\nСмотри результаты: /results"


def build_ballot_keyboard():
    buttons = [[InlineKeyboardButton(text=f"{cid}. {CANDIDATES[cid]['name']}", callback_data=f"vote_{cid}")] for cid in ["1", "2", "3"]]
    buttons.append([InlineKeyboardButton(text="— Доп. кандидат —", callback_data="noop")])
    buttons.append([InlineKeyboardButton(text=f"4. {CANDIDATES['4']['name']}", callback_data="vote_4")])
    buttons.append([InlineKeyboardButton(text=f"5. {CANDIDATES['5']['name']}", callback_data="vote_5")])
    buttons.append([InlineKeyboardButton(text="📖 Биографии кандидатов", callback_data="bios")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_bios_text():
    text = "━━━━━━━━━━━━━━━━━━━━━\n📖 БИОГРАФИИ КАНДИДАТОВ\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    for cid in ["1", "2", "3"]:
        c = CANDIDATES[cid]
        text += f"{cid}. {c['name']}\n{c['bio']}\n\n"
    c = CANDIDATES["4"]
    text += f"Доп. кандидат:\n\n4. {c['name']}\n{c['bio']}\n\n"
    c = CANDIDATES["5"]
    text += f"5. {c['name']}\n{c['bio']}\n\n━━━━━━━━━━━━━━━━━━━━━\n"
    return text


async def build_results_text():
    all_votes = await get_all_votes()
    counter = {cid: 0 for cid in CANDIDATES}
    for v in all_votes:
        counter[v["candidate_id"]] += 1
    text = "━━━━━━━━━━━━━━━━━━━━━\n📊 РЕЗУЛЬТАТЫ ГОЛОСОВАНИЯ\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    for cid, c in CANDIDATES.items():
        marker = " (доп.)" if c["type"] == "additional" else (" (особый пункт)" if c["type"] == "against" else "")
        text += f"{cid}. {c['name']}{marker} — {counter[cid]}\n"
    text += f"\nВсего голосов: {len(all_votes)}"
    max_votes = max(counter.values()) if counter else 0
    winners = [cid for cid, c in counter.items() if c == max_votes]
    if len(winners) == 1:
        win_id = winners[0]
        if win_id == "5":
            text += "\n\n⚠️ Победил «ПРОТИВ ВСЕХ» — выборы недействительны."
        else:
            text += f"\n\n🏆 Победитель: {CANDIDATES[win_id]['name']}"
    else:
        text += "\n\n⚖️ Ничья!"
    return text


async def build_status_text():
    all_votes = await get_all_votes()
    voted_usernames = set()
    voted_ids = set()
    for v in all_votes:
        uname = normalize_username(v["username"])
        if uname:
            voted_usernames.add(uname)
        if v["user_id"] and v["user_id"] > 0:
            voted_ids.add(v["user_id"])
    voted_list, not_voted_list = [], []
    for uname, info in VOTERS.items():
        uname_norm = normalize_username(uname)
        uid = info.get("id")
        is_voted = uname_norm in voted_usernames or (uid and uid > 0 and uid in voted_ids)
        if is_voted:
            voted_list.append(f"✅ {info['name']} ({uname})")
        else:
            not_voted_list.append(f"❌ {info['name']} ({uname})")
    text = "━━━━━━━━━━━━━━━━━━━━━\n👥 СТАТУС ГОЛОСОВАНИЯ\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    text += f"Проголосовали ({len(voted_list)}):\n" + ("\n".join(voted_list) if voted_list else "—")
    text += f"\n\nНе голосовали ({len(not_voted_list)}):\n" + ("\n".join(not_voted_list) if not_voted_list else "—")
    text += f"\n\nВсего: {len(voted_list)} / {len(VOTERS)}"
    return text


async def build_votes_list_text():
    all_votes = await get_all_votes()
    by_candidate = {cid: [] for cid in CANDIDATES}
    for v in all_votes:
        cid = v["candidate_id"]
        marker = " (админ)" if v.get("added_by_admin", False) else ""
        by_candidate[cid].append(f"{v['voter_name']}{marker}")
    text = "━━━━━━━━━━━━━━━━━━━━━\n📋 СПИСОК ГОЛОСОВ\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    for cid, c in CANDIDATES.items():
        voters = by_candidate[cid]
        text += f"{cid}. {c['name']} — {len(voters)} голос(ов)\n"
        for voter in voters:
            text += f"  • {voter}\n"
        text += "\n"
    return text


async def build_subjects_list_text():
    subjects = await get_all_subjects()
    text = "━━━━━━━━━━━━━━━━━━━━━\n👥 СУБЪЕКТЫ ДКД\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    for s in subjects:
        roles = await get_subject_roles(s["id"])
        roles_short = ", ".join([r["name"] for r in roles]) if roles else "Субъект"
        text += f"• {s['full_name']}\n  {roles_short}\n\n"
    text += f"Всего: {len(subjects)}"
    return text


async def build_roles_list_text():
    roles = await get_all_roles()
    text = "━━━━━━━━━━━━━━━━━━━━━\n🎭 ДОЛЖНОСТИ ДКД\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    for r in roles:
        max_text = f"макс: {r['max_holders']}" if r["max_holders"] else "без ограничений"
        text += f"{r['emoji']} {r['name']} ({max_text})\n"
    return text


async def build_parties_list_text():
    parties = await get_all_parties()
    if not parties:
        return "━━━━━━━━━━━━━━━━━━━━━\n🎭 ПАРТИИ ДКД\n━━━━━━━━━━━━━━━━━━━━━\n\nПока нет партий."
    text = "━━━━━━━━━━━━━━━━━━━━━\n🎭 ПАРТИИ ДКД\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    for p in parties:
        members = await get_party_members(p["id"])
        text += f"{p['emoji']} {p['name']} — {len(members)} чел.\n   Лидер: {p['leader_username']}\n\n"
    return text


async def build_party_detail_text(party):
    members = await get_party_members(party["id"])
    text = "━━━━━━━━━━━━━━━━━━━━━\n"
    text += f"{party['emoji']} {party['name'].upper()}\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    text += f"{party['description']}\n\n"
    text += f"Лидер: {party['leader_username']}\nСостав: {len(members)}\n"
    for m in members:
        text += f"  • {m['username']}\n"
    return text


# ===== АДМИН-ПАНЕЛЬ =====
def build_admin_keyboard(active=False):
    activate_btn = "🔓 Активировать Админ-режим" if not active else "🔒 Деактивировать Админ-режим"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=activate_btn, callback_data="admin_toggle")],
        [InlineKeyboardButton(text="👥 Субъекты", callback_data="admin_subjects")],
        [InlineKeyboardButton(text="🎭 Должности", callback_data="admin_roles")],
        [InlineKeyboardButton(text="🎭 Партии", callback_data="admin_parties")],
        [InlineKeyboardButton(text="📋 Заявки", callback_data="admin_apps")],
        [InlineKeyboardButton(text="📜 Законы", callback_data="admin_laws")],
        [InlineKeyboardButton(text="📢 Указы", callback_data="admin_decrees")],
        [InlineKeyboardButton(text="📰 Газета", callback_data="admin_news")],
        [InlineKeyboardButton(text="🗳 ГосДума", callback_data="admin_duma")],
        [InlineKeyboardButton(text="👤 Гражданство", callback_data="admin_citizen")],
        [InlineKeyboardButton(text="📊 Результаты выборов", callback_data="admin_results")],
        [InlineKeyboardButton(text="👥 Кто голосовал", callback_data="admin_status")],
        [InlineKeyboardButton(text="📋 Список голосов", callback_data="admin_votes")],
        [InlineKeyboardButton(text="✍️ Внести голос", callback_data="admin_add_vote")],
        [InlineKeyboardButton(text="🗑 Удалить голос", callback_data="admin_del_vote")],
        [InlineKeyboardButton(text="🔄 Сбросить голоса", callback_data="admin_reset_confirm")],
    ])


def build_admin_subjects_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Список субъектов", callback_data="admin_subjects_list")],
        [InlineKeyboardButton(text="➕ Выдать должность", callback_data="admin_assign_role_subj")],
        [InlineKeyboardButton(text="➖ Снять должность", callback_data="admin_remove_role_subj")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")],
    ])


def build_admin_laws_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Список законов", callback_data="admin_laws_list")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")],
    ])


def build_admin_decrees_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Список указов", callback_data="admin_decrees_list")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")],
    ])


def build_admin_news_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Лента", callback_data="admin_news_list")],
        [InlineKeyboardButton(text="➕ Добавить", callback_data="admin_news_add")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")],
    ])


def build_admin_duma_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗳 Начать выборы", callback_data="admin_duma_start")],
        [InlineKeyboardButton(text="📊 Результаты", callback_data="admin_duma_results")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")],
    ])


def build_admin_parties_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Список партий", callback_data="admin_parties_list")],
        [InlineKeyboardButton(text="➕ Создать партию", callback_data="admin_create_party")],
        [InlineKeyboardButton(text="🗑 Распустить партию", callback_data="admin_dissolve_party")],
        [InlineKeyboardButton(text="👑 Сменить лидера", callback_data="admin_change_leader")],
        [InlineKeyboardButton(text="🏆 Кладбище партий", callback_data="admin_party_graveyard")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")],
    ])


async def build_admin_parties_list_keyboard():
    parties = await get_all_parties(active_only=False)
    buttons = []
    for p in parties:
        status = "✅" if p["status"] == "active" else "💀"
        buttons.append([InlineKeyboardButton(text=f"{status} {p['emoji']} {p['name']}", callback_data=f"admin_party_view|{p['id']}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_parties")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def build_admin_dissolve_party_keyboard():
    parties = await get_all_parties(active_only=True)
    buttons = []
    for p in parties:
        buttons.append([InlineKeyboardButton(text=f"🗑 {p['emoji']} {p['name']}", callback_data=f"admin_dissolve|{p['id']}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_parties")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def build_admin_change_leader_keyboard():
    parties = await get_all_parties(active_only=True)
    buttons = []
    for p in parties:
        buttons.append([InlineKeyboardButton(text=f"{p['emoji']} {p['name']} (лидер: {p['leader_username']})", callback_data=f"admin_leader_party|{p['id']}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_parties")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def build_admin_leader_subject_keyboard(party_id):
    subjects = await get_all_subjects()
    buttons = []
    for s in subjects:
        buttons.append([InlineKeyboardButton(text=s['full_name'], callback_data=f"admin_leader_set|{party_id}|{s['username']}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_change_leader")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def build_admin_subjects_list_keyboard():
    subjects = await get_all_subjects()
    buttons = []
    for s in subjects:
        buttons.append([InlineKeyboardButton(text=s['full_name'], callback_data=f"admin_subj_view|{s['id']}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_subjects")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def build_admin_assign_role_subj_keyboard():
    subjects = await get_all_subjects()
    buttons = []
    for s in subjects:
        buttons.append([InlineKeyboardButton(text=s['full_name'], callback_data=f"admin_assign_subj|{s['id']}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_subjects")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def build_admin_assign_role_keyboard(subject_id):
    roles = await get_all_roles()
    buttons = []
    for r in roles:
        buttons.append([InlineKeyboardButton(text=f"{r['emoji']} {r['name']}", callback_data=f"admin_assign_role|{subject_id}|{r['id']}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_subjects")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def build_admin_remove_role_subj_keyboard():
    subjects = await get_all_subjects()
    buttons = []
    for s in subjects:
        buttons.append([InlineKeyboardButton(text=s['full_name'], callback_data=f"admin_remove_subj|{s['id']}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_subjects")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def build_admin_remove_role_keyboard(subject_id):
    roles = await get_subject_roles(subject_id)
    buttons = []
    for r in roles:
        buttons.append([InlineKeyboardButton(text=f"🗑 {r['emoji']} {r['name']}", callback_data=f"admin_remove_role|{subject_id}|{r['id']}")])
    if not roles:
        buttons.append([InlineKeyboardButton(text="(нет должностей)", callback_data="noop")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_subjects")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_admin_del_vote_keyboard():
    buttons = []
    for uname, info in VOTERS.items():
        buttons.append([InlineKeyboardButton(text=f"🗑 {info['name']}", callback_data=f"admin_delvote|{uname}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_admin_add_vote_keyboard():
    buttons = []
    for uname, info in VOTERS.items():
        buttons.append([InlineKeyboardButton(text=info['name'], callback_data=f"admin_addvote_subj|{uname}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_admin_add_candidate_keyboard(username):
    buttons = []
    for cid, c in CANDIDATES.items():
        buttons.append([InlineKeyboardButton(text=f"{cid}. {c['name']}", callback_data=f"admin_addvote_cand|{username}|{cid}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_add_vote")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_admin_confirm_reset_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚠️ ДА, СБРОСИТЬ", callback_data="admin_reset_yes")],
        [InlineKeyboardButton(text="◀️ Отмена", callback_data="admin_back")],
    ])


# ===== ПУБЛИЧНЫЕ КОМАНДЫ =====
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user = message.from_user
    username = normalize_username(user.username)
    subject = await get_subject(user.id, username)
    if subject:
        if subject["user_id"] != user.id and user.id:
            await update_subject_user_id(subject["username"], user.id)
        await message.answer(
            f"🏛 Добро пожаловать, {subject['full_name']}!\n\n"
            "Команды:\n/me — профиль\n/subjects — список субъектов\n/roles — должности\n"
            "/parties — партии\n/laws — законы\n/decrees — указы\n/news — газета\n"
            "/apps — мои заявки\n/vote — голосование\n/help — помощь"
        )
        return
    await message.answer("🏛 Добро пожаловать в ДКД!\n\nТы не в списке субъектов.\nЧтобы зарегистрироваться, отправь кодовое слово.")


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "📖 Помощь\n\n/me — профиль\n/subjects — субъекты\n/roles — должности\n"
        "/parties — партии\n/laws — законы\n/decrees — указы\n/news — газета\n"
        "/apps — мои заявки\n/vote — голосование\n/law — внести закон (депутатам)\n"
        "/president — панель Президента\n/admin — админ-панель"
    )


@dp.message(Command("me"))
async def cmd_me(message: types.Message):
    user = message.from_user
    username = normalize_username(user.username)
    subject = await get_subject(user.id, username)
    if not subject:
        await message.answer("❌ Ты не зарегистрирован. Напиши /start.")
        return
    roles = await get_subject_roles(subject["id"])
    user_party = await get_user_party(username)
    admin_mode = await is_admin_active(user.id)
    text = build_subject_profile_text_sync(subject, roles, user_party, admin_mode)
    await message.answer(text)


@dp.message(Command("subjects"))
async def cmd_subjects(message: types.Message):
    await message.answer(await build_subjects_list_text())


@dp.message(Command("roles"))
async def cmd_roles(message: types.Message):
    await message.answer(await build_roles_list_text())


@dp.message(Command("parties"))
async def cmd_parties(message: types.Message):
    parties = await get_all_parties()
    if not parties:
        await message.answer("━━━━━━━━━━━━━━━━━━━━━\n🎭 ПАРТИИ ДКД\n━━━━━━━━━━━━━━━━━━━━━\n\nПока нет партий.")
        return
    text = await build_parties_list_text()
    buttons = [[InlineKeyboardButton(text=f"{p['emoji']} {p['name']}", callback_data=f"party_view|{p['id']}")] for p in parties]
    buttons.append([InlineKeyboardButton(text="➕ Создать партию", callback_data="party_create")])
    buttons.append([InlineKeyboardButton(text="🏆 Кладбище партий", callback_data="party_graveyard")])
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@dp.message(Command("laws"))
async def cmd_laws(message: types.Message):
    laws = await get_all_laws()
    if not laws:
        await message.answer("📜 Законов пока нет.")
        return
    status_names = {"duma": "🟡 ГосДума", "government": "🟠 Правительство", "president": "🔵 Президент", "approved": "🟢 Принят", "vetoed": "🔴 Вето"}
    buttons = []
    for l in laws[:15]:
        buttons.append([InlineKeyboardButton(text=f"#{l['id']} {l['title'][:25]} — {status_names.get(l['status'], '')}", callback_data=f"law_view|{l['id']}")])
    await message.answer("━━━━━━━━━━━━━━━━━━━━━\n📜 ЗАКОНЫ ДКД\n━━━━━━━━━━━━━━━━━━━━━", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@dp.message(Command("decrees"))
async def cmd_decrees(message: types.Message):
    decrees = await get_all_decrees()
    if not decrees:
        await message.answer("📢 Указов пока нет.")
        return
    text = "━━━━━━━━━━━━━━━━━━━━━\n📢 УКАЗЫ ПРЕЗИДЕНТА\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    for d in decrees[:20]:
        marker = "🔒" if d["is_secret"] else "📢"
        text += f"{marker} #{d['id']} {d['title']}\n"
    await message.answer(text)


@dp.message(Command("news"))
async def cmd_news(message: types.Message):
    news = await get_news(20)
    if not news:
        await message.answer("📰 Газета пока пустая.")
        return
    text = "━━━━━━━━━━━━━━━━━━━━━\n📰 ГАЗЕТА ДКД\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    for n in news:
        dt = n["created_at"].strftime("%d.%m %H:%M") if n["created_at"] else "—"
        text += f"[{dt}] {n['text']}\n\n"
    await message.answer(text)


@dp.message(Command("apps"))
async def cmd_apps(message: types.Message):
    user = message.from_user
    username = normalize_username(user.username)
    subject = await get_subject(user.id, username)
    if not subject:
        await message.answer("❌ Ты не зарегистрирован.")
        return
    async with db_pool.acquire() as conn:
        my_apps = await conn.fetch("SELECT * FROM applications WHERE author_username = $1 ORDER BY created_at DESC LIMIT 10", username)
    if not my_apps:
        await message.answer("📋 У тебя пока нет заявок.")
        return
    text = "━━━━━━━━━━━━━━━━━━━━━\n📋 МОИ ЗАЯВКИ\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    for a in my_apps:
        se = {"pending": "🟡", "approved": "🟢", "rejected": "🔴"}.get(a["status"], "⚪")
        text += f"{se} #{a['id']} — {a['type']}\n"
        if a["reason"]:
            text += f"   Причина: {a['reason']}\n"
        text += "\n"
    await message.answer(text)


# ===== ПАНЕЛЬ ПРЕЗИДЕНТА =====
def build_president_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Создать указ", callback_data="pres_decree")],
        [InlineKeyboardButton(text="📜 Обращение к народу", callback_data="pres_address")],
        [InlineKeyboardButton(text="📋 Заявки мне", callback_data="pres_apps")],
        [InlineKeyboardButton(text="🗳 Назначить выборы в ГосДуму", callback_data="pres_duma_start")],
        [InlineKeyboardButton(text="⚖️ Министры", callback_data="pres_ministers")],
        [InlineKeyboardButton(text="🏛 Созвать собрание ГосДумы", callback_data="pres_duma_session")],
    ])


@dp.message(Command("president"))
async def cmd_president(message: types.Message):
    user = message.from_user
    username = normalize_username(user.username)
    is_pres = await has_role_by_username(username, "president")
    if not is_pres:
        await message.answer("⛔ Только Президент имеет доступ к этой панели.")
        return
    term = await get_active_president_term()
    term_text = ""
    if term:
        term_text = f"\nСрок до: {term['ends_at'].strftime('%d.%m.%Y %H:%M')} МСК"
    await message.answer(
        f"━━━━━━━━━━━━━━━━━━━━━\n👑 ПАНЕЛЬ ПРЕЗИДЕНТА\n━━━━━━━━━━━━━━━━━━━━━{term_text}\n\nВыбери действие:",
        reply_markup=build_president_keyboard()
    )


@dp.callback_query(lambda c: c.data == "pres_back")
async def pres_back(callback: types.CallbackQuery):
    try:
        if not await has_role_by_username(callback.from_user.username, "president"):
            await callback.answer("Только Президент.", show_alert=True)
            return
        await callback.message.edit_text("━━━━━━━━━━━━━━━━━━━━━\n👑 ПАНЕЛЬ ПРЕЗИДЕНТА\n━━━━━━━━━━━━━━━━━━━━━\n\nВыбери действие:", reply_markup=build_president_keyboard())
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "pres_decree")
async def pres_decree(callback: types.CallbackQuery, state: FSMContext):
    try:
        if not await has_role_by_username(callback.from_user.username, "president"):
            await callback.answer("Только Президент.", show_alert=True)
            return
        await callback.message.answer("📢 СОЗДАНИЕ УКАЗА\n\nШаг 1/3. Отправь ЗАГОЛОВОК.")
        await state.set_state(DecreeForm.waiting_title)
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "pres_apps")
async def pres_apps(callback: types.CallbackQuery):
    try:
        if not await has_role_by_username(callback.from_user.username, "president"):
            await callback.answer("Только Президент.", show_alert=True)
            return
        apps = await get_pending_applications(callback.from_user.username)
        if not apps:
            await callback.message.edit_text("📋 Заявок тебе нет.", reply_markup=build_president_keyboard())
            await callback.answer()
            return
        text = "━━━━━━━━━━━━━━━━━━━━━\n📋 ЗАЯВКИ ПРЕЗИДЕНТУ\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        buttons = []
        for a in apps:
            text += f"#{a['id']} — {a['type']} (от {a['author_username']})\n"
            buttons.append([InlineKeyboardButton(text=f"#{a['id']} — открыть", callback_data=f"pres_app_view|{a['id']}")])
        buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="pres_back")])
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("pres_app_view|"))
async def pres_app_view(callback: types.CallbackQuery):
    try:
        if not await has_role_by_username(callback.from_user.username, "president"):
            await callback.answer("Только Президент.", show_alert=True)
            return
        app_id = int(callback.data.split("|")[1])
        app = await get_application(app_id)
        if not app:
            await callback.answer("Не найдена.", show_alert=True)
            return
        data = app["data"]
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except Exception:
                data = {}
        text = f"📋 ЗАЯВКА #{app_id}\n\nТип: {app['type']}\nАвтор: {app['author_username']}\n"
        if data:
            text += f"Данные: {json.dumps(data, ensure_ascii=False)}\n"
        buttons = [
            [InlineKeyboardButton(text="✅ Одобрить", callback_data=f"pres_app_approve|{app_id}")],
            [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"pres_app_reject|{app_id}")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="pres_apps")],
        ]
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("pres_app_approve|"))
async def pres_app_approve(callback: types.CallbackQuery):
    try:
        if not await has_role_by_username(callback.from_user.username, "president"):
            await callback.answer("Только Президент.", show_alert=True)
            return
        app_id = int(callback.data.split("|")[1])
        app = await get_application(app_id)
        if not app:
            await callback.answer("Не найдена.", show_alert=True)
            return
        data = app["data"]
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except Exception:
                data = {}
        if app["type"] == "citizenship":
            user_id = data.get("user_id")
            username = app["author_username"]
            if username:
                async with db_pool.acquire() as conn:
                    subj = await conn.fetchrow("SELECT id FROM subjects WHERE username = $1", username)
                    if not subj:
                        await conn.execute("""
                            INSERT INTO subjects (user_id, username, full_name, is_citizen)
                            VALUES ($1, $2, $3, TRUE)
                            ON CONFLICT (username) DO UPDATE SET is_citizen = TRUE
                        """, user_id, username, app["author_name"] or "Новый субъект")
                    else:
                        await conn.execute("UPDATE subjects SET is_citizen = TRUE WHERE username = $1", username)
        elif app["type"] == "create_party":
            name = data.get("name")
            emoji = data.get("emoji", "🎭")
            description = data.get("description", "")
            leader = app["author_username"]
            existing = await get_party_by_name(name)
            if not existing:
                await create_party(name, emoji, description, leader)
                await add_news(f"🎭 Создана партия «{name}» {emoji}")
                await add_reputation(leader, REP_RULES["party_created"])
        elif app["type"] == "join_party":
            pid = data.get("party_id")
            if pid:
                await add_party_member(pid, app["author_username"])
        await approve_application(app_id, callback.from_user.id)
        await add_reputation(app["author_username"], REP_RULES["application_approved"])
        await callback.message.edit_text(f"✅ Заявка #{app_id} одобрена.", reply_markup=build_president_keyboard())
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("pres_app_reject|"))
async def pres_app_reject(callback: types.CallbackQuery):
    try:
        if not await has_role_by_username(callback.from_user.username, "president"):
            await callback.answer("Только Президент.", show_alert=True)
            return
        app_id = int(callback.data.split("|")[1])
        app = await get_application(app_id)
        await reject_application(app_id, callback.from_user.id, "Отклонено Президентом")
        if app:
            await add_reputation(app["author_username"], REP_RULES["application_rejected"])
        await callback.message.edit_text(f"❌ Заявка #{app_id} отклонена.", reply_markup=build_president_keyboard())
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "pres_ministers")
async def pres_ministers(callback: types.CallbackQuery):
    try:
        if not await has_role_by_username(callback.from_user.username, "president"):
            await callback.answer("Только Президент.", show_alert=True)
            return
        async with db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT s.full_name, s.username FROM subjects s
                JOIN subject_roles sr ON sr.subject_id = s.id
                JOIN roles r ON r.id = sr.role_id
                WHERE r.code IN ('minister', 'premier', 'cbank', 'advisor')
                ORDER BY r.id
            """)
        if not rows:
            await callback.message.edit_text("⚖️ Министров нет.", reply_markup=build_president_keyboard())
            await callback.answer()
            return
        text = "━━━━━━━━━━━━━━━━━━━━━\n⚖️ МИНИСТРЫ\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        for r in rows:
            text += f"• {r['full_name']} ({r['username']})\n"
        await callback.message.edit_text(text, reply_markup=build_president_keyboard())
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "pres_duma_start")
async def pres_duma_start(callback: types.CallbackQuery, state: FSMContext):
    try:
        if not await has_role_by_username(callback.from_user.username, "president"):
            await callback.answer("Только Президент.", show_alert=True)
            return
        active = await get_active_duma_election()
        if active:
            await callback.answer("Выборы в ГосДуму уже идут!", show_alert=True)
            return
        await callback.message.answer(
            "🗳 НАЗНАЧЕНИЕ ВЫБОРОВ В ГОСДУМУ\n\n"
            "Отправь ДАТУ ОКОНЧАНИЯ в формате:\n"
            "ГГГГ-ММ-ДД ЧЧ:ММ\n\nНапример: 2027-01-15 20:00"
        )
        await state.set_state(ElectionForm.waiting_date_end)
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.message(ElectionForm.waiting_date_end)
async def duma_date_end(message: types.Message, state: FSMContext):
    username = normalize_username(message.from_user.username)
    if not await has_role_by_username(username, "president"):
        await message.answer("⛔ Только Президент.")
        await state.clear()
        return
    try:
        dt = datetime.strptime(message.text.strip(), "%Y-%m-%d %H:%M")
        dt = dt.replace(tzinfo=MSK)
    except Exception:
        await message.answer("Неверный формат. Попробуй: 2027-01-15 20:00")
        return
    election = await start_duma_election(dt)
    await add_news(f"🗳 Президент назначил выборы в ГосДуму! До {dt.strftime('%d.%m.%Y %H:%M')} МСК")
    parties = await get_all_parties()
    await message.answer(
        f"✅ Выборы в ГосДуму назначены!\n\nОкончание: {dt.strftime('%d.%m.%Y %H:%M')} МСК\n"
        f"Партий участвует: {len(parties)}\n\n"
        "Голосование — командой /duma"
    )
    await state.clear()


@dp.callback_query(lambda c: c.data == "pres_duma_session")
async def pres_duma_session(callback: types.CallbackQuery):
    try:
        if not await has_role_by_username(callback.from_user.username, "president"):
            await callback.answer("Только Президент.", show_alert=True)
            return
        await callback.message.edit_text(
            "🏛 Собрание ГосДумы созывается **депутатами**.\n\n"
            "Если ты депутат — используй /duma_session.",
            reply_markup=build_president_keyboard()
        )
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "pres_address")
async def pres_address(callback: types.CallbackQuery, state: FSMContext):
    try:
        if not await has_role_by_username(callback.from_user.username, "president"):
            await callback.answer("Только Президент.", show_alert=True)
            return
        await callback.message.answer("📜 Отправь текст ОБРАЩЕНИЯ К НАРОДУ.")
        await state.set_state(NewsForm.waiting_text)
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


# ===== КОМАНДЫ ЗАКОНОВ (депутатам) =====
@dp.message(Command("law"))
async def cmd_law(message: types.Message, state: FSMContext):
    user = message.from_user
    username = normalize_username(user.username)
    if not await has_role_by_username(username, "deputy"):
        await message.answer("❌ Только депутаты ГосДумы могут вносить законы.")
        return
    await message.answer("📜 ВНЕСЕНИЕ ЗАКОНА\n\nШаг 1/2. Отправь НАЗВАНИЕ.")
    await state.set_state(LawForm.waiting_title)


@dp.message(LawForm.waiting_title)
async def law_get_title(message: types.Message, state: FSMContext):
    title = message.text.strip() if message.text else ""
    if len(title) < 3:
        await message.answer("Слишком коротко. Попробуй снова.")
        return
    await state.update_data(law_title=title)
    await message.answer(f"Название: {title}\n\nШаг 2/2. Отправь ОПИСАНИЕ закона.")
    await state.set_state(LawForm.waiting_description)


@dp.message(LawForm.waiting_description)
async def law_get_description(message: types.Message, state: FSMContext):
    description = message.text.strip() if message.text else ""
    data = await state.get_data()
    title = data.get("law_title")
    user = message.from_user
    username = normalize_username(user.username)
    deadline = now_msk() + timedelta(days=1)
    law = await create_law(title, description, username, deadline)
    await add_news(f"📜 Внесён законопроект «{title}» от {username}")
    await message.answer(f"✅ Законопроект создан!\n\n#{law['id']} «{title}»\n\nГолосование — /laws")
    await state.clear()


@dp.message(Command("duma_session"))
async def cmd_duma_session(message: types.Message, state: FSMContext):
    user = message.from_user
    username = normalize_username(user.username)
    if not await has_role_by_username(username, "deputy"):
        await message.answer("❌ Только депутаты ГосДумы могут созвать собрание.")
        return
    active = await get_duma_session()
    if active:
        await message.answer("Собрание уже идёт! Голосуйте в /laws.")
        return
    laws = await get_all_laws(status="duma")
    if not laws:
        await message.answer("Нет законопроектов на голосование.")
        return
    buttons = []
    for l in laws:
        buttons.append([InlineKeyboardButton(text=f"#{l['id']} {l['title'][:30]}", callback_data=f"duma_session_start|{l['id']}")])
    await message.answer(
        "🏛 СОЗЫВ СОБРАНИЯ ГОСДУМЫ\n\nВыбери законопроект:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@dp.callback_query(lambda c: c.data.startswith("duma_session_start|"))
async def duma_session_start(callback: types.CallbackQuery):
    try:
        username = normalize_username(callback.from_user.username)
        if not await has_role_by_username(username, "deputy"):
            await callback.answer("Только депутаты.", show_alert=True)
            return
        lid = int(callback.data.split("|")[1])
        law = await get_law(lid)
        if not law:
            await callback.answer("Закон не найден.", show_alert=True)
            return
        deadline = now_msk() + timedelta(days=1)
        await create_duma_session(lid, username, deadline)
        # Рассылаем всем депутатам
        async with db_pool.acquire() as conn:
            deputies = await conn.fetch("""
                SELECT s.user_id FROM subjects s
                JOIN subject_roles sr ON sr.subject_id = s.id
                JOIN roles r ON r.id = sr.role_id
                WHERE r.code = 'deputy' AND s.user_id IS NOT NULL
            """)
        text = (
            f"🏛 ПОВЕСТКА ДНЯ ГОСДУМЫ\n\n"
            f"Законопроект #{lid}: «{law['title']}»\n\n{law['description']}\n\n"
            f"Автор: {law['author_username']}\n"
            f"Дедлайн: {deadline.strftime('%d.%m.%Y %H:%M')} МСК\n\n"
            f"Голосуй: /laws"
        )
        for d in deputies:
            try:
                await callback.bot.send_message(d["user_id"], text)
            except Exception as e:
                print(f"Не смог уведомить {d['user_id']}: {e}")
        await callback.message.edit_text(f"✅ Собрание созвано. Повестка отправлена {len(deputies)} депутатам.")
        await add_news(f"🏛 Собрание ГосДумы: законопроект «{law['title']}»")
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("law_view|"))
async def law_view(callback: types.CallbackQuery):
    try:
        lid = int(callback.data.split("|")[1])
        law = await get_law(lid)
        if not law:
            await callback.answer("Не найден.", show_alert=True)
            return
        text = f"📜 ЗАКОН #{lid}\n\n«{law['title']}»\n\n{law['description']}\n\n"
        text += f"Автор: {law['author_username']}\nСтатус: {law['status']}\n"
        text += f"ГосДума: за {law['duma_votes_for']}, против {law['duma_votes_against']}"
        buttons = []
        username = normalize_username(callback.from_user.username)
        if law["status"] == "duma" and await has_role_by_username(username, "deputy"):
            buttons.append([InlineKeyboardButton(text="✅ За", callback_data=f"law_vote|{lid}|for")])
            buttons.append([InlineKeyboardButton(text="❌ Против", callback_data=f"law_vote|{lid}|against")])
        buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="laws_back")])
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "laws_back")
async def laws_back(callback: types.CallbackQuery):
    try:
        laws = await get_all_laws()
        status_names = {"duma": "🟡", "government": "🟠", "president": "🔵", "approved": "🟢", "vetoed": "🔴"}
        buttons = []
        for l in laws[:15]:
            buttons.append([InlineKeyboardButton(text=f"#{l['id']} {l['title'][:25]} — {status_names.get(l['status'], '')}", callback_data=f"law_view|{l['id']}")])
        await callback.message.edit_text("📜 ЗАКОНЫ ДКД", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("law_vote|"))
async def law_vote(callback: types.CallbackQuery):
    try:
        parts = callback.data.split("|")
        lid = int(parts[1])
        vote = parts[2]
        username = normalize_username(callback.from_user.username)
        ok, msg = await vote_law(lid, username, vote)
        if not ok:
            await callback.answer(msg, show_alert=True)
            return
        await callback.answer("Голос принят!")
        law = await get_law(lid)
        async with db_pool.acquire() as conn:
            total_deputies = await conn.fetchval("SELECT COUNT(*) FROM subject_roles sr JOIN roles r ON r.id = sr.role_id WHERE r.code = 'deputy'")
            voted = await conn.fetchval("SELECT COUNT(*) FROM law_votes WHERE law_id = $1", lid)
        if voted >= total_deputies and total_deputies > 0:
            await update_law_status(lid, "government")
            await add_news(f"📜 Закон «{law['title']}» прошёл ГосДуму")
            await callback.message.answer("✅ Все проголосовали. Закон направлен в Правительство.")
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


# ===== ВЫБОРЫ В ГОСДУМУ (голосование) =====
@dp.message(Command("duma"))
async def cmd_duma(message: types.Message):
    user = message.from_user
    username = normalize_username(user.username)
    subject = await get_subject(user.id, username)
    if not subject:
        await message.answer("❌ Только для зарегистрированных.")
        return
    election = await get_active_duma_election()
    if not election:
        await message.answer("Выборы в ГосДуму сейчас не идут.")
        return
    if await has_role_by_username(username, "party_leader"):
        await message.answer("⚠️ Лидеры партий не голосуют.")
        return
    parties = await get_all_parties()
    if not parties:
        await message.answer("Нет партий.")
        return
    buttons = []
    for p in parties:
        buttons.append([InlineKeyboardButton(text=f"{p['emoji']} {p['name']}", callback_data=f"duma_vote|{election['id']}|{p['id']}")])
    await message.answer(
        f"🗳 ГОЛОСОВАНИЕ В ГОСДУМУ\n\nОкончание: {election['ends_at'].strftime('%d.%m.%Y %H:%M')} МСК\n\nВыбери партию:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@dp.callback_query(lambda c: c.data.startswith("duma_vote|"))
async def duma_vote(callback: types.CallbackQuery):
    try:
        parts = callback.data.split("|")
        eid = int(parts[1])
        pid = int(parts[2])
        username = normalize_username(callback.from_user.username)
        if await has_role_by_username(username, "party_leader"):
            await callback.answer("Лидеры партий не голосуют.", show_alert=True)
            return
        ok, msg = await vote_duma(eid, username, pid)
        if not ok:
            await callback.answer(msg, show_alert=True)
            return
        party = await get_party(pid)
        await callback.message.edit_text(f"✅ Голос за «{party['name']}» принят!")
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


# ===== ПАРТИИ =====
@dp.callback_query(lambda c: c.data.startswith("party_view|"))
async def party_view(callback: types.CallbackQuery):
    try:
        pid = int(callback.data.split("|")[1])
        party = await get_party(pid)
        if not party:
            await callback.answer("Партия не найдена.", show_alert=True)
            return
        text = await build_party_detail_text(party)
        username = normalize_username(callback.from_user.username)
        user_party = await get_user_party(username)
        buttons = []
        if user_party and user_party["id"] == pid:
            buttons.append([InlineKeyboardButton(text="🚪 Выйти", callback_data=f"party_leave|{pid}")])
        elif not user_party:
            buttons.append([InlineKeyboardButton(text="✍️ Вступить", callback_data=f"party_join|{pid}")])
        buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="party_back")])
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "party_back")
async def party_back(callback: types.CallbackQuery):
    try:
        parties = await get_all_parties()
        text = await build_parties_list_text()
        buttons = [[InlineKeyboardButton(text=f"{p['emoji']} {p['name']}", callback_data=f"party_view|{p['id']}")] for p in parties]
        buttons.append([InlineKeyboardButton(text="➕ Создать", callback_data="party_create")])
        buttons.append([InlineKeyboardButton(text="🏆 Кладбище", callback_data="party_graveyard")])
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "party_graveyard")
async def party_graveyard(callback: types.CallbackQuery):
    try:
        async with db_pool.acquire() as conn:
            dead = await conn.fetch("SELECT * FROM parties WHERE status = 'dissolved' ORDER BY id DESC")
        if not dead:
            await callback.message.edit_text("🏆 Кладбище пустое.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="party_back")]]))
            await callback.answer()
            return
        text = "━━━━━━━━━━━━━━━━━━━━━\n🏆 КЛАДБИЩЕ ПАРТИЙ\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        for p in dead:
            text += f"💀 {p['emoji']} {p['name']} (RIP)\n"
        buttons = [[InlineKeyboardButton(text="◀️ Назад", callback_data="party_back")]]
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("party_join|"))
async def party_join(callback: types.CallbackQuery):
    try:
        pid = int(callback.data.split("|")[1])
        username = normalize_username(callback.from_user.username)
        subject = await get_subject(callback.from_user.id, username)
        if not subject:
            await callback.answer("Только для зарегистрированных.", show_alert=True)
            return
        user_party = await get_user_party(username)
        if user_party:
            await callback.answer("Ты уже в партии.", show_alert=True)
            return
        party = await get_party(pid)
        if not party:
            await callback.answer("Партия не найдена.", show_alert=True)
            return
        await create_application("join_party", username, subject["full_name"], party["leader_username"], {"party_id": pid, "party_name": party["name"]})
        await add_reputation(username, REP_RULES["application"])
        await callback.message.answer(f"✍️ Заявка в партию «{party['name']}» отправлена лидеру.")
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("party_leave|"))
async def party_leave(callback: types.CallbackQuery):
    try:
        username = normalize_username(callback.from_user.username)
        await remove_party_member(username)
        await callback.message.edit_text("🚪 Ты покинул партию.")
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "party_create")
async def party_create(callback: types.CallbackQuery, state: FSMContext):
    try:
        username = normalize_username(callback.from_user.username)
        subject = await get_subject(callback.from_user.id, username)
        if not subject:
            await callback.answer("Только для зарегистрированных.", show_alert=True)
            return
        if await get_user_party(username):
            await callback.answer("Ты уже в партии.", show_alert=True)
            return
        await callback.message.answer("➕ СОЗДАНИЕ ПАРТИИ\n\nШаг 1/3. Отправь НАЗВАНИЕ.")
        await state.set_state(PartyForm.waiting_name)
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.message(PartyForm.waiting_name)
async def party_get_name(message: types.Message, state: FSMContext):
    name = message.text.strip() if message.text else ""
    if len(name) < 2 or len(name) > 50:
        await message.answer("Название 2-50 символов. Попробуй снова.")
        return
    existing = await get_party_by_name(name)
    if existing:
        await message.answer("Партия с таким названием уже есть. Придумай другое.")
        return
    await state.update_data(party_name=name)
    await message.answer(f"Название: {name}\n\nШаг 2/3. Отправь ЭМОДЗИ.")
    await state.set_state(PartyForm.waiting_emoji)


@dp.message(PartyForm.waiting_emoji)
async def party_get_emoji(message: types.Message, state: FSMContext):
    emoji = message.text.strip() if message.text else "🎭"
    if len(emoji) > 5:
        await message.answer("Один эмодзи. Попробуй снова.")
        return
    await state.update_data(party_emoji=emoji)
    await message.answer(f"Эмодзи: {emoji}\n\nШаг 3/3. Отправь ПРОГРАММУ.")
    await state.set_state(PartyForm.waiting_description)


@dp.message(PartyForm.waiting_description)
async def party_get_description(message: types.Message, state: FSMContext):
    description = message.text.strip() if message.text else ""
    data = await state.get_data()
    name = data.get("party_name")
    emoji = data.get("party_emoji", "🎭")
    username = normalize_username(message.from_user.username)
    subject = await get_subject(message.from_user.id, username)
    async with db_pool.acquire() as conn:
        president = await conn.fetchrow("SELECT s.username FROM subjects s JOIN subject_roles sr ON sr.subject_id = s.id JOIN roles r ON r.id = sr.role_id WHERE r.code = 'president' LIMIT 1")
    target = president["username"] if president else None
    await create_application("create_party", username, subject["full_name"] if subject else message.from_user.full_name, target, {"name": name, "emoji": emoji, "description": description})
    await add_reputation(username, REP_RULES["application"])
    await message.answer(f"✅ Заявка на партию отправлена Президенту.\n\nНазвание: {name}\nЭмодзи: {emoji}")
    await state.clear()


# ===== УКАЗ =====
@dp.message(Command("decree"))
async def cmd_decree(message: types.Message, state: FSMContext):
    username = normalize_username(message.from_user.username)
    if not await has_role_by_username(username, "president") and not await is_admin_active(message.from_user.id):
        await message.answer("❌ Только Президент или Админ.")
        return
    await message.answer("📢 СОЗДАНИЕ УКАЗА\n\nШаг 1/3. Отправь ЗАГОЛОВОК.")
    await state.set_state(DecreeForm.waiting_title)


@dp.message(DecreeForm.waiting_title)
async def decree_title(message: types.Message, state: FSMContext):
    title = message.text.strip() if message.text else ""
    if len(title) < 3:
        await message.answer("Слишком короткий. Попробуй снова.")
        return
    await state.update_data(decree_title=title)
    await message.answer(f"Заголовок: {title}\n\nШаг 2/3. Отправь ТЕКСТ указа.")
    await state.set_state(DecreeForm.waiting_text)


@dp.message(DecreeForm.waiting_text)
async def decree_text(message: types.Message, state: FSMContext):
    text = message.text.strip() if message.text else ""
    await state.update_data(decree_text=text)
    await message.answer("Шаг 3/3. Секретный? Отправь @username или «нет».")
    await state.set_state(DecreeForm.waiting_secret)


@dp.message(DecreeForm.waiting_secret)
async def decree_secret(message: types.Message, state: FSMContext):
    answer = message.text.strip() if message.text else "нет"
    is_secret = False
    secret_for = None
    if answer.lower() != "нет" and answer.startswith("@"):
        is_secret = True
        secret_for = normalize_username(answer)
    data = await state.get_data()
    title = data.get("decree_title")
    text = data.get("decree_text")
    username = normalize_username(message.from_user.username)
    await create_decree(title, text, username, is_secret, secret_for)
    if is_secret:
        await add_news(f"🔒 Подписан секретный указ (для {secret_for})")
        await message.answer(f"✅ Секретный указ «{title}» создан.")
    else:
        await add_news(f"📢 Подписан указ: «{title}»")
        subjects = await get_all_subjects()
        for s in subjects:
            if s["user_id"] and s["user_id"] > 0:
                try:
                    await message.bot.send_message(s["user_id"], f"📢 УКАЗ ПРЕЗИДЕНТА\n\n{title}\n\n{text}")
                except Exception:
                    pass
        await message.answer(f"✅ Указ «{title}» разослан.")
    await state.clear()


# ===== КОДОВОЕ СЛОВО =====
@dp.message(lambda m: m.text and not m.text.startswith("/") and m.video is None)
async def handle_text(message: types.Message):
    user = message.from_user
    username = normalize_username(user.username)
    subject = await get_subject(user.id, username)
    if subject:
        return
    if check_secret_word(message.text):
        if not username:
            await message.answer("❌ У тебя нет username.")
            return
        async with db_pool.acquire() as conn:
            president = await conn.fetchrow("SELECT s.username FROM subjects s JOIN subject_roles sr ON sr.subject_id = s.id JOIN roles r ON r.id = sr.role_id WHERE r.code = 'president' LIMIT 1")
        target = president["username"] if president else None
        await create_application("citizenship", username, user.full_name, target, {"user_id": user.id, "telegram_name": user.full_name})
        await message.answer("✅ Кодовое слово принято!\n\nЗаявка отправлена Президенту.")
        return
    await message.answer("❌ Неверное кодовое слово.\n\nПодсказка: два слова, связанные с Эфиопией и Богом.")


# ===== АДМИН-ПАНЕЛЬ =====
async def admin_check_and_active(callback):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Только админ.", show_alert=True)
        return False
    if not await is_admin_active(callback.from_user.id):
        await callback.answer("🔒 Админ-режим не активен.", show_alert=True)
        return False
    return True


@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Только админ.")
        return
    active = await is_admin_active(message.from_user.id)
    status = "🔓 АКТИВЕН" if active else "🔒 НЕ АКТИВЕН"
    await message.answer(f"━━━━━━━━━━━━━━━━━━━━━\n🛠 АДМИН-ПАНЕЛЬ ДКД\n━━━━━━━━━━━━━━━━━━━━━\n\nСтатус: {status}\n\nВыбери действие:", reply_markup=build_admin_keyboard(active))


@dp.callback_query(lambda c: c.data == "admin_toggle")
async def admin_toggle(callback: types.CallbackQuery):
    try:
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("Только админ.", show_alert=True)
            return
        active = await is_admin_active(callback.from_user.id)
        if active:
            await deactivate_admin(callback.from_user.id)
            await callback.answer("🔒 Выключено", show_alert=True)
        else:
            await activate_admin(callback.from_user.id)
            await callback.answer("🔓 Включено", show_alert=True)
        active = await is_admin_active(callback.from_user.id)
        status = "🔓 АКТИВЕН" if active else "🔒 НЕ АКТИВЕН"
        await callback.message.edit_text(f"━━━━━━━━━━━━━━━━━━━━━\n🛠 АДМИН-ПАНЕЛЬ ДКД\n━━━━━━━━━━━━━━━━━━━━━\n\nСтатус: {status}\n\nВыбери действие:", reply_markup=build_admin_keyboard(active))
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_back")
async def admin_back(callback: types.CallbackQuery):
    try:
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("Только админ.", show_alert=True)
            return
        active = await is_admin_active(callback.from_user.id)
        status = "🔓 АКТИВЕН" if active else "🔒 НЕ АКТИВЕН"
        await callback.message.edit_text(f"━━━━━━━━━━━━━━━━━━━━━\n🛠 АДМИН-ПАНЕЛЬ ДКД\n━━━━━━━━━━━━━━━━━━━━━\n\nСтатус: {status}\n\nВыбери действие:", reply_markup=build_admin_keyboard(active))
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


# ===== АДМИН: СУБЪЕКТЫ =====
@dp.callback_query(lambda c: c.data == "admin_subjects")
async def admin_subjects(callback: types.CallbackQuery):
    try:
        if not await admin_check_and_active(callback):
            return
        await callback.message.edit_text("━━━━━━━━━━━━━━━━━━━━━\n👥 СУБЪЕКТЫ\n━━━━━━━━━━━━━━━━━━━━━\n\nВыбери действие:", reply_markup=build_admin_subjects_keyboard())
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_subjects_list")
async def admin_subjects_list(callback: types.CallbackQuery):
    try:
        if not await admin_check_and_active(callback):
            return
        kb = await build_admin_subjects_list_keyboard()
        await callback.message.edit_text("👥 СУБЪЕКТЫ\n\nВыбери субъекта:", reply_markup=kb)
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("admin_subj_view|"))
async def admin_subj_view(callback: types.CallbackQuery):
    try:
        if not await admin_check_and_active(callback):
            return
        sid = int(callback.data.split("|")[1])
        async with db_pool.acquire() as conn:
            subject = await conn.fetchrow("SELECT * FROM subjects WHERE id = $1", sid)
        if not subject:
            await callback.answer("Не найден.", show_alert=True)
            return
        roles = await get_subject_roles(subject["id"])
        user_party = await get_user_party(subject["username"])
        text = build_subject_profile_text_sync(subject, roles, user_party, False)
        await callback.message.answer(text)
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_assign_role_subj")
async def admin_assign_role_subj(callback: types.CallbackQuery):
    try:
        if not await admin_check_and_active(callback):
            return
        kb = await build_admin_assign_role_subj_keyboard()
        await callback.message.edit_text("➕ ВЫДАТЬ ДОЛЖНОСТЬ\n\nВыбери субъекта:", reply_markup=kb)
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("admin_assign_subj|"))
async def admin_assign_subj(callback: types.CallbackQuery):
    try:
        if not await admin_check_and_active(callback):
            return
        sid = int(callback.data.split("|")[1])
        kb = await build_admin_assign_role_keyboard(sid)
        await callback.message.edit_text("➕ ВЫБЕРИ ДОЛЖНОСТЬ", reply_markup=kb)
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("admin_assign_role|"))
async def admin_assign_role(callback: types.CallbackQuery):
    try:
        if not await admin_check_and_active(callback):
            return
        parts = callback.data.split("|")
        sid = int(parts[1])
        rid = int(parts[2])
        ok, msg = await assign_role(sid, rid, ADMIN_ID)
        if ok:
            async with db_pool.acquire() as conn:
                subject = await conn.fetchrow("SELECT * FROM subjects WHERE id = $1", sid)
                role = await conn.fetchrow("SELECT * FROM roles WHERE id = $1", rid)
            text = f"✅ ГОТОВО!\n\n{subject['full_name']} назначен: {role['emoji']} {role['name']}"
            await add_news(f"👑 {subject['full_name']} назначен: {role['name']}")
            try:
                await callback.message.edit_text(text)
            except Exception:
                await callback.message.answer(text)
        else:
            await callback.message.answer(f"❌ {msg}")
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_remove_role_subj")
async def admin_remove_role_subj(callback: types.CallbackQuery):
    try:
        if not await admin_check_and_active(callback):
            return
        kb = await build_admin_remove_role_subj_keyboard()
        await callback.message.edit_text("➖ СНЯТЬ ДОЛЖНОСТЬ\n\nВыбери субъекта:", reply_markup=kb)
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("admin_remove_subj|"))
async def admin_remove_subj(callback: types.CallbackQuery):
    try:
        if not await admin_check_and_active(callback):
            return
        sid = int(callback.data.split("|")[1])
        kb = await build_admin_remove_role_keyboard(sid)
        await callback.message.edit_text("➖ ВЫБЕРИ ДОЛЖНОСТЬ", reply_markup=kb)
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("admin_remove_role|"))
async def admin_remove_role(callback: types.CallbackQuery):
    try:
        if not await admin_check_and_active(callback):
            return
        parts = callback.data.split("|")
        sid = int(parts[1])
        rid = int(parts[2])
        await remove_role(sid, rid)
        await callback.message.edit_text("✅ Должность снята.")
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_roles")
async def admin_roles(callback: types.CallbackQuery):
    try:
        if not await admin_check_and_active(callback):
            return
        await callback.message.answer(await build_roles_list_text())
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


# ===== АДМИН: ЗАКОНЫ =====
@dp.callback_query(lambda c: c.data == "admin_laws")
async def admin_laws(callback: types.CallbackQuery):
    try:
        if not await admin_check_and_active(callback):
            return
        await callback.message.edit_text("━━━━━━━━━━━━━━━━━━━━━\n📜 ЗАКОНЫ\n━━━━━━━━━━━━━━━━━━━━━", reply_markup=build_admin_laws_keyboard())
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_laws_list")
async def admin_laws_list(callback: types.CallbackQuery):
    try:
        if not await admin_check_and_active(callback):
            return
        laws = await get_all_laws()
        if not laws:
            await callback.message.edit_text("📜 Законов нет.")
            await callback.answer()
            return
        status_names = {"duma": "🟡 ГосДума", "government": "🟠 Правительство", "president": "🔵 Президент", "approved": "🟢 Принят", "vetoed": "🔴 Вето"}
        buttons = []
        for l in laws:
            buttons.append([InlineKeyboardButton(text=f"#{l['id']} {l['title'][:25]} — {status_names.get(l['status'], '')}", callback_data=f"admin_law_view|{l['id']}")])
        buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_laws")])
        await callback.message.edit_text("📜 ЗАКОНЫ", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("admin_law_view|"))
async def admin_law_view(callback: types.CallbackQuery):
    try:
        if not await admin_check_and_active(callback):
            return
        lid = int(callback.data.split("|")[1])
        law = await get_law(lid)
        if not law:
            await callback.answer("Не найден.", show_alert=True)
            return
        text = f"📜 ЗАКОН #{lid}\n\n«{law['title']}»\n\n{law['description']}\n\nСтатус: {law['status']}\nГосДума: за {law['duma_votes_for']}, против {law['duma_votes_against']}"
        buttons = []
        if law["status"] == "government":
            buttons.append([InlineKeyboardButton(text="✅ Одобрено Правительством", callback_data=f"admin_law_gov|{lid}")])
            buttons.append([InlineKeyboardButton(text="❌ Отклонено", callback_data=f"admin_law_gov_reject|{lid}")])
        if law["status"] == "president":
            buttons.append([InlineKeyboardButton(text="✅ Подписать", callback_data=f"admin_law_sign|{lid}")])
            buttons.append([InlineKeyboardButton(text="❌ Вето", callback_data=f"admin_law_veto|{lid}")])
        buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_laws_list")])
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("admin_law_gov|"))
async def admin_law_gov(callback: types.CallbackQuery):
    try:
        if not await admin_check_and_active(callback):
            return
        lid = int(callback.data.split("|")[1])
        await update_law_status(lid, "president")
        await callback.message.edit_text("✅ Направлено Президенту.")
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("admin_law_gov_reject|"))
async def admin_law_gov_reject(callback: types.CallbackQuery):
    try:
        if not await admin_check_and_active(callback):
            return
        lid = int(callback.data.split("|")[1])
        await update_law_status(lid, "vetoed")
        await callback.message.edit_text("❌ Отклонено Правительством.")
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("admin_law_sign|"))
async def admin_law_sign(callback: types.CallbackQuery):
    try:
        if not await admin_check_and_active(callback):
            return
        lid = int(callback.data.split("|")[1])
        law = await get_law(lid)
        await update_law_status(lid, "approved")
        await add_news(f"🟢 Закон «{law['title']}» подписан Президентом!")
        await add_reputation(law["author_username"], REP_RULES["law_approved"])
        await callback.message.edit_text("✅ Закон подписан.")
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("admin_law_veto|"))
async def admin_law_veto(callback: types.CallbackQuery):
    try:
        if not await admin_check_and_active(callback):
            return
        lid = int(callback.data.split("|")[1])
        law = await get_law(lid)
        await update_law_status(lid, "vetoed")
        await add_reputation(law["author_username"], REP_RULES["law_rejected"])
        await callback.message.edit_text("❌ Вето.")
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


# ===== АДМИН: УКАЗЫ =====
@dp.callback_query(lambda c: c.data == "admin_decrees")
async def admin_decrees(callback: types.CallbackQuery):
    try:
        if not await admin_check_and_active(callback):
            return
        await callback.message.edit_text("📢 УКАЗЫ", reply_markup=build_admin_decrees_keyboard())
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_decrees_list")
async def admin_decrees_list(callback: types.CallbackQuery):
    try:
        if not await admin_check_and_active(callback):
            return
        decrees = await get_all_decrees()
        if not decrees:
            await callback.message.edit_text("📢 Указов нет.")
            await callback.answer()
            return
        text = "📢 УКАЗЫ\n\n"
        for d in decrees:
            marker = "🔒" if d["is_secret"] else "📢"
            text += f"{marker} #{d['id']} {d['title']}\n"
        buttons = [[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_decrees")]]
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


# ===== АДМИН: ГАЗЕТА =====
@dp.callback_query(lambda c: c.data == "admin_news")
async def admin_news(callback: types.CallbackQuery):
    try:
        if not await admin_check_and_active(callback):
            return
        await callback.message.edit_text("📰 ГАЗЕТА", reply_markup=build_admin_news_keyboard())
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_news_list")
async def admin_news_list(callback: types.CallbackQuery):
    try:
        if not await admin_check_and_active(callback):
            return
        news = await get_news(20)
        if not news:
            await callback.message.edit_text("📰 Пусто.")
            await callback.answer()
            return
        text = "📰 ГАЗЕТА\n\n"
        for n in news:
            dt = n["created_at"].strftime("%d.%m %H:%M") if n["created_at"] else "—"
            text += f"[{dt}] {n['text']}\n\n"
        buttons = [[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_news")]]
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_news_add")
async def admin_news_add(callback: types.CallbackQuery, state: FSMContext):
    try:
        if not await admin_check_and_active(callback):
            return
        await callback.message.answer("📰 Отправь текст новости.")
        await state.set_state(NewsForm.waiting_text)
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.message(NewsForm.waiting_text)
async def news_text(message: types.Message, state: FSMContext):
    text = message.text.strip() if message.text else ""
    if len(text) < 3:
        await message.answer("Слишком коротко.")
        return
    await add_news(f"📢 {text}", source="admin")
    await message.answer("✅ Новость добавлена.")
    await state.clear()


# ===== АДМИН: ГОСДУМА =====
@dp.callback_query(lambda c: c.data == "admin_duma")
async def admin_duma(callback: types.CallbackQuery):
    try:
        if not await admin_check_and_active(callback):
            return
        await callback.message.edit_text("🗳 ГОСДУМА", reply_markup=build_admin_duma_keyboard())
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_duma_start")
async def admin_duma_start(callback: types.CallbackQuery, state: FSMContext):
    try:
        if not await admin_check_and_active(callback):
            return
        active = await get_active_duma_election()
        if active:
            await callback.answer("Уже идут.", show_alert=True)
            return
        await callback.message.answer("🗳 Отправь ДАТУ окончания: ГГГГ-ММ-ДД ЧЧ:ММ\nНапример: 2027-01-15 20:00")
        await state.set_state(ElectionForm.waiting_date_end)
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_duma_results")
async def admin_duma_results(callback: types.CallbackQuery):
    try:
        if not await admin_check_and_active(callback):
            return
        async with db_pool.acquire() as conn:
            elections = await conn.fetch("SELECT * FROM duma_elections ORDER BY id DESC LIMIT 5")
        if not elections:
            await callback.message.edit_text("Выборов не было.")
            await callback.answer()
            return
        text = "🗳 РЕЗУЛЬТАТЫ ГОСДУМЫ\n\n"
        for e in elections:
            res = e["results"]
            if isinstance(res, str):
                try:
                    res = json.loads(res)
                except Exception:
                    res = []
            text += f"#{e['id']} — {e['status']}\n"
            if isinstance(res, list):
                for r in res:
                    text += f"  {r.get('place')}. {r['party']} ({r['votes']} голосов) — депутаты: {', '.join(r.get('deputies', []))}\n"
            text += "\n"
        buttons = [[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_duma")]]
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


# ===== АДМИН: ГРАЖДАНСТВО =====
@dp.callback_query(lambda c: c.data == "admin_citizen")
async def admin_citizen(callback: types.CallbackQuery):
    try:
        if not await admin_check_and_active(callback):
            return
        apps = await get_pending_applications()
        citizens = [a for a in apps if a["type"] == "citizenship"]
        if not citizens:
            await callback.message.edit_text("👤 Заявок нет.", reply_markup=build_admin_keyboard(True))
            await callback.answer()
            return
        buttons = []
        for a in citizens:
            buttons.append([InlineKeyboardButton(text=f"#{a['id']} {a['author_username']}", callback_data=f"admin_app_view|{a['id']}")])
        buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")])
        await callback.message.edit_text("👤 ЗАЯВКИ НА ГРАЖДАНСТВО", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


# ===== АДМИН: ВЫБОРЫ =====
@dp.callback_query(lambda c: c.data == "admin_results")
async def admin_results(callback: types.CallbackQuery):
    try:
        if not await admin_check_and_active(callback):
            return
        await callback.message.answer(await build_results_text())
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_status")
async def admin_status(callback: types.CallbackQuery):
    try:
        if not await admin_check_and_active(callback):
            return
        await callback.message.answer(await build_status_text())
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_votes")
async def admin_votes(callback: types.CallbackQuery):
    try:
        if not await admin_check_and_active(callback):
            return
        await callback.message.answer(await build_votes_list_text())
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_add_vote")
async def admin_add_vote(callback: types.CallbackQuery):
    try:
        if not await admin_check_and_active(callback):
            return
        await callback.message.edit_text("✍️ ВНЕСТИ ГОЛОС", reply_markup=build_admin_add_vote_keyboard())
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("admin_addvote_subj|"))
async def admin_addvote_subj(callback: types.CallbackQuery):
    try:
        if not await admin_check_and_active(callback):
            return
        username = callback.data.split("|", 1)[1]
        info = VOTERS.get(username)
        if not info:
            await callback.answer("Не найден.", show_alert=True)
            return
        await callback.message.edit_text(f"✍️ ГОЛОС ЗА: {info['name']}\n\nЗа какого кандидата?", reply_markup=build_admin_add_candidate_keyboard(username))
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("admin_addvote_cand|"))
async def admin_addvote_cand(callback: types.CallbackQuery):
    try:
        if not await admin_check_and_active(callback):
            return
        parts = callback.data.split("|")
        username, cid = parts[1], parts[2]
        info = VOTERS.get(username)
        if not info:
            await callback.answer("Не найден.", show_alert=True)
            return
        await delete_vote_by_username(username)
        await save_vote(-1, username, info["name"], cid, added_by_admin=True)
        try:
            await callback.message.edit_text(f"✅ Голос внесён.\n\n{info['name']} → {CANDIDATES[cid]['name']}")
        except Exception:
            await callback.message.answer(f"✅ Голос внесён: {info['name']} → {CANDIDATES[cid]['name']}")
        await callback.answer("Готово!")
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_del_vote")
async def admin_del_vote(callback: types.CallbackQuery):
    try:
        if not await admin_check_and_active(callback):
            return
        await callback.message.edit_text("🗑 УДАЛИТЬ ГОЛОС", reply_markup=build_admin_del_vote_keyboard())
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("admin_delvote|"))
async def admin_delvote(callback: types.CallbackQuery):
    try:
        if not await admin_check_and_active(callback):
            return
        username = callback.data.split("|", 1)[1]
        info = VOTERS.get(username)
        if not info:
            await callback.answer("Не найден.", show_alert=True)
            return
        await delete_vote_by_username(username)
        try:
            await callback.message.edit_text(f"✅ Голос удалён: {info['name']}")
        except Exception:
            await callback.message.answer(f"✅ Голос удалён: {info['name']}")
        await callback.answer("Готово!")
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_reset_confirm")
async def admin_reset_confirm(callback: types.CallbackQuery):
    try:
        if not await admin_check_and_active(callback):
            return
        await callback.message.edit_text("⚠️ СБРОСИТЬ ВСЁ?", reply_markup=build_admin_confirm_reset_keyboard())
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_reset_yes")
async def admin_reset_yes(callback: types.CallbackQuery):
    try:
        if not await admin_check_and_active(callback):
            return
        await clear_votes()
        await callback.message.edit_text("🔄 Сброшено.")
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


# ===== АДМИН: ПАРТИИ =====
@dp.callback_query(lambda c: c.data == "admin_parties")
async def admin_parties(callback: types.CallbackQuery):
    try:
        if not await admin_check_and_active(callback):
            return
        await callback.message.edit_text("🎭 ПАРТИИ", reply_markup=build_admin_parties_keyboard())
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_parties_list")
async def admin_parties_list(callback: types.CallbackQuery):
    try:
        if not await admin_check_and_active(callback):
            return
        kb = await build_admin_parties_list_keyboard()
        await callback.message.edit_text("🎭 СПИСОК ПАРТИЙ", reply_markup=kb)
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_party_graveyard")
async def admin_party_graveyard(callback: types.CallbackQuery):
    try:
        if not await admin_check_and_active(callback):
            return
        async with db_pool.acquire() as conn:
            dead = await conn.fetch("SELECT * FROM parties WHERE status = 'dissolved' ORDER BY id DESC")
        if not dead:
            await callback.message.edit_text("🏆 Кладбище пустое.", reply_markup=build_admin_parties_keyboard())
            await callback.answer()
            return
        text = "🏆 КЛАДБИЩЕ ПАРТИЙ\n\n"
        for p in dead:
            text += f"💀 {p['emoji']} {p['name']} (RIP)\n"
        buttons = [[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_parties")]]
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("admin_party_view|"))
async def admin_party_view(callback: types.CallbackQuery):
    try:
        if not await admin_check_and_active(callback):
            return
        pid = int(callback.data.split("|")[1])
        party = await get_party(pid)
        if not party:
            await callback.answer("Не найдена.", show_alert=True)
            return
        text = await build_party_detail_text(party) + f"\n\nСтатус: {party['status']}"
        await callback.message.answer(text)
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_create_party")
async def admin_create_party(callback: types.CallbackQuery):
    try:
        if not await admin_check_and_active(callback):
            return
        await callback.message.answer("➕ /make_party НАЗВАНИЕ | ЭМОДЗИ | @лидер | ОПИСАНИЕ")
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_dissolve_party")
async def admin_dissolve_party(callback: types.CallbackQuery):
    try:
        if not await admin_check_and_active(callback):
            return
        kb = await build_admin_dissolve_party_keyboard()
        await callback.message.edit_text("🗑 РАСПУСТИТЬ ПАРТИЮ", reply_markup=kb)
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("admin_dissolve|"))
async def admin_dissolve(callback: types.CallbackQuery):
    try:
        if not await admin_check_and_active(callback):
            return
        pid = int(callback.data.split("|")[1])
        party = await get_party(pid)
        await dissolve_party(pid)
        if party:
            await add_news(f"💀 Партия «{party['name']}» распущена (RIP)")
            await add_reputation(party["leader_username"], REP_RULES["party_dissolved"])
        await callback.message.edit_text("✅ Партия распущена.")
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_change_leader")
async def admin_change_leader(callback: types.CallbackQuery):
    try:
        if not await admin_check_and_active(callback):
            return
        kb = await build_admin_change_leader_keyboard()
        await callback.message.edit_text("👑 СМЕНИТЬ ЛИДЕРА", reply_markup=kb)
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("admin_leader_party|"))
async def admin_leader_party(callback: types.CallbackQuery):
    try:
        if not await admin_check_and_active(callback):
            return
        pid = int(callback.data.split("|")[1])
        kb = await build_admin_leader_subject_keyboard(pid)
        await callback.message.edit_text("👑 НОВЫЙ ЛИДЕР", reply_markup=kb)
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("admin_leader_set|"))
async def admin_leader_set(callback: types.CallbackQuery):
    try:
        if not await admin_check_and_active(callback):
            return
        parts = callback.data.split("|")
        pid = int(parts[1])
        new_leader = parts[2]
        party = await get_party(pid)
        old_leader = party["leader_username"] if party else None
        await change_party_leader(pid, new_leader)
        if old_leader and old_leader != new_leader:
            await transfer_applications(old_leader, new_leader)
        await callback.message.edit_text(f"✅ Новый лидер: {new_leader}")
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("admin_app_view|"))
async def admin_app_view(callback: types.CallbackQuery):
    try:
        if not await admin_check_and_active(callback):
            return
        app_id = int(callback.data.split("|")[1])
        app = await get_application(app_id)
        if not app:
            await callback.answer("Не найдена.", show_alert=True)
            return
        data = app["data"]
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except Exception:
                data = {}
        text = f"📋 ЗАЯВКА #{app_id}\n\nТип: {app['type']}\nАвтор: {app['author_username']}\nАдресат: {app['target_username']}\n"
        if data:
            text += f"Данные: {json.dumps(data, ensure_ascii=False)}\n"
        buttons = [
            [InlineKeyboardButton(text="✅ Одобрить", callback_data=f"admin_app_approve|{app_id}")],
            [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin_app_reject|{app_id}")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_apps")],
        ]
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_apps")
async def admin_apps(callback: types.CallbackQuery):
    try:
        if not await admin_check_and_active(callback):
            return
        apps = await get_pending_applications()
        if not apps:
            await callback.message.edit_text("📋 Заявок нет.", reply_markup=build_admin_keyboard(True))
            await callback.answer()
            return
        text = "📋 ЗАЯВКИ\n\n"
        buttons = []
        for a in apps:
            text += f"#{a['id']} — {a['type']} ({a['author_username']})\n"
            buttons.append([InlineKeyboardButton(text=f"#{a['id']}", callback_data=f"admin_app_view|{a['id']}")])
        buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")])
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("admin_app_approve|"))
async def admin_app_approve(callback: types.CallbackQuery):
    try:
        if not await admin_check_and_active(callback):
            return
        app_id = int(callback.data.split("|")[1])
        app = await get_application(app_id)
        if not app:
            await callback.answer("Не найдена.", show_alert=True)
            return
        data = app["data"]
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except Exception:
                data = {}
        if app["type"] == "citizenship":
            user_id = data.get("user_id")
            username = app["author_username"]
            if username:
                async with db_pool.acquire() as conn:
                    subj = await conn.fetchrow("SELECT id FROM subjects WHERE username = $1", username)
                    if not subj:
                        await conn.execute("""
                            INSERT INTO subjects (user_id, username, full_name, is_citizen)
                            VALUES ($1, $2, $3, TRUE)
                            ON CONFLICT (username) DO UPDATE SET is_citizen = TRUE
                        """, user_id, username, app["author_name"] or "Новый субъект")
                    else:
                        await conn.execute("UPDATE subjects SET is_citizen = TRUE WHERE username = $1", username)
        elif app["type"] == "create_party":
            name = data.get("name")
            emoji = data.get("emoji", "🎭")
            description = data.get("description", "")
            leader = app["author_username"]
            existing = await get_party_by_name(name)
            if not existing:
                await create_party(name, emoji, description, leader)
                await add_news(f"🎭 Создана партия «{name}» {emoji}")
                await add_reputation(leader, REP_RULES["party_created"])
        elif app["type"] == "join_party":
            pid = data.get("party_id")
            if pid:
                await add_party_member(pid, app["author_username"])
        await approve_application(app_id, ADMIN_ID)
        await add_reputation(app["author_username"], REP_RULES["application_approved"])
        await callback.message.edit_text(f"✅ Заявка #{app_id} одобрена.")
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("admin_app_reject|"))
async def admin_app_reject(callback: types.CallbackQuery):
    try:
        if not await admin_check_and_active(callback):
            return
        app_id = int(callback.data.split("|")[1])
        app = await get_application(app_id)
        await reject_application(app_id, ADMIN_ID, "Отклонено админом")
        if app:
            await add_reputation(app["author_username"], REP_RULES["application_rejected"])
        await callback.message.edit_text(f"❌ Заявка #{app_id} отклонена.")
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.message(Command("make_party"))
async def cmd_make_party(message: types.Message):
    if not await is_admin_active(message.from_user.id):
        await message.answer("⛔ Только админ.")
        return
    try:
        args = message.text.replace("/make_party", "").strip()
        parts = [p.strip() for p in args.split("|")]
        if len(parts) < 3:
            await message.answer("Формат: /make_party НАЗВАНИЕ | ЭМОДЗИ | @лидер | ОПИСАНИЕ")
            return
        name, emoji = parts[0], parts[1]
        leader = parts[2] if len(parts) > 2 else None
        desc = parts[3] if len(parts) > 3 else ""
        existing = await get_party_by_name(name)
        if existing:
            await message.answer("Партия с таким названием уже есть.")
            return
        await create_party(name, emoji, desc, leader)
        await add_news(f"🎭 Создана партия «{name}» {emoji}")
        await message.answer(f"✅ Партия «{name}» создана.")
    except Exception as e:
        await message.answer(f"Ошибка: {e}")


# ===== ГОЛОСОВАНИЕ (Президент) =====
@dp.message(Command("vote"))
async def cmd_vote(message: types.Message):
    try:
        user = message.from_user
        username = normalize_username(user.username)
        tester = is_tester(username)
        if not tester and not is_allowed_to_vote(user.id, username):
            await message.answer("❌ Ты не в списке голосующих.")
            return
        status = get_election_status()
        if not tester and status != "during":
            await message.answer(build_ballot_text())
            return
        if not tester:
            already_voted = await user_has_voted(user.id)
            if not already_voted and username:
                already_voted = await username_has_voted(username)
            if already_voted:
                await message.answer("⚠️ Ты уже голосовал.")
                return
        prefix = "🧪 ТЕСТОВЫЙ РЕЖИМ\n\n" if tester else ""
        await message.answer(prefix + build_ballot_text(), reply_markup=build_ballot_keyboard())
    except Exception as e:
        print(f"Ошибка cmd_vote: {e}")
        await message.answer(f"Ошибка: {e}")


@dp.callback_query(lambda c: c.data == "bios")
async def process_bios(callback: types.CallbackQuery):
    try:
        await callback.message.answer(build_bios_text())
    except Exception as e:
        print(f"Ошибка: {e}")
    try:
        await callback.answer()
    except Exception:
        pass


@dp.callback_query(lambda c: c.data == "noop")
async def process_noop(callback: types.CallbackQuery):
    try:
        await callback.answer("Пометка 🙂")
    except Exception:
        pass


@dp.callback_query(lambda c: c.data.startswith("vote_"))
async def process_vote(callback: types.CallbackQuery):
    try:
        user = callback.from_user
        username = normalize_username(user.username)
        tester = is_tester(username)
        if not tester and not is_allowed_to_vote(user.id, username):
            await callback.answer("Не в списке.", show_alert=True)
            return
        status = get_election_status()
        if not tester and status != "during":
            await callback.answer("Голосование закрыто.", show_alert=True)
            return
        if not tester:
            already_voted = await user_has_voted(user.id)
            if not already_voted and username:
                already_voted = await username_has_voted(username)
            if already_voted:
                await callback.answer("Ты уже голосовал!", show_alert=True)
                return
        candidate_id = callback.data.split("_")[1]
        candidate_name = CANDIDATES[candidate_id]["name"]
        voter_name = get_voter_name(user.id, username) if not tester else "🧪 Тест"
        await save_vote(user.id, username, voter_name, candidate_id)
        await add_reputation(username, REP_RULES["vote"])
        suffix = "\n\nМожешь голосовать ещё раз." if tester else ""
        caption = f"━━━━━━━━━━━━━━━━━━━━━\n✅ ГОЛОС ПРИНЯТ!\n━━━━━━━━━━━━━━━━━━━━━\n\n👤 Субъект: {voter_name}\n🗳 Выбор: {candidate_name}{suffix}"
        if VIDEO_FILE_ID:
            try:
                await callback.message.answer_video(video=VIDEO_FILE_ID, caption=caption)
            except Exception:
                await callback.message.answer(caption)
        else:
            await callback.message.answer(caption)
        if tester:
            await callback.message.answer("🧪 Ещё раз?", reply_markup=build_ballot_keyboard())
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.message(Command("results"))
async def cmd_results(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Только админ.")
        return
    if not await get_all_votes():
        await message.answer("📊 Пока никто не голосовал.")
        return
    await message.answer(await build_results_text())


@dp.message(Command("reset"))
async def cmd_reset(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Только админ.")
        return
    await clear_votes()
    await message.answer("🔄 Сброшено.")


@dp.message(lambda m: m.video is not None)
async def get_video_id(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer(f"📹 file_id:\n\n{message.video.file_id}")


# ===== ФОНОВАЯ ЗАДАЧА =====
async def background_watcher(bot: Bot):
    global flags
    while True:
        try:
            n = now_msk()
            if not flags["test_end_notified"] and n >= TEST_MODE_END:
                try:
                    await bot.send_message(ADMIN_ID, "🧪 Тестовый режим снят.")
                except Exception:
                    pass
                flags["test_end_notified"] = True

            if not flags["election_end_notified"] and n >= ELECTION_END:
                all_votes = await get_all_votes()
                text = await build_results_text()
                sent_to = set()
                for v in all_votes:
                    uid = v["user_id"]
                    if uid in sent_to or uid < 0:
                        continue
                    sent_to.add(uid)
                    try:
                        await bot.send_message(uid, text)
                    except Exception as e:
                        print(f"Не смог отправить {uid}: {e}")
                if ADMIN_ID not in sent_to:
                    try:
                        await bot.send_message(ADMIN_ID, text)
                    except Exception:
                        pass
                flags["election_end_notified"] = True

            # Проверка окончания выборов в ГосДуму
            try:
                active_e = await get_active_duma_election()
                if active_e and active_e["ends_at"]:
                    if now_msk() >= active_e["ends_at"]:
                        winners_info = await finish_duma_election(active_e["id"])
                        text = "🗳 ВЫБОРЫ В ГОСДУМУ ЗАВЕРШЕНЫ!\n\n"
                        for w in winners_info:
                            text += f"{w['place']}. {w['party']} ({w['votes']} голосов)\n"
                            text += f"   Депутаты: {', '.join(w['deputies'])}\n\n"
                        await add_news(f"🗳 Выборы в ГосДуму завершены!")
                        # Рассылаем всем
                        subjects = await get_all_subjects()
                        for s in subjects:
                            if s["user_id"] and s["user_id"] > 0:
                                try:
                                    await bot.send_message(s["user_id"], text)
                                except Exception:
                                    pass
            except Exception as e:
                print(f"Ошибка duma watcher: {e}")

            # Проверка срока Президента
            try:
                term = await get_active_president_term()
                if term and term["ends_at"] and now_msk() >= term["ends_at"]:
                    await end_president_term()
                    # Снимаем роль президента
                    async with db_pool.acquire() as conn:
                        role = await conn.fetchrow("SELECT id FROM roles WHERE code = 'president'")
                        if role:
                            await conn.execute("DELETE FROM subject_roles WHERE role_id = $1", role["id"])
                    await add_news(f"👑 Срок Президента истёк. ГосДума должна назначить новые выборы.")
                    try:
                        await bot.send_message(ADMIN_ID, "👑 Срок Президента истёк. Нужны новые выборы.")
                    except Exception:
                        pass
            except Exception as e:
                print(f"Ошибка president watcher: {e}")

        except Exception as e:
            print(f"Ошибка watcher: {e}")
        await asyncio.sleep(30)


# ===== ЗАПУСК =====
async def main():
    global db_pool
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN не задан!")
        return
    if not DATABASE_URL:
        print("❌ DATABASE_URL не задан!")
        return

    db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    await init_db()
    await preload_roles()
    await preload_subjects()
    await preload_initial_roles()
    await preload_parties()
    await preload_votes()
    print("База данных подключена.")

    bot = Bot(token=BOT_TOKEN)
    asyncio.create_task(background_watcher(bot))
    print("Бот запущен...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
