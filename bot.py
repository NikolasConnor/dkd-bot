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
    "1": {"name": "Блошихин Кирилл Вадимович", "bio": "Перепил Горохова.", "type": "main"},
    "2": {"name": "Косарев Сергей Сергеевич", "bio": "Генератор шашлыков.", "type": "main"},
    "3": {"name": "Проселков Кирилл Романович", "bio": "Генератор сбора на хате.", "type": "main"},
    "4": {"name": "Горохов Никита Александрович", "bio": "Бывший президент.", "type": "additional"},
    "5": {"name": "ПРОТИВ ВСЕХ", "bio": "PS. Группа «Ленинград».", "type": "against"},
}
VOTERS = {
    "@Haiser101": {"id": None, "name": "Яровой Иван Сергеевич"},
    "@vozduhanprimee": {"id": None, "name": "Бородин Тимофей Сергеевич"},
    "@spar9d": {"id": None, "name": "Глазков Владислав Юрьевич"},
    "@Cakcer_12": {"id": None, "name": "Головин Максим Сергеевич"},
    "@Dronus01": {"id": None, "name": "Морев Андрей Олегович"},
    "@Nikolas_Connor": {"id": 7934244888, "name": "Горохов Никита Александрович"},
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
REP_RULES = {"vote": 1, "application": 2, "application_approved": 5, "application_rejected": -2, "law_approved": 10, "law_rejected": -3, "party_created": 15, "party_dissolved": -10}
db_pool = None
flags = {"test_end_notified": False, "election_end_notified": False}


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


dp = Dispatcher()


def normalize_username(username):
    if not username:
        return None
    if not username.startswith("@"):
        return "@" + username
    return username


def now_msk():
    return datetime.now(MSK)
def to_db_dt(dt):
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(MSK).replace(tzinfo=None)
    return dt


def from_db_dt(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=MSK)
    return dt


def get_election_status():
    n = now_msk()
    if n < ELECTION_START:
        return "before"
    if n <= ELECTION_END:
        return "during"
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


def parse_date_flexible(text):
    if not text:
        return None
    t = text.strip().replace(".", "-").replace("/", "-").replace(",", " ")
    formats = ["%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H.%M", "%d-%m-%Y %H:%M", "%d-%m-%Y %H.%M", "%d-%m-%y %H:%M", "%Y.%m.%d %H:%M"]
    for fmt in formats:
        try:
            dt = datetime.strptime(t, fmt)
            return dt.replace(tzinfo=MSK)
        except Exception:
            continue
    return None


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
    t = " ".join(text.lower().strip().split())
    parts = t.split()
    if len(parts) == 2:
        w1, w2 = parts
        if len(w1) == 3 and w1[0] == "б" and w1[1] == "о" and w1[2] == "г":
            if w2.startswith("эфиоп") or w2.startswith("ефиоп"):
                if w2.endswith("и") or w2.endswith("ия"):
                    return True
    return False


async def init_db():
    async with db_pool.acquire() as conn:
        await conn.execute("""CREATE TABLE IF NOT EXISTS votes (id SERIAL PRIMARY KEY, user_id BIGINT NOT NULL, username TEXT, voter_name TEXT, candidate_id TEXT NOT NULL, voted_at TIMESTAMP DEFAULT NOW(), added_by_admin BOOLEAN DEFAULT FALSE)""")
        await conn.execute("ALTER TABLE votes ADD COLUMN IF NOT EXISTS added_by_admin BOOLEAN DEFAULT FALSE")
        await conn.execute("""CREATE TABLE IF NOT EXISTS service_flags (key TEXT PRIMARY KEY, value TEXT)""")
        await conn.execute("""CREATE TABLE IF NOT EXISTS subjects (id SERIAL PRIMARY KEY, user_id BIGINT UNIQUE, username TEXT UNIQUE, full_name TEXT NOT NULL, is_citizen BOOLEAN DEFAULT FALSE, reputation INTEGER DEFAULT 0, joined_at TIMESTAMP DEFAULT NOW())""")
        await conn.execute("""CREATE TABLE IF NOT EXISTS roles (id SERIAL PRIMARY KEY, code TEXT UNIQUE NOT NULL, name TEXT NOT NULL, emoji TEXT DEFAULT '👤', max_holders INTEGER)""")
        await conn.execute("""CREATE TABLE IF NOT EXISTS subject_roles (id SERIAL PRIMARY KEY, subject_id INTEGER REFERENCES subjects(id) ON DELETE CASCADE, role_id INTEGER REFERENCES roles(id) ON DELETE CASCADE, assigned_by BIGINT, assigned_at TIMESTAMP DEFAULT NOW(), UNIQUE(subject_id, role_id))""")
        await conn.execute("""CREATE TABLE IF NOT EXISTS parties (id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL, emoji TEXT DEFAULT '🎭', description TEXT DEFAULT '', founder_username TEXT, leader_username TEXT, status TEXT DEFAULT 'active', created_at TIMESTAMP DEFAULT NOW())""")
        await conn.execute("""CREATE TABLE IF NOT EXISTS party_members (id SERIAL PRIMARY KEY, party_id INTEGER REFERENCES parties(id) ON DELETE CASCADE, username TEXT UNIQUE NOT NULL, joined_at TIMESTAMP DEFAULT NOW())""")
        await conn.execute("""CREATE TABLE IF NOT EXISTS applications (id SERIAL PRIMARY KEY, type TEXT NOT NULL, author_username TEXT NOT NULL, author_name TEXT, target_username TEXT, data JSONB DEFAULT '{}', status TEXT DEFAULT 'pending', created_at TIMESTAMP DEFAULT NOW(), decided_at TIMESTAMP, decided_by BIGINT, reason TEXT)""")
        await conn.execute("""CREATE TABLE IF NOT EXISTS admin_sessions (user_id BIGINT PRIMARY KEY, is_active BOOLEAN DEFAULT FALSE, activated_at TIMESTAMP)""")
        await conn.execute("""CREATE TABLE IF NOT EXISTS laws (id SERIAL PRIMARY KEY, title TEXT NOT NULL, description TEXT, author_username TEXT, status TEXT DEFAULT 'duma', duma_votes_for INTEGER DEFAULT 0, duma_votes_against INTEGER DEFAULT 0, deadline TIMESTAMP, created_at TIMESTAMP DEFAULT NOW())""")
        await conn.execute("""CREATE TABLE IF NOT EXISTS law_votes (id SERIAL PRIMARY KEY, law_id INTEGER REFERENCES laws(id) ON DELETE CASCADE, voter_username TEXT NOT NULL, vote TEXT NOT NULL, voted_at TIMESTAMP DEFAULT NOW(), UNIQUE(law_id, voter_username))""")
        await conn.execute("""CREATE TABLE IF NOT EXISTS decrees (id SERIAL PRIMARY KEY, title TEXT NOT NULL, text TEXT, author_username TEXT, is_secret BOOLEAN DEFAULT FALSE, secret_for TEXT, created_at TIMESTAMP DEFAULT NOW())""")
        await conn.execute("""CREATE TABLE IF NOT EXISTS news (id SERIAL PRIMARY KEY, text TEXT NOT NULL, source TEXT DEFAULT 'auto', created_at TIMESTAMP DEFAULT NOW())""")
        await conn.execute("""CREATE TABLE IF NOT EXISTS duma_elections (id SERIAL PRIMARY KEY, started_at TIMESTAMP DEFAULT NOW(), ends_at TIMESTAMP, status TEXT DEFAULT 'active', results JSONB DEFAULT '[]')""")
        await conn.execute("""CREATE TABLE IF NOT EXISTS duma_votes (id SERIAL PRIMARY KEY, election_id INTEGER REFERENCES duma_elections(id) ON DELETE CASCADE, voter_username TEXT NOT NULL, party_id INTEGER NOT NULL, voted_at TIMESTAMP DEFAULT NOW(), UNIQUE(election_id, voter_username))""")
        await conn.execute("""CREATE TABLE IF NOT EXISTS president_term (id SERIAL PRIMARY KEY, username TEXT NOT NULL, started_at TIMESTAMP DEFAULT NOW(), ends_at TIMESTAMP, status TEXT DEFAULT 'active')""")


async def preload_roles():
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT value FROM service_flags WHERE key = 'roles_loaded'")
        if row is not None:
            return
        for r in ROLES_INITIAL:
            await conn.execute("INSERT INTO roles (code, name, emoji, max_holders) VALUES ($1, $2, $3, $4) ON CONFLICT (code) DO NOTHING", r["code"], r["name"], r["emoji"], r["max_holders"])
        await conn.execute("INSERT INTO service_flags (key, value) VALUES ('roles_loaded', 'done')")


async def preload_subjects():
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT value FROM service_flags WHERE key = 'subjects_loaded'")
        if row is not None:
            return
        for s in SUBJECTS_INITIAL:
            await conn.execute("INSERT INTO subjects (username, full_name, is_citizen) VALUES ($1, $2, TRUE) ON CONFLICT (username) DO NOTHING", normalize_username(s["username"]), s["full_name"])
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
                await conn.execute("INSERT INTO subject_roles (subject_id, role_id, assigned_by) VALUES ($1, $2, $3) ON CONFLICT (subject_id, role_id) DO NOTHING", subj["id"], role["id"], ADMIN_ID)
        await conn.execute("INSERT INTO service_flags (key, value) VALUES ('initial_roles_loaded', 'done')")


async def preload_parties():
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT value FROM service_flags WHERE key = 'parties_loaded'")
        if row is not None:
            return
        for p in PARTIES_INITIAL:
            uname = normalize_username(p["leader_username"])
            await conn.execute("INSERT INTO parties (name, emoji, description, founder_username, leader_username) VALUES ($1, $2, $3, $4, $5) ON CONFLICT (name) DO NOTHING", p["name"], p["emoji"], p["description"], uname, uname)
            party = await conn.fetchrow("SELECT id FROM parties WHERE name = $1", p["name"])
            if party:
                await conn.execute("INSERT INTO party_members (party_id, username) VALUES ($1, $2) ON CONFLICT (username) DO NOTHING", party["id"], uname)
        await conn.execute("INSERT INTO service_flags (key, value) VALUES ('parties_loaded', 'done')")


async def preload_votes():
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT value FROM service_flags WHERE key = 'preloaded_votes'")
        if row is not None:
            return
        for v in PRELOADED_VOTES:
            await conn.execute("INSERT INTO votes (user_id, username, voter_name, candidate_id) VALUES ($1, $2, $3, $4)", -1, normalize_username(v["username"]), v["voter_name"], v["candidate_id"])
        await conn.execute("INSERT INTO service_flags (key, value) VALUES ('preloaded_votes', 'done')")


async def save_vote(user_id, username, voter_name, candidate_id, added_by_admin=False):
    async with db_pool.acquire() as conn:
        await conn.execute("INSERT INTO votes (user_id, username, voter_name, candidate_id, added_by_admin) VALUES ($1, $2, $3, $4, $5)", user_id, normalize_username(username), voter_name, candidate_id, added_by_admin)


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
        return await conn.fetch("SELECT r.* FROM roles r JOIN subject_roles sr ON sr.role_id = r.id WHERE sr.subject_id = $1 ORDER BY r.id", subject_id)


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
        await conn.execute("INSERT INTO subject_roles (subject_id, role_id, assigned_by) VALUES ($1, $2, $3) ON CONFLICT (subject_id, role_id) DO NOTHING", subject_id, role_id, assigned_by)
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


async def has_role_by_username(username, role_code):
    username = normalize_username(username)
    if not username:
        return False
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT 1 FROM subjects s JOIN subject_roles sr ON sr.subject_id = s.id JOIN roles r ON r.id = sr.role_id WHERE s.username = $1 AND r.code = $2", username, role_code)
        return row is not None


async def is_admin_active(user_id):
    if user_id != ADMIN_ID:
        return False
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT is_active FROM admin_sessions WHERE user_id = $1", user_id)
        return row and row["is_active"]


async def can_use_pres_panel(user_id, username):
    if user_id == ADMIN_ID:
        return True
    return await has_role_by_username(username, "president")


async def activate_admin(user_id):
    async with db_pool.acquire() as conn:
        await conn.execute("INSERT INTO admin_sessions (user_id, is_active, activated_at) VALUES ($1, TRUE, NOW()) ON CONFLICT (user_id) DO UPDATE SET is_active = TRUE, activated_at = NOW()", user_id)


async def deactivate_admin(user_id):
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE admin_sessions SET is_active = FALSE WHERE user_id = $1", user_id)


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
        await conn.execute("INSERT INTO parties (name, emoji, description, founder_username, leader_username) VALUES ($1, $2, $3, $4, $5)", name, emoji, description, leader_username, leader_username)
        party = await conn.fetchrow("SELECT id FROM parties WHERE name = $1", name)
        if party:
            await conn.execute("INSERT INTO party_members (party_id, username) VALUES ($1, $2) ON CONFLICT (username) DO NOTHING", party["id"], leader_username)
        return party


async def get_user_party(username):
    username = normalize_username(username)
    if not username:
        return None
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("SELECT p.* FROM parties p JOIN party_members pm ON pm.party_id = p.id WHERE pm.username = $1 AND p.status = 'active'", username)


async def add_party_member(party_id, username):
    async with db_pool.acquire() as conn:
        await conn.execute("INSERT INTO party_members (party_id, username) VALUES ($1, $2) ON CONFLICT (username) DO NOTHING", party_id, normalize_username(username))


async def remove_party_member(username):
    username = normalize_username(username)
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM party_members WHERE username = $1", username)


async def dissolve_party(party_id):
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE parties SET status = 'dissolved' WHERE id = $1", party_id)


async def change_party_leader(party_id, new_leader_username):
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE parties SET leader_username = $1 WHERE id = $2", normalize_username(new_leader_username), party_id)


async def create_application(app_type, author_username, author_name, target_username, data):
    async with db_pool.acquire() as conn:
        await conn.execute("INSERT INTO applications (type, author_username, author_name, target_username, data) VALUES ($1, $2, $3, $4, $5)", app_type, normalize_username(author_username), author_name, normalize_username(target_username) if target_username else None, json.dumps(data))


async def get_pending_applications(target_username=None):
    async with db_pool.acquire() as conn:
        if target_username:
            return await conn.fetch("SELECT * FROM applications WHERE status = 'pending' AND target_username = $1 ORDER BY created_at", normalize_username(target_username))
        return await conn.fetch("SELECT * FROM applications WHERE status = 'pending' ORDER BY created_at")


async def get_application(app_id):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM applications WHERE id = $1", app_id)


async def approve_application(app_id, decided_by):
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE applications SET status = 'approved', decided_at = NOW(), decided_by = $1 WHERE id = $2", decided_by, app_id)


async def reject_application(app_id, decided_by, reason):
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE applications SET status = 'rejected', decided_at = NOW(), decided_by = $1, reason = $2 WHERE id = $3", decided_by, reason, app_id)


async def transfer_applications(old_target, new_target):
    old_target = normalize_username(old_target)
    new_target = normalize_username(new_target)
    if not old_target or not new_target:
        return
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE applications SET target_username = $1 WHERE target_username = $2 AND status = 'pending'", new_target, old_target)


async def notify_author(bot, app, status_text):
    if not app:
        return
    subj = await get_subject_by_username(app["author_username"])
    if subj and subj["user_id"] and subj["user_id"] > 0:
        try:
            await bot.send_message(subj["user_id"], f"📋 Заявка #{app['id']}\n\n{status_text}")
        except Exception as e:
            print(f"Не смог уведомить: {e}")


async def create_law(title, description, author_username):
    deadline = to_db_dt(now_msk() + timedelta(days=1))
    async with db_pool.acquire() as conn:
        await conn.execute("INSERT INTO laws (title, description, author_username, status, deadline) VALUES ($1, $2, $3, 'duma', $4)", title, description, normalize_username(author_username), deadline)
        return await conn.fetchrow("SELECT * FROM laws ORDER BY id DESC LIMIT 1")


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
        await conn.execute("INSERT INTO law_votes (law_id, voter_username, vote) VALUES ($1, $2, $3)", law_id, username, vote)
        if vote == "for":
            await conn.execute("UPDATE laws SET duma_votes_for = duma_votes_for + 1 WHERE id = $1", law_id)
        else:
            await conn.execute("UPDATE laws SET duma_votes_against = duma_votes_against + 1 WHERE id = $1", law_id)
        return True, "OK"


async def update_law_status(law_id, status):
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE laws SET status = $1 WHERE id = $2", status, law_id)


async def create_decree(title, text, author_username, is_secret=False, secret_for=None):
    async with db_pool.acquire() as conn:
        await conn.execute("INSERT INTO decrees (title, text, author_username, is_secret, secret_for) VALUES ($1, $2, $3, $4, $5)", title, text, normalize_username(author_username), is_secret, normalize_username(secret_for) if secret_for else None)


async def get_all_decrees():
    async with db_pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM decrees ORDER BY id DESC")


async def add_news(text, source="auto"):
    async with db_pool.acquire() as conn:
        await conn.execute("INSERT INTO news (text, source) VALUES ($1, $2)", text, source)


async def get_news(limit=20):
    async with db_pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM news ORDER BY id DESC LIMIT $1", limit)


async def get_active_president_term():
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM president_term WHERE status = 'active' ORDER BY id DESC LIMIT 1")


async def start_president_term(username, ends_at):
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE president_term SET status = 'finished' WHERE status = 'active'")
        await conn.execute("INSERT INTO president_term (username, ends_at, status) VALUES ($1, $2, 'active')", normalize_username(username), to_db_dt(ends_at))

async def end_president_term():
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE president_term SET status = 'finished' WHERE status = 'active'")


async def force_finish_president():
    await end_president_term()
    async with db_pool.acquire() as conn:
        role = await conn.fetchrow("SELECT id FROM roles WHERE code = 'president'")
        if role:
            await conn.execute("DELETE FROM subject_roles WHERE role_id = $1", role["id"])
    await add_news("👑 Президент снят досрочно.")
    return True


async def start_duma_election(ends_at):
    async with db_pool.acquire() as conn:
        await conn.execute("INSERT INTO duma_elections (ends_at, status) VALUES ($1, 'active')", to_db_dt(ends_at))
        return await conn.fetchrow("SELECT * FROM duma_elections ORDER BY id DESC LIMIT 1")

async def get_active_duma_election():
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM duma_elections WHERE status = 'active' ORDER BY id DESC LIMIT 1")


async def vote_duma(election_id, voter_username, party_id):
    async with db_pool.acquire() as conn:
        existing = await conn.fetchrow("SELECT id FROM duma_votes WHERE election_id = $1 AND voter_username = $2", election_id, normalize_username(voter_username))
        if existing:
            return False, "Ты уже голосовал"
        await conn.execute("INSERT INTO duma_votes (election_id, voter_username, party_id) VALUES ($1, $2, $3)", election_id, normalize_username(voter_username), party_id)
        return True, "OK"


async def finish_duma_election(election_id):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT party_id, COUNT(*) as cnt FROM duma_votes WHERE election_id = $1 GROUP BY party_id ORDER BY cnt DESC LIMIT 3", election_id)
        await conn.execute("DELETE FROM subject_roles WHERE role_id IN (SELECT id FROM roles WHERE code = 'deputy')")
        role = await conn.fetchrow("SELECT id FROM roles WHERE code = 'deputy'")
        winners = []
        for idx, r in enumerate(rows):
            party = await conn.fetchrow("SELECT * FROM parties WHERE id = $1", r["party_id"])
            if not party:
                continue
            members = await conn.fetch("SELECT username FROM party_members WHERE party_id = $1", party["id"])
            allowed = max(0, len(members) - idx)
            deputies = [m["username"] for m in members[:allowed]]
            winners.append({"party": party["name"], "votes": r["cnt"], "deputies": deputies, "place": idx + 1})
            for d in deputies:
                subj = await conn.fetchrow("SELECT id FROM subjects WHERE username = $1", d)
                if subj and role:
                    await conn.execute("INSERT INTO subject_roles (subject_id, role_id, assigned_by) VALUES ($1, $2, $3) ON CONFLICT (subject_id, role_id) DO NOTHING", subj["id"], role["id"], ADMIN_ID)
        await conn.execute("UPDATE duma_elections SET status = 'finished', results = $1 WHERE id = $2", json.dumps(winners), election_id)
        return winners


async def force_finish_duma_election():
    active = await get_active_duma_election()
    if not active:
        return None
    winners = await finish_duma_election(active["id"])
    return winners

# ===== КОНЕЦ ЧАСТИ 1 =====
# ===== НАЧАЛО ЧАСТИ 2 =====

def build_subject_profile(subject, roles, user_party, admin_mode=False):
    roles_text = "\n".join([f"{r['emoji']} {r['name']}" for r in roles]) if roles else "👤 Субъект"
    joined = subject["joined_at"].strftime("%d.%m.%Y") if subject["joined_at"] else "—"
    citizen_text = "✅ Есть" if subject["is_citizen"] else "❌ Нет"
    party_text = f"{user_party['emoji']} {user_party['name']}" if user_party else "—"
    text = "━━━━━━━━━━━━━━━━━━━━━\n👤 ПРОФИЛЬ\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    text += f"{subject['full_name']}\nUsername: {subject['username'] or '—'}\n\n"
    text += f"Должности:\n{roles_text}\n\nПартия: {party_text}\nГражданство: {citizen_text}\nВ ДКД с: {joined}\nРепутация: {subject['reputation']}"
    if admin_mode:
        text += "\n\n🔓 АДМИН-РЕЖИМ АКТИВЕН"
    return text


def build_ballot_text():
    status = get_election_status()
    n = now_msk()
    date = n.strftime("%d.%m.%Y %H:%M")
    if status == "before":
        return f"━━━━━━━━━━━━━━━━━━━━━\n🗳 БЮЛЛЕТЕНЬ ДКД\n━━━━━━━━━━━━━━━━━━━━━\n\n⏳ Не начались.\n\nДо старта: {format_delta(ELECTION_START - n)}"
    if status == "during":
        return f"━━━━━━━━━━━━━━━━━━━━━\n🗳 БЮЛЛЕТЕНЬ ДКД\nДата: {date} МСК\n━━━━━━━━━━━━━━━━━━━━━\n\n⏳ До конца: {format_delta(ELECTION_END - n)}\n\nОдин субъект — один голос."
    return "━━━━━━━━━━━━━━━━━━━━━\n🗳 БЮЛЛЕТЕНЬ ДКД\n━━━━━━━━━━━━━━━━━━━━━\n\n🔒 Завершены."


def build_ballot_keyboard():
    buttons = [[InlineKeyboardButton(text=f"{cid}. {CANDIDATES[cid]['name']}", callback_data=f"vote_{cid}")] for cid in ["1", "2", "3"]]
    buttons.append([InlineKeyboardButton(text="— Доп. кандидат —", callback_data="noop")])
    buttons.append([InlineKeyboardButton(text=f"4. {CANDIDATES['4']['name']}", callback_data="vote_4")])
    buttons.append([InlineKeyboardButton(text=f"5. {CANDIDATES['5']['name']}", callback_data="vote_5")])
    buttons.append([InlineKeyboardButton(text="📖 Биографии", callback_data="bios")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_bios_text():
    text = "📖 БИОГРАФИИ\n\n"
    for cid in ["1", "2", "3", "4", "5"]:
        c = CANDIDATES[cid]
        text += f"{cid}. {c['name']}\n{c['bio']}\n\n"
    return text


async def build_results_text():
    all_votes = await get_all_votes()
    counter = {cid: 0 for cid in CANDIDATES}
    for v in all_votes:
        counter[v["candidate_id"]] += 1
    text = "📊 РЕЗУЛЬТАТЫ\n\n"
    for cid, c in CANDIDATES.items():
        text += f"{cid}. {c['name']} — {counter[cid]}\n"
    text += f"\nВсего: {len(all_votes)}"
    max_votes = max(counter.values()) if counter else 0
    winners = [cid for cid, c in counter.items() if c == max_votes]
    if len(winners) == 1:
        win_id = winners[0]
        text += f"\n\n🏆 {CANDIDATES[win_id]['name']}" if win_id != "5" else "\n\n⚠️ Против всех."
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
    voted, not_voted = [], []
    for uname, info in VOTERS.items():
        uname_norm = normalize_username(uname)
        uid = info.get("id")
        is_voted = uname_norm in voted_usernames or (uid and uid > 0 and uid in voted_ids)
        (voted if is_voted else not_voted).append(("✅ " if is_voted else "❌ ") + info["name"])
    text = "👥 СТАТУС\n\nПроголосовали:\n" + ("\n".join(voted) if voted else "—")
    text += "\n\nНе голосовали:\n" + ("\n".join(not_voted) if not_voted else "—")
    return text


async def build_subjects_list_text():
    subjects = await get_all_subjects()
    text = "👥 СУБЪЕКТЫ\n\n"
    for s in subjects:
        roles = await get_subject_roles(s["id"])
        roles_short = ", ".join([r["name"] for r in roles]) if roles else "Субъект"
        text += f"• {s['full_name']}\n  {roles_short}\n\n"
    return text


async def build_roles_list_text():
    roles = await get_all_roles()
    text = "🎭 ДОЛЖНОСТИ\n\n"
    for r in roles:
        max_text = f"макс: {r['max_holders']}" if r["max_holders"] else "∞"
        text += f"{r['emoji']} {r['name']} ({max_text})\n"
    return text


async def build_parties_list_text():
    parties = await get_all_parties()
    if not parties:
        return "🎭 ПАРТИИ\n\nПока нет."
    text = "🎭 ПАРТИИ\n\n"
    for p in parties:
        members = await get_party_members(p["id"])
        text += f"{p['emoji']} {p['name']} — {len(members)} чел.\n   Лидер: {p['leader_username']}\n\n"
    return text


async def build_party_detail_text(party):
    members = await get_party_members(party["id"])
    text = f"━━━━━━━━━━━━━━━━━━━━━\n{party['emoji']} {party['name'].upper()}\n━━━━━━━━━━━━━━━━━━━━━\n\n{party['description']}\n\nЛидер: {party['leader_username']}\nСостав: {len(members)}\n"
    for m in members:
        text += f"  • {m['username']}\n"
    return text


def build_admin_keyboard(active=False):
    btn = "🔓 Активировать" if not active else "🔒 Деактивировать"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=btn, callback_data="admin_toggle")],
        [InlineKeyboardButton(text="👥 Субъекты", callback_data="admin_subjects")],
        [InlineKeyboardButton(text="🎭 Партии", callback_data="admin_parties")],
        [InlineKeyboardButton(text="📋 Заявки", callback_data="admin_apps")],
        [InlineKeyboardButton(text="📜 Законы", callback_data="admin_laws")],
        [InlineKeyboardButton(text="📢 Указы", callback_data="admin_decrees")],
        [InlineKeyboardButton(text="📰 Новости", callback_data="admin_news")],
        [InlineKeyboardButton(text="🗳 ГосДума", callback_data="admin_duma")],
        [InlineKeyboardButton(text="🛑 Завершить ГосДуму", callback_data="admin_duma_finish_now")],
        [InlineKeyboardButton(text="👑 Снять Президента", callback_data="admin_pres_finish_now")],
        [InlineKeyboardButton(text="📊 Выборы", callback_data="admin_results")],
        [InlineKeyboardButton(text="👥 Статус", callback_data="admin_status")],
        [InlineKeyboardButton(text="✍️ Внести голос", callback_data="admin_add_vote")],
        [InlineKeyboardButton(text="🔄 Сброс", callback_data="admin_reset_confirm")],
    ])


def build_admin_subjects_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Список", callback_data="admin_subjects_list")],
        [InlineKeyboardButton(text="➕ Выдать должность", callback_data="admin_assign_role_subj")],
        [InlineKeyboardButton(text="➖ Снять должность", callback_data="admin_remove_role_subj")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")],
    ])


def build_admin_parties_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Список", callback_data="admin_parties_list")],
        [InlineKeyboardButton(text="🗑 Распустить", callback_data="admin_dissolve_party")],
        [InlineKeyboardButton(text="👑 Сменить лидера", callback_data="admin_change_leader")],
        [InlineKeyboardButton(text="🏆 Кладбище", callback_data="admin_party_graveyard")],
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
        buttons.append([InlineKeyboardButton(text=f"{p['emoji']} {p['name']}", callback_data=f"admin_leader_party|{p['id']}")])
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
        buttons.append([InlineKeyboardButton(text="(нет)", callback_data="noop")])
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
        [InlineKeyboardButton(text="⚠️ ДА", callback_data="admin_reset_yes")],
        [InlineKeyboardButton(text="◀️ Отмена", callback_data="admin_back")],
    ])


def build_president_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Создать указ", callback_data="pres_decree")],
        [InlineKeyboardButton(text="📜 Обращение к народу", callback_data="pres_address")],
        [InlineKeyboardButton(text="📋 Заявки мне", callback_data="pres_apps")],
        [InlineKeyboardButton(text="🗳 Назначить выборы в ГосДуму", callback_data="pres_duma_start")],
        [InlineKeyboardButton(text="👑 Назначить министров", callback_data="pres_ministers_manage")],
        [InlineKeyboardButton(text="⚖️ Список правительства", callback_data="pres_ministers_list")],
        [InlineKeyboardButton(text="🏛 Созвать собрание", callback_data="pres_duma_session")],
    ])


async def build_pres_ministers_subject_keyboard():
    subjects = await get_all_subjects()
    buttons = []
    for s in subjects:
        buttons.append([InlineKeyboardButton(text=s['full_name'], callback_data=f"pres_ministers_pick|{s['id']}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="pres_back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def build_pres_ministers_role_keyboard(subject_id):
    roles = await get_all_roles()
    buttons = []
    for r in roles:
        if r["code"] in ["president", "deputy", "subject", "party_leader"]:
            continue
        buttons.append([InlineKeyboardButton(text=f"{r['emoji']} {r['name']}", callback_data=f"pres_ministers_set|{subject_id}|{r['id']}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="pres_ministers_manage")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user = message.from_user
    username = normalize_username(user.username)
    subject = await get_subject(user.id, username)
    if subject:
        if subject["user_id"] != user.id and user.id:
            await update_subject_user_id(subject["username"], user.id)
        roles = await get_subject_roles(subject["id"])
        roles_short = ", ".join([r["name"] for r in roles]) if roles else "Субъект"
        text = (
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🏛 ДКДУСЛУГИ\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"👤 {subject['full_name']}\n"
            f"🎭 {roles_short}\n"
            f"⭐ Репутация: {subject['reputation']}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📋 КОМАНДЫ:\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 /me — профиль\n"
            f"👥 /subjects — субъекты\n"
            f"🎭 /roles — должности\n"
            f"🎭 /parties — партии\n"
            f"📜 /laws — законы\n"
            f"📢 /decrees — указы\n"
            f"📰 /news — газета\n"
            f"📋 /apps — мои заявки\n"
            f"🗳 /vote — голосование\n"
            f"👑 /president — панель Президента\n"
            f"🏛 /duma — выборы в ГосДуму\n"
            f"🛠 /admin — админ-панель"
        )
        await message.answer(text)
        return
    await message.answer(
        "🏛 Добро пожаловать в ДКД!\n\n"
        "Ты не в списке субъектов.\n"
        "Чтобы зарегистрироваться, отправь КОДОВОЕ СЛОВО.\n\n"
        "Подсказка: два слова, связанных с Эфиопией и Богом."
    )


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "📖 ПОМОЩЬ\n\n"
        "/me — профиль\n"
        "/subjects — список субъектов\n"
        "/roles — список должностей\n"
        "/parties — партии\n"
        "/laws — законы\n"
        "/decrees — указы\n"
        "/news — газета\n"
        "/apps — мои заявки\n"
        "/vote — голосование Президента\n"
        "/law — внести закон (депутатам)\n"
        "/president — панель Президента\n"
        "/duma — выборы в ГосДуму\n"
        "/duma_session — созвать собрание (депутатам)\n"
        "/admin — админ-панель (админу)"
    )


@dp.message(Command("me"))
async def cmd_me(message: types.Message):
    user = message.from_user
    username = normalize_username(user.username)
    subject = await get_subject(user.id, username)
    if not subject:
        await message.answer("❌ Не зарегистрирован.")
        return
    roles = await get_subject_roles(subject["id"])
    user_party = await get_user_party(username)
    admin_mode = await is_admin_active(user.id)
    await message.answer(build_subject_profile(subject, roles, user_party, admin_mode))


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
        await message.answer("🎭 ПАРТИИ\n\nПока нет.")
        return
    text = await build_parties_list_text()
    buttons = [[InlineKeyboardButton(text=f"{p['emoji']} {p['name']}", callback_data=f"party_view|{p['id']}")] for p in parties]
    buttons.append([InlineKeyboardButton(text="➕ Создать", callback_data="party_create")])
    buttons.append([InlineKeyboardButton(text="🏆 Кладбище", callback_data="party_graveyard")])
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@dp.message(Command("laws"))
async def cmd_laws(message: types.Message):
    laws = await get_all_laws()
    if not laws:
        await message.answer("📜 Законов нет.")
        return
    sn = {"duma": "🟡 ГосДума", "government": "🟠 Правительство", "president": "🔵 Президент", "approved": "🟢 Принят", "vetoed": "🔴 Вето"}
    buttons = []
    for l in laws[:15]:
        buttons.append([InlineKeyboardButton(text=f"#{l['id']} {l['title'][:25]} — {sn.get(l['status'], '')}", callback_data=f"law_view|{l['id']}")])
    await message.answer("📜 ЗАКОНЫ", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@dp.message(Command("decrees"))
async def cmd_decrees(message: types.Message):
    decrees = await get_all_decrees()
    if not decrees:
        await message.answer("📢 Указов нет.")
        return
    text = "📢 УКАЗЫ\n\n"
    for d in decrees[:20]:
        marker = "🔒" if d["is_secret"] else "📢"
        text += f"{marker} #{d['id']} {d['title']}\n"
    await message.answer(text)


@dp.message(Command("news"))
async def cmd_news(message: types.Message):
    news = await get_news(20)
    if not news:
        await message.answer("📰 Пусто.")
        return
    text = "📰 ГАЗЕТА\n\n"
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
        await message.answer("❌ Не зарегистрирован.")
        return
    async with db_pool.acquire() as conn:
        my_apps = await conn.fetch("SELECT * FROM applications WHERE author_username = $1 ORDER BY created_at DESC LIMIT 10", username)
    if not my_apps:
        await message.answer("📋 Заявок нет.")
        return
    text = "📋 МОИ ЗАЯВКИ\n\n"
    for a in my_apps:
        se = {"pending": "🟡", "approved": "🟢", "rejected": "🔴"}.get(a["status"], "⚪")
        text += f"{se} #{a['id']} — {a['type']}\n"
    await message.answer(text)


# ===== ПАНЕЛЬ ПРЕЗИДЕНТА =====
@dp.message(Command("president"))
async def cmd_president(message: types.Message):
    user = message.from_user
    username = normalize_username(user.username)
    if not await can_use_pres_panel(user.id, username):
        await message.answer("⛔ Только Президент или Админ.")
        return
    term = await get_active_president_term()
    term_text = f"\nСрок до: {from_db_dt(term['ends_at']).strftime('%d.%m.%Y %H:%M')} МСК" if term and term['ends_at'] else "\nСрок не установлен"
    await message.answer(
        f"━━━━━━━━━━━━━━━━━━━━━\n👑 ПАНЕЛЬ ПРЕЗИДЕНТА\n━━━━━━━━━━━━━━━━━━━━━{term_text}\n\nВыбери действие:",
        reply_markup=build_president_keyboard()
    )


@dp.callback_query(lambda c: c.data == "pres_back")
async def pres_back(callback: types.CallbackQuery):
    try:
        username = normalize_username(callback.from_user.username)
        if not await can_use_pres_panel(callback.from_user.id, username):
            await callback.answer("Только Президент.", show_alert=True)
            return
        try:
            await callback.message.edit_text(
                "━━━━━━━━━━━━━━━━━━━━━\n👑 ПАНЕЛЬ ПРЕЗИДЕНТА\n━━━━━━━━━━━━━━━━━━━━━\n\nВыбери действие:",
                reply_markup=build_president_keyboard()
            )
        except Exception:
            await callback.message.answer(
                "━━━━━━━━━━━━━━━━━━━━━\n👑 ПАНЕЛЬ ПРЕЗИДЕНТА\n━━━━━━━━━━━━━━━━━━━━━\n\nВыбери действие:",
                reply_markup=build_president_keyboard()
            )
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
        username = normalize_username(callback.from_user.username)
        if not await can_use_pres_panel(callback.from_user.id, username):
            await callback.answer("Только Президент.", show_alert=True)
            return
        await callback.message.answer("📢 СОЗДАНИЕ УКАЗА\n\nШаг 1/3. Отправь ЗАГОЛОВОК (минимум 3 символа).")
        await state.set_state(DecreeForm.waiting_title)
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "pres_apps")
async def pres_apps(callback: types.CallbackQuery):
    try:
        username = normalize_username(callback.from_user.username)
        if not await can_use_pres_panel(callback.from_user.id, username):
            await callback.answer("Только Президент.", show_alert=True)
            return
        apps = await get_pending_applications(username)
        if not apps:
            try:
                await callback.message.edit_text("📋 Заявок нет.", reply_markup=build_president_keyboard())
            except Exception:
                await callback.message.answer("📋 Заявок нет.", reply_markup=build_president_keyboard())
            await callback.answer()
            return
        buttons = []
        text = "📋 ЗАЯВКИ ПРЕЗИДЕНТУ\n\n"
        for a in apps:
            text += f"#{a['id']} — {a['type']} от {a['author_username']}\n"
            buttons.append([InlineKeyboardButton(text=f"#{a['id']} открыть", callback_data=f"pres_app_view|{a['id']}")])
        buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="pres_back")])
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("pres_app_view|"))
async def pres_app_view(callback: types.CallbackQuery):
    try:
        username = normalize_username(callback.from_user.username)
        if not await can_use_pres_panel(callback.from_user.id, username):
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
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


async def handle_app_approve(app_id, decided_by, bot):
    app = await get_application(app_id)
    if not app:
        return None, "Заявка не найдена"
    data = app["data"]
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception:
            data = {}
    if app["type"] == "citizenship":
        user_id = data.get("user_id")
        author = app["author_username"]
        if author:
            async with db_pool.acquire() as conn:
                subj = await conn.fetchrow("SELECT id FROM subjects WHERE username = $1", author)
                if not subj:
                    await conn.execute("INSERT INTO subjects (user_id, username, full_name, is_citizen) VALUES ($1, $2, $3, TRUE) ON CONFLICT (username) DO UPDATE SET is_citizen = TRUE", user_id, author, app["author_name"] or "Новый субъект")
                else:
                    await conn.execute("UPDATE subjects SET is_citizen = TRUE WHERE username = $1", author)
    elif app["type"] == "create_party":
        name = data.get("name")
        emoji = data.get("emoji", "🎭")
        description = data.get("description", "")
        leader = app["author_username"]
        if not await get_party_by_name(name):
            await create_party(name, emoji, description, leader)
            await add_news(f"🎭 Создана партия «{name}» {emoji}")
            await add_reputation(leader, REP_RULES["party_created"])
    elif app["type"] == "join_party":
        pid = data.get("party_id")
        if pid:
            await add_party_member(pid, app["author_username"])
    await approve_application(app_id, decided_by)
    await add_reputation(app["author_username"], REP_RULES["application_approved"])
    await notify_author(bot, app, "✅ Твоя заявка ОДОБРЕНА!")
    return app, "OK"


async def handle_app_reject(app_id, decided_by, reason, bot):
    app = await get_application(app_id)
    if not app:
        return None
    await reject_application(app_id, decided_by, reason)
    await add_reputation(app["author_username"], REP_RULES["application_rejected"])
    await notify_author(bot, app, f"❌ Твоя заявка ОТКЛОНЕНА.\n\nПричина: {reason}")
    return app


@dp.callback_query(lambda c: c.data.startswith("pres_app_approve|"))
async def pres_app_approve(callback: types.CallbackQuery):
    try:
        username = normalize_username(callback.from_user.username)
        if not await can_use_pres_panel(callback.from_user.id, username):
            await callback.answer("Только Президент.", show_alert=True)
            return
        app_id = int(callback.data.split("|")[1])
        await handle_app_approve(app_id, callback.from_user.id, callback.bot)
        try:
            await callback.message.edit_text(f"✅ Заявка #{app_id} одобрена.", reply_markup=build_president_keyboard())
        except Exception:
            await callback.message.answer(f"✅ Заявка #{app_id} одобрена.")
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("pres_app_reject|"))
async def pres_app_reject(callback: types.CallbackQuery):
    try:
        username = normalize_username(callback.from_user.username)
        if not await can_use_pres_panel(callback.from_user.id, username):
            await callback.answer("Только Президент.", show_alert=True)
            return
        app_id = int(callback.data.split("|")[1])
        await handle_app_reject(app_id, callback.from_user.id, "Отклонено Президентом", callback.bot)
        try:
            await callback.message.edit_text(f"❌ Заявка #{app_id} отклонена.", reply_markup=build_president_keyboard())
        except Exception:
            await callback.message.answer(f"❌ Заявка #{app_id} отклонена.")
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "pres_ministers_list")
async def pres_ministers_list(callback: types.CallbackQuery):
    try:
        username = normalize_username(callback.from_user.username)
        if not await can_use_pres_panel(callback.from_user.id, username):
            await callback.answer("Только Президент.", show_alert=True)
            return
        async with db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT s.full_name, s.username, r.name as role_name, r.emoji
                FROM subjects s
                JOIN subject_roles sr ON sr.subject_id = s.id
                JOIN roles r ON r.id = sr.role_id
                WHERE r.code IN ('minister', 'premier', 'cbank', 'advisor')
                ORDER BY r.id
            """)
        text = "⚖️ ПРАВИТЕЛЬСТВО\n\n"
        if not rows:
            text += "Пока никого.\n"
        for r in rows:
            text += f"{r['emoji']} {r['role_name']}: {r['full_name']}\n"
        buttons = [[InlineKeyboardButton(text="◀️ Назад", callback_data="pres_back")]]
        try:
            await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        except Exception:
            await callback.message.answer(text)
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "pres_ministers_manage")
async def pres_ministers_manage(callback: types.CallbackQuery):
    try:
        username = normalize_username(callback.from_user.username)
        if not await can_use_pres_panel(callback.from_user.id, username):
            await callback.answer("Только Президент.", show_alert=True)
            return
        kb = await build_pres_ministers_subject_keyboard()
        await callback.message.edit_text(
            "👑 НАЗНАЧЕНИЕ МИНИСТРОВ\n\nШаг 1/2. Выбери субъекта:",
            reply_markup=kb
        )
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("pres_ministers_pick|"))
async def pres_ministers_pick(callback: types.CallbackQuery):
    try:
        username = normalize_username(callback.from_user.username)
        if not await can_use_pres_panel(callback.from_user.id, username):
            await callback.answer("Только Президент.", show_alert=True)
            return
        sid = int(callback.data.split("|")[1])
        kb = await build_pres_ministers_role_keyboard(sid)
        await callback.message.edit_text(
            "👑 Шаг 2/2. Выбери ДОЛЖНОСТЬ:",
            reply_markup=kb
        )
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("pres_ministers_set|"))
async def pres_ministers_set(callback: types.CallbackQuery):
    try:
        username = normalize_username(callback.from_user.username)
        if not await can_use_pres_panel(callback.from_user.id, username):
            await callback.answer("Только Президент.", show_alert=True)
            return
        parts = callback.data.split("|")
        sid = int(parts[1])
        rid = int(parts[2])
        ok, msg = await assign_role(sid, rid, callback.from_user.id)
        if ok:
            async with db_pool.acquire() as conn:
                subject = await conn.fetchrow("SELECT * FROM subjects WHERE id = $1", sid)
                role = await conn.fetchrow("SELECT * FROM roles WHERE id = $1", rid)
            await add_news(f"👑 {subject['full_name']} назначен: {role['name']}")
            try:
                await callback.message.edit_text(
                    f"✅ {subject['full_name']} назначен на должность:\n{role['emoji']} {role['name']}",
                    reply_markup=build_president_keyboard()
                )
            except Exception:
                await callback.message.answer(f"✅ {subject['full_name']} → {role['name']}")
        else:
            await callback.message.answer(f"❌ {msg}")
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "pres_duma_start")
async def pres_duma_start(callback: types.CallbackQuery, state: FSMContext):
    try:
        username = normalize_username(callback.from_user.username)
        if not await can_use_pres_panel(callback.from_user.id, username):
            await callback.answer("Только Президент.", show_alert=True)
            return
        if await get_active_duma_election():
            await callback.answer("Выборы уже идут!", show_alert=True)
            return
        await callback.message.answer(
            "🗳 НАЗНАЧЕНИЕ ВЫБОРОВ В ГОСДУМУ\n\n"
            "Отправь ДАТУ ОКОНЧАНИЯ.\n\n"
            "Форматы:\n"
            "• 2027-01-15 20:00\n"
            "• 15-01-2027 20:00\n"
            "• 15.01.2027 20:00\n\n"
            "Главное — дата должна быть в БУДУЩЕМ."
        )
        await state.set_state(ElectionForm.waiting_date_end)
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "pres_duma_session")
async def pres_duma_session(callback: types.CallbackQuery):
    try:
        try:
            await callback.message.edit_text(
                "🏛 Собрание ГосДумы созывается ДЕПУТАТАМИ.\n\nКоманда: /duma_session",
                reply_markup=build_president_keyboard()
            )
        except Exception:
            await callback.message.answer("🏛 Команда: /duma_session")
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
        username = normalize_username(callback.from_user.username)
        if not await can_use_pres_panel(callback.from_user.id, username):
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

# ===== КОНЕЦ ЧАСТИ 2 =====
# ===== НАЧАЛО ЧАСТИ 3 =====

# ===== FSM-ОБРАБОТЧИКИ (до handle_text!) =====
@dp.message(ElectionForm.waiting_date_end)
async def duma_date_end(message: types.Message, state: FSMContext):
    try:
        username = normalize_username(message.from_user.username)
        if not await can_use_pres_panel(message.from_user.id, username):
            await message.answer("⛔ Только Президент или Админ.")
            await state.clear()
            return
        dt = parse_date_flexible(message.text)
        if not dt:
            await message.answer(
                "❌ Неверный формат.\n\n"
                "Попробуй: 2027-01-15 20:00\n"
                "или: 15-01-2027 20:00\n"
                "или: 15.01.2027 20:00"
            )
            return
        if dt <= now_msk():
            await message.answer(
                f"❌ Дата должна быть в БУДУЩЕМ.\n\n"
                f"Сейчас: {now_msk().strftime('%d.%m.%Y %H:%M')} МСК\n"
                f"Ты ввёл: {dt.strftime('%d.%m.%Y %H:%M')} МСК"
            )
            return
        await start_duma_election(dt)
        await add_news(f"🗳 Назначены выборы в ГосДуму! До {dt.strftime('%d.%m.%Y %H:%M')} МСК")
        await message.answer(
            f"✅ ВЫБОРЫ НАЗНАЧЕНЫ!\n\n"
            f"Окончание: {dt.strftime('%d.%m.%Y %H:%M')} МСК\n\n"
            f"Голосование: /duma"
        )
        await state.clear()
    except Exception as e:
        print(f"Ошибка duma_date_end: {e}")
        await message.answer(f"❌ Ошибка: {e}")
        await state.clear()

@dp.message(DecreeForm.waiting_title)
async def decree_title(message: types.Message, state: FSMContext):
    title = message.text.strip() if message.text else ""
    if len(title) < 3:
        await message.answer("Слишком коротко (минимум 3 символа).")
        return
    await state.update_data(decree_title=title)
    await message.answer(f"Заголовок: {title}\n\nШаг 2/3. Отправь ТЕКСТ указа.")
    await state.set_state(DecreeForm.waiting_text)


@dp.message(DecreeForm.waiting_text)
async def decree_text(message: types.Message, state: FSMContext):
    text = message.text.strip() if message.text else ""
    if len(text) < 3:
        await message.answer("Слишком коротко.")
        return
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
        await add_news(f"🔒 Секретный указ (для {secret_for})")
        await message.answer(f"✅ СЕКРЕТНЫЙ УКАЗ «{title}» создан.\nВидит только: {secret_for}")
    else:
        await add_news(f"📢 Подписан указ: «{title}»")
        sent = 0
        for s in await get_all_subjects():
            if s["user_id"] and s["user_id"] > 0:
                try:
                    await message.bot.send_message(s["user_id"], f"📢 УКАЗ ПРЕЗИДЕНТА\n\n{title}\n\n{text}")
                    sent += 1
                except Exception:
                    pass
        await message.answer(f"✅ УКАЗ «{title}» разослан {sent} субъектам.")
    await state.clear()


@dp.message(LawForm.waiting_title)
async def law_title(message: types.Message, state: FSMContext):
    title = message.text.strip() if message.text else ""
    if len(title) < 3:
        await message.answer("Слишком коротко (минимум 3 символа).")
        return
    await state.update_data(law_title=title)
    await message.answer(f"Название: {title}\n\nШаг 2/2. Отправь ОПИСАНИЕ закона.")
    await state.set_state(LawForm.waiting_description)


@dp.message(LawForm.waiting_description)
async def law_description(message: types.Message, state: FSMContext):
    description = message.text.strip() if message.text else ""
    if len(description) < 3:
        await message.answer("Слишком коротко.")
        return
    data = await state.get_data()
    title = data.get("law_title")
    username = normalize_username(message.from_user.username)
    law = await create_law(title, description, username)
    await add_news(f"📜 Внесён законопроект «{title}» от {username}")
    await message.answer(f"✅ ЗАКОНОПРОЕКТ #{law['id']} «{title}» создан!\n\nГолосование — /laws")
    await state.clear()


@dp.message(PartyForm.waiting_name)
async def party_name(message: types.Message, state: FSMContext):
    name = message.text.strip() if message.text else ""
    if len(name) < 2 or len(name) > 50:
        await message.answer("Название должно быть 2-50 символов.")
        return
    if await get_party_by_name(name):
        await message.answer("Партия с таким названием уже есть. Придумай другое.")
        return
    await state.update_data(party_name=name)
    await message.answer(f"Название: {name}\n\nШаг 2/3. Отправь ЭМОДЗИ (1 символ).")
    await state.set_state(PartyForm.waiting_emoji)


@dp.message(PartyForm.waiting_emoji)
async def party_emoji(message: types.Message, state: FSMContext):
    emoji = message.text.strip() if message.text else "🎭"
    if len(emoji) > 5:
        await message.answer("Отправь ОДИН эмодзи.")
        return
    await state.update_data(party_emoji=emoji)
    await message.answer(f"Эмодзи: {emoji}\n\nШаг 3/3. Отправь ПРОГРАММУ партии.")
    await state.set_state(PartyForm.waiting_description)


@dp.message(PartyForm.waiting_description)
async def party_description(message: types.Message, state: FSMContext):
    description = message.text.strip() if message.text else ""
    if len(description) < 3:
        await message.answer("Слишком коротко.")
        return
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
    await message.answer(
        f"✅ ЗАЯВКА НА ПАРТИЮ ОТПРАВЛЕНА!\n\n"
        f"Название: {name}\n"
        f"Эмодзи: {emoji}\n"
        f"Программа: {description}\n\n"
        f"Ожидай решения Президента."
    )
    await state.clear()


@dp.message(NewsForm.waiting_text)
async def news_text(message: types.Message, state: FSMContext):
    text = message.text.strip() if message.text else ""
    if len(text) < 3:
        await message.answer("Слишком коротко.")
        return
    await add_news(f"📢 {text}", source="admin")
    await message.answer("✅ Новость добавлена в газету.")
    await state.clear()


# ===== КОДОВОЕ СЛОВО (ПОСЛЕ ВСЕХ FSM!) =====
from aiogram.filters import StateFilter

@dp.message(StateFilter(None), lambda m: m.text and not m.text.startswith("/") and m.video is None)
async def handle_text(message: types.Message):
    user = message.from_user
    username = normalize_username(user.username)
    subject = await get_subject(user.id, username)
    if subject:
        return
    if check_secret_word(message.text):
        if not username:
            await message.answer("❌ У тебя нет username в Telegram. Установи username и попробуй снова.")
            return
        async with db_pool.acquire() as conn:
            president = await conn.fetchrow("SELECT s.username FROM subjects s JOIN subject_roles sr ON sr.subject_id = s.id JOIN roles r ON r.id = sr.role_id WHERE r.code = 'president' LIMIT 1")
        target = president["username"] if president else None
        await create_application("citizenship", username, user.full_name, target, {"user_id": user.id})
        await message.answer(
            "✅ КОДОВОЕ СЛОВО ПРИНЯТО!\n\n"
            "Заявка на гражданство отправлена Президенту.\n"
            "Ожидай одобрения."
        )
        return
    await message.answer("❌ Неверное кодовое слово.\n\nПодсказка: два слова, связанные с Эфиопией и Богом.")


# ===== ЗАКОНЫ: просмотр =====
@dp.callback_query(lambda c: c.data.startswith("law_view|"))
async def law_view(callback: types.CallbackQuery):
    try:
        lid = int(callback.data.split("|")[1])
        law = await get_law(lid)
        if not law:
            await callback.answer("Не найден.", show_alert=True)
            return
        text = f"📜 ЗАКОН #{lid}\n\n«{law['title']}»\n\n{law['description']}\n\nАвтор: {law['author_username']}\nСтатус: {law['status']}\nГолоса: за {law['duma_votes_for']}, против {law['duma_votes_against']}"
        username = normalize_username(callback.from_user.username)
        buttons = []
        if law["status"] == "duma" and await has_role_by_username(username, "deputy"):
            buttons.append([InlineKeyboardButton(text="✅ За", callback_data=f"law_vote|{lid}|for")])
            buttons.append([InlineKeyboardButton(text="❌ Против", callback_data=f"law_vote|{lid}|against")])
        buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="laws_back")])
        try:
            await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        except Exception:
            await callback.message.answer(text)
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "laws_back")
async def laws_back(callback: types.CallbackQuery):
    try:
        laws = await get_all_laws()
        sn = {"duma": "🟡", "government": "🟠", "president": "🔵", "approved": "🟢", "vetoed": "🔴"}
        buttons = []
        for l in laws[:15]:
            buttons.append([InlineKeyboardButton(text=f"#{l['id']} {l['title'][:25]} {sn.get(l['status'], '')}", callback_data=f"law_view|{l['id']}")])
        try:
            await callback.message.edit_text("📜 ЗАКОНЫ", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        except Exception:
            await callback.message.answer("📜 ЗАКОНЫ")
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
        if not await has_role_by_username(username, "deputy"):
            await callback.answer("Только депутаты.", show_alert=True)
            return
        ok, msg = await vote_law(lid, username, vote)
        if not ok:
            await callback.answer(msg, show_alert=True)
            return
        await callback.answer("Голос принят!")
        law = await get_law(lid)
        async with db_pool.acquire() as conn:
            total = await conn.fetchval("SELECT COUNT(*) FROM subject_roles sr JOIN roles r ON r.id = sr.role_id WHERE r.code = 'deputy'")
            voted = await conn.fetchval("SELECT COUNT(*) FROM law_votes WHERE law_id = $1", lid)
        if voted >= total and total > 0:
            await update_law_status(lid, "government")
            await add_news(f"📜 Закон «{law['title']}» прошёл ГосДуму")
            await callback.message.answer("✅ Все проголосовали. Закон направлен в Правительство.")
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.message(Command("law"))
async def cmd_law(message: types.Message, state: FSMContext):
    username = normalize_username(message.from_user.username)
    if not await has_role_by_username(username, "deputy"):
        await message.answer("❌ Только депутаты ГосДумы могут вносить законы.")
        return
    await message.answer("📜 ВНЕСЕНИЕ ЗАКОНА\n\nШаг 1/2. Отправь НАЗВАНИЕ (минимум 3 символа).")
    await state.set_state(LawForm.waiting_title)


# ===== СОЗЫВ СОБРАНИЯ ГОСДУМЫ =====
@dp.message(Command("duma_session"))
async def cmd_duma_session(message: types.Message):
    username = normalize_username(message.from_user.username)
    if not await has_role_by_username(username, "deputy"):
        await message.answer("❌ Только депутаты ГосДумы могут созвать собрание.")
        return
    laws = await get_all_laws(status="duma")
    if not laws:
        await message.answer("Нет законопроектов на голосование.")
        return
    buttons = []
    for l in laws:
        buttons.append([InlineKeyboardButton(text=f"#{l['id']} {l['title'][:30]}", callback_data=f"duma_session_start|{l['id']}")])
    await message.answer("🏛 СОЗЫВ СОБРАНИЯ ГОСДУМЫ\n\nВыбери законопроект:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


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
            await callback.answer("Не найден.", show_alert=True)
            return
        deadline = now_msk() + timedelta(days=1)
        async with db_pool.acquire() as conn:
            deputies = await conn.fetch("SELECT s.user_id FROM subjects s JOIN subject_roles sr ON sr.subject_id = s.id JOIN roles r ON r.id = sr.role_id WHERE r.code = 'deputy' AND s.user_id IS NOT NULL")
        text = (
            f"🏛 ПОВЕСТКА ДНЯ ГОСДУМЫ\n\n"
            f"Законопроект #{lid}: «{law['title']}»\n\n"
            f"{law['description']}\n\n"
            f"Автор: {law['author_username']}\n"
            f"Дедлайн: {deadline.strftime('%d.%m.%Y %H:%M')} МСК\n\n"
            f"Голосуй: /laws"
        )
        sent = 0
        for d in deputies:
            try:
                await callback.bot.send_message(d["user_id"], text)
                sent += 1
            except Exception as e:
                print(f"Не смог {d['user_id']}: {e}")
        try:
            await callback.message.edit_text(f"✅ Собрание созвано. Повестка отправлена {sent} депутатам.")
        except Exception:
            await callback.message.answer(f"✅ Собрание созвано. Повестка отправлена {sent} депутатам.")
        await add_news(f"🏛 Собрание ГосДумы: законопроект «{law['title']}»")
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


# ===== ВЫБОРЫ В ГОСДУМУ =====
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
        await message.answer("Нет партий для голосования.")
        return
    buttons = [[InlineKeyboardButton(text=f"{p['emoji']} {p['name']}", callback_data=f"duma_vote|{election['id']}|{p['id']}")] for p in parties]
    await message.answer(
        f"🗳 ГОЛОСОВАНИЕ В ГОСДУМУ\n\n"
        f"До: {from_db_dt(election['ends_at']).strftime('%d.%m.%Y %H:%M')} МСК\n\n"
        f"Выбери партию:",
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
        subject = await get_subject(callback.from_user.id, username)
        voter_name = subject["full_name"] if subject else username

        caption = (
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "✅ ГОЛОС ПРИНЯТ!\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"👤 Субъект: {voter_name}\n"
            f"🗳 Партия: {party['emoji']} {party['name']}"
        )

        if VIDEO_FILE_ID:
            try:
                await callback.message.answer_video(video=VIDEO_FILE_ID, caption=caption)
            except Exception as e:
                print(f"Не смог отправить видео: {e}")
                await callback.message.answer(caption)
        else:
            await callback.message.answer(caption)

        await callback.answer("Голос принят!")
    except Exception as e:
        print(f"Ошибка duma_vote: {e}")
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
            await callback.answer("Не найдена.", show_alert=True)
            return
        text = await build_party_detail_text(party)
        username = normalize_username(callback.from_user.username)
        user_party = await get_user_party(username)
        buttons = []
        if user_party and user_party["id"] == pid:
            buttons.append([InlineKeyboardButton(text="🚪 Выйти из партии", callback_data=f"party_leave|{pid}")])
        elif not user_party:
            buttons.append([InlineKeyboardButton(text="✍️ Вступить в партию", callback_data=f"party_join|{pid}")])
        buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="party_back")])
        try:
            await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        except Exception:
            await callback.message.answer(text)
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "party_back")
async def party_back(callback: types.CallbackQuery):
    try:
        parties = await get_all_parties()
        text = await build_parties_list_text()
        buttons = [[InlineKeyboardButton(text=f"{p['emoji']} {p['name']}", callback_data=f"party_view|{p['id']}")] for p in parties]
        buttons.append([InlineKeyboardButton(text="➕ Создать партию", callback_data="party_create")])
        buttons.append([InlineKeyboardButton(text="🏆 Кладбище партий", callback_data="party_graveyard")])
        try:
            await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        except Exception:
            await callback.message.answer(text)
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
        text = "🏆 КЛАДБИЩЕ ПАРТИЙ\n\n"
        if not dead:
            text += "Пусто."
        for p in dead:
            text += f"💀 {p['emoji']} {p['name']} (RIP)\n"
        buttons = [[InlineKeyboardButton(text="◀️ Назад", callback_data="party_back")]]
        try:
            await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        except Exception:
            await callback.message.answer(text)
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
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
        if await get_user_party(username):
            await callback.answer("Ты уже в партии.", show_alert=True)
            return
        party = await get_party(pid)
        if not party:
            await callback.answer("Не найдена.", show_alert=True)
            return
        await create_application("join_party", username, subject["full_name"], party["leader_username"], {"party_id": pid, "party_name": party["name"]})
        await add_reputation(username, REP_RULES["application"])
        await callback.message.answer(f"✍️ Заявка на вступление в партию «{party['name']}» отправлена лидеру {party['leader_username']}.")
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("party_leave|"))
async def party_leave(callback: types.CallbackQuery):
    try:
        username = normalize_username(callback.from_user.username)
        await remove_party_member(username)
        try:
            await callback.message.edit_text("🚪 Ты покинул партию.")
        except Exception:
            await callback.message.answer("🚪 Ты покинул партию.")
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
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
            await callback.answer("Ты уже в партии. Сначала выйди.", show_alert=True)
            return
        await callback.message.answer("➕ СОЗДАНИЕ ПАРТИИ\n\nШаг 1/3. Отправь НАЗВАНИЕ (2-50 символов).")
        await state.set_state(PartyForm.waiting_name)
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


# ===== АДМИН-ПАНЕЛЬ =====
async def admin_check(callback):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Только админ.", show_alert=True)
        return False
    if not await is_admin_active(callback.from_user.id):
        await callback.answer("🔒 Админ-режим не активен. Нажми кнопку активации.", show_alert=True)
        return False
    return True


@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Только админ.")
        return
    active = await is_admin_active(message.from_user.id)
    status = "🔓 АКТИВЕН" if active else "🔒 НЕ АКТИВЕН"
    await message.answer(f"🛠 АДМИН-ПАНЕЛЬ\n\nСтатус: {status}\n\nВыбери действие:", reply_markup=build_admin_keyboard(active))


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
        try:
            await callback.message.edit_text(f"🛠 АДМИН-ПАНЕЛЬ\n\nСтатус: {status}\n\nВыбери:", reply_markup=build_admin_keyboard(active))
        except Exception:
            await callback.message.answer(f"🛠 АДМИН-ПАНЕЛЬ\n\nСтатус: {status}", reply_markup=build_admin_keyboard(active))
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
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
        try:
            await callback.message.edit_text(f"🛠 АДМИН-ПАНЕЛЬ\n\nСтатус: {status}\n\nВыбери:", reply_markup=build_admin_keyboard(active))
        except Exception:
            await callback.message.answer(f"🛠 АДМИН-ПАНЕЛЬ\n\nСтатус: {status}", reply_markup=build_admin_keyboard(active))
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_subjects")
async def admin_subjects(callback: types.CallbackQuery):
    try:
        if not await admin_check(callback):
            return
        try:
            await callback.message.edit_text("👥 СУБЪЕКТЫ", reply_markup=build_admin_subjects_keyboard())
        except Exception:
            await callback.message.answer("👥 СУБЪЕКТЫ", reply_markup=build_admin_subjects_keyboard())
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_subjects_list")
async def admin_subjects_list(callback: types.CallbackQuery):
    try:
        if not await admin_check(callback):
            return
        kb = await build_admin_subjects_list_keyboard()
        try:
            await callback.message.edit_text("👥 СУБЪЕКТЫ\n\nВыбери:", reply_markup=kb)
        except Exception:
            await callback.message.answer("👥 СУБЪЕКТЫ", reply_markup=kb)
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("admin_subj_view|"))
async def admin_subj_view(callback: types.CallbackQuery):
    try:
        if not await admin_check(callback):
            return
        sid = int(callback.data.split("|")[1])
        async with db_pool.acquire() as conn:
            subject = await conn.fetchrow("SELECT * FROM subjects WHERE id = $1", sid)
        if not subject:
            await callback.answer("Не найден.", show_alert=True)
            return
        roles = await get_subject_roles(subject["id"])
        user_party = await get_user_party(subject["username"])
        await callback.message.answer(build_subject_profile(subject, roles, user_party, False))
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_assign_role_subj")
async def admin_assign_role_subj(callback: types.CallbackQuery):
    try:
        if not await admin_check(callback):
            return
        kb = await build_admin_assign_role_subj_keyboard()
        try:
            await callback.message.edit_text("➕ ВЫДАТЬ ДОЛЖНОСТЬ\n\nВыбери субъекта:", reply_markup=kb)
        except Exception:
            await callback.message.answer("➕ ВЫДАТЬ ДОЛЖНОСТЬ", reply_markup=kb)
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("admin_assign_subj|"))
async def admin_assign_subj(callback: types.CallbackQuery):
    try:
        if not await admin_check(callback):
            return
        sid = int(callback.data.split("|")[1])
        kb = await build_admin_assign_role_keyboard(sid)
        try:
            await callback.message.edit_text("➕ ВЫБЕРИ ДОЛЖНОСТЬ", reply_markup=kb)
        except Exception:
            await callback.message.answer("➕ ВЫБЕРИ ДОЛЖНОСТЬ", reply_markup=kb)
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("admin_assign_role|"))
async def admin_assign_role(callback: types.CallbackQuery):
    try:
        if not await admin_check(callback):
            return
        parts = callback.data.split("|")
        sid = int(parts[1])
        rid = int(parts[2])
        ok, msg = await assign_role(sid, rid, ADMIN_ID)
        if ok:
            async with db_pool.acquire() as conn:
                subject = await conn.fetchrow("SELECT * FROM subjects WHERE id = $1", sid)
                role = await conn.fetchrow("SELECT * FROM roles WHERE id = $1", rid)
            await add_news(f"👑 {subject['full_name']} назначен: {role['name']}")
            try:
                await callback.message.edit_text(f"✅ {subject['full_name']} → {role['name']}")
            except Exception:
                await callback.message.answer(f"✅ {subject['full_name']} → {role['name']}")
        else:
            await callback.message.answer(f"❌ {msg}")
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_remove_role_subj")
async def admin_remove_role_subj(callback: types.CallbackQuery):
    try:
        if not await admin_check(callback):
            return
        kb = await build_admin_remove_role_subj_keyboard()
        try:
            await callback.message.edit_text("➖ СНЯТЬ ДОЛЖНОСТЬ\n\nВыбери:", reply_markup=kb)
        except Exception:
            await callback.message.answer("➖ СНЯТЬ ДОЛЖНОСТЬ", reply_markup=kb)
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("admin_remove_subj|"))
async def admin_remove_subj(callback: types.CallbackQuery):
    try:
        if not await admin_check(callback):
            return
        sid = int(callback.data.split("|")[1])
        kb = await build_admin_remove_role_keyboard(sid)
        try:
            await callback.message.edit_text("➖ ВЫБЕРИ ДОЛЖНОСТЬ", reply_markup=kb)
        except Exception:
            await callback.message.answer("➖ ВЫБЕРИ ДОЛЖНОСТЬ", reply_markup=kb)
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("admin_remove_role|"))
async def admin_remove_role(callback: types.CallbackQuery):
    try:
        if not await admin_check(callback):
            return
        parts = callback.data.split("|")
        sid = int(parts[1])
        rid = int(parts[2])
        await remove_role(sid, rid)
        try:
            await callback.message.edit_text("✅ Должность снята.")
        except Exception:
            await callback.message.answer("✅ Должность снята.")
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_parties")
async def admin_parties(callback: types.CallbackQuery):
    try:
        if not await admin_check(callback):
            return
        try:
            await callback.message.edit_text("🎭 ПАРТИИ", reply_markup=build_admin_parties_keyboard())
        except Exception:
            await callback.message.answer("🎭 ПАРТИИ", reply_markup=build_admin_parties_keyboard())
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_parties_list")
async def admin_parties_list(callback: types.CallbackQuery):
    try:
        if not await admin_check(callback):
            return
        kb = await build_admin_parties_list_keyboard()
        try:
            await callback.message.edit_text("🎭 ПАРТИИ", reply_markup=kb)
        except Exception:
            await callback.message.answer("🎭 ПАРТИИ", reply_markup=kb)
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_party_graveyard")
async def admin_party_graveyard(callback: types.CallbackQuery):
    try:
        if not await admin_check(callback):
            return
        async with db_pool.acquire() as conn:
            dead = await conn.fetch("SELECT * FROM parties WHERE status = 'dissolved' ORDER BY id DESC")
        text = "🏆 КЛАДБИЩЕ ПАРТИЙ\n\n"
        for p in dead:
            text += f"💀 {p['emoji']} {p['name']} (RIP)\n"
        if not dead:
            text += "Пусто."
        buttons = [[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_parties")]]
        try:
            await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        except Exception:
            await callback.message.answer(text)
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("admin_party_view|"))
async def admin_party_view(callback: types.CallbackQuery):
    try:
        if not await admin_check(callback):
            return
        pid = int(callback.data.split("|")[1])
        party = await get_party(pid)
        if not party:
            await callback.answer("Не найдена.", show_alert=True)
            return
        await callback.message.answer(await build_party_detail_text(party) + f"\n\nСтатус: {party['status']}")
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_dissolve_party")
async def admin_dissolve_party(callback: types.CallbackQuery):
    try:
        if not await admin_check(callback):
            return
        kb = await build_admin_dissolve_party_keyboard()
        try:
            await callback.message.edit_text("🗑 РАСПУСТИТЬ ПАРТИЮ", reply_markup=kb)
        except Exception:
            await callback.message.answer("🗑 РАСПУСТИТЬ ПАРТИЮ", reply_markup=kb)
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("admin_dissolve|"))
async def admin_dissolve(callback: types.CallbackQuery):
    try:
        if not await admin_check(callback):
            return
        pid = int(callback.data.split("|")[1])
        party = await get_party(pid)
        await dissolve_party(pid)
        if party:
            await add_news(f"💀 Партия «{party['name']}» распущена (RIP)")
            await add_reputation(party["leader_username"], REP_RULES["party_dissolved"])
        try:
            await callback.message.edit_text("✅ Партия распущена.")
        except Exception:
            await callback.message.answer("✅ Партия распущена.")
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_change_leader")
async def admin_change_leader(callback: types.CallbackQuery):
    try:
        if not await admin_check(callback):
            return
        kb = await build_admin_change_leader_keyboard()
        try:
            await callback.message.edit_text("👑 СМЕНИТЬ ЛИДЕРА", reply_markup=kb)
        except Exception:
            await callback.message.answer("👑 СМЕНИТЬ ЛИДЕРА", reply_markup=kb)
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("admin_leader_party|"))
async def admin_leader_party(callback: types.CallbackQuery):
    try:
        if not await admin_check(callback):
            return
        pid = int(callback.data.split("|")[1])
        kb = await build_admin_leader_subject_keyboard(pid)
        try:
            await callback.message.edit_text("👑 НОВЫЙ ЛИДЕР\n\nВыбери субъекта:", reply_markup=kb)
        except Exception:
            await callback.message.answer("👑 НОВЫЙ ЛИДЕР", reply_markup=kb)
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("admin_leader_set|"))
async def admin_leader_set(callback: types.CallbackQuery):
    try:
        if not await admin_check(callback):
            return
        parts = callback.data.split("|")
        pid = int(parts[1])
        new_leader = parts[2]
        party = await get_party(pid)
        old_leader = party["leader_username"] if party else None
        await change_party_leader(pid, new_leader)
        if old_leader and old_leader != new_leader:
            await transfer_applications(old_leader, new_leader)
        try:
            await callback.message.edit_text(f"✅ Новый лидер: {new_leader}")
        except Exception:
            await callback.message.answer(f"✅ Новый лидер: {new_leader}")
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_apps")
async def admin_apps(callback: types.CallbackQuery):
    try:
        if not await admin_check(callback):
            return
        apps = await get_pending_applications()
        if not apps:
            try:
                await callback.message.edit_text("📋 Заявок нет.", reply_markup=build_admin_keyboard(True))
            except Exception:
                await callback.message.answer("📋 Заявок нет.")
            await callback.answer()
            return
        text = "📋 ЗАЯВКИ\n\n"
        buttons = []
        for a in apps:
            text += f"#{a['id']} — {a['type']} ({a['author_username']})\n"
            buttons.append([InlineKeyboardButton(text=f"#{a['id']}", callback_data=f"admin_app_view|{a['id']}")])
        buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")])
        try:
            await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        except Exception:
            await callback.message.answer(text)
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("admin_app_view|"))
async def admin_app_view(callback: types.CallbackQuery):
    try:
        if not await admin_check(callback):
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
            [InlineKeyboardButton(text="✅ Одобрить", callback_data=f"admin_app_approve|{app_id}")],
            [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin_app_reject|{app_id}")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_apps")],
        ]
        try:
            await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        except Exception:
            await callback.message.answer(text)
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("admin_app_approve|"))
async def admin_app_approve(callback: types.CallbackQuery):
    try:
        if not await admin_check(callback):
            return
        app_id = int(callback.data.split("|")[1])
        await handle_app_approve(app_id, ADMIN_ID, callback.bot)
        try:
            await callback.message.edit_text(f"✅ Заявка #{app_id} одобрена. Автор уведомлён.")
        except Exception:
            await callback.message.answer(f"✅ Заявка #{app_id} одобрена.")
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("admin_app_reject|"))
async def admin_app_reject(callback: types.CallbackQuery):
    try:
        if not await admin_check(callback):
            return
        app_id = int(callback.data.split("|")[1])
        await handle_app_reject(app_id, ADMIN_ID, "Отклонено админом", callback.bot)
        try:
            await callback.message.edit_text(f"❌ Заявка #{app_id} отклонена. Автор уведомлён.")
        except Exception:
            await callback.message.answer(f"❌ Заявка #{app_id} отклонена.")
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_laws")
async def admin_laws(callback: types.CallbackQuery):
    try:
        if not await admin_check(callback):
            return
        laws = await get_all_laws()
        if not laws:
            try:
                await callback.message.edit_text("📜 Законов нет.", reply_markup=build_admin_keyboard(True))
            except Exception:
                await callback.message.answer("📜 Законов нет.")
            await callback.answer()
            return
        sn = {"duma": "🟡", "government": "🟠", "president": "🔵", "approved": "🟢", "vetoed": "🔴"}
        buttons = []
        for l in laws:
            buttons.append([InlineKeyboardButton(text=f"#{l['id']} {l['title'][:25]} {sn.get(l['status'], '')}", callback_data=f"admin_law_view|{l['id']}")])
        buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")])
        try:
            await callback.message.edit_text("📜 ЗАКОНЫ", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        except Exception:
            await callback.message.answer("📜 ЗАКОНЫ")
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("admin_law_view|"))
async def admin_law_view(callback: types.CallbackQuery):
    try:
        if not await admin_check(callback):
            return
        lid = int(callback.data.split("|")[1])
        law = await get_law(lid)
        if not law:
            await callback.answer("Не найден.", show_alert=True)
            return
        text = f"📜 #{lid} «{law['title']}»\n\n{law['description']}\n\nСтатус: {law['status']}"
        buttons = []
        if law["status"] == "government":
            buttons.append([InlineKeyboardButton(text="✅ Правительство OK", callback_data=f"admin_law_gov|{lid}")])
            buttons.append([InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin_law_gov_rej|{lid}")])
        if law["status"] == "president":
            buttons.append([InlineKeyboardButton(text="✅ Подписать", callback_data=f"admin_law_sign|{lid}")])
            buttons.append([InlineKeyboardButton(text="❌ Вето", callback_data=f"admin_law_veto|{lid}")])
        buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_laws")])
        try:
            await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        except Exception:
            await callback.message.answer(text)
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("admin_law_gov|"))
async def admin_law_gov(callback: types.CallbackQuery):
    try:
        if not await admin_check(callback):
            return
        lid = int(callback.data.split("|")[1])
        await update_law_status(lid, "president")
        try:
            await callback.message.edit_text("✅ Направлено Президенту.")
        except Exception:
            await callback.message.answer("✅ Направлено Президенту.")
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("admin_law_gov_rej|"))
async def admin_law_gov_rej(callback: types.CallbackQuery):
    try:
        if not await admin_check(callback):
            return
        lid = int(callback.data.split("|")[1])
        await update_law_status(lid, "vetoed")
        try:
            await callback.message.edit_text("❌ Отклонено Правительством.")
        except Exception:
            await callback.message.answer("❌ Отклонено.")
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("admin_law_sign|"))
async def admin_law_sign(callback: types.CallbackQuery):
    try:
        if not await admin_check(callback):
            return
        lid = int(callback.data.split("|")[1])
        law = await get_law(lid)
        await update_law_status(lid, "approved")
        await add_news(f"🟢 Закон «{law['title']}» подписан Президентом!")
        await add_reputation(law["author_username"], REP_RULES["law_approved"])
        try:
            await callback.message.edit_text("✅ Закон подписан.")
        except Exception:
            await callback.message.answer("✅ Закон подписан.")
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("admin_law_veto|"))
async def admin_law_veto(callback: types.CallbackQuery):
    try:
        if not await admin_check(callback):
            return
        lid = int(callback.data.split("|")[1])
        law = await get_law(lid)
        await update_law_status(lid, "vetoed")
        await add_reputation(law["author_username"], REP_RULES["law_rejected"])
        try:
            await callback.message.edit_text("❌ Вето.")
        except Exception:
            await callback.message.answer("❌ Вето.")
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_decrees")
async def admin_decrees(callback: types.CallbackQuery):
    try:
        if not await admin_check(callback):
            return
        decrees = await get_all_decrees()
        text = "📢 УКАЗЫ\n\n"
        for d in decrees:
            marker = "🔒" if d["is_secret"] else "📢"
            text += f"{marker} #{d['id']} {d['title']}\n"
        if not decrees:
            text += "Пусто.\n"
        buttons = [[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]]
        try:
            await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        except Exception:
            await callback.message.answer(text)
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_news")
async def admin_news(callback: types.CallbackQuery):
    try:
        if not await admin_check(callback):
            return
        news = await get_news(20)
        text = "📰 НОВОСТИ\n\n"
        for n in news:
            dt = n["created_at"].strftime("%d.%m %H:%M") if n["created_at"] else "—"
            text += f"[{dt}] {n['text']}\n\n"
        if not news:
            text += "Пусто.\n"
        buttons = [
            [InlineKeyboardButton(text="➕ Добавить", callback_data="admin_news_add")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")],
        ]
        try:
            await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        except Exception:
            await callback.message.answer(text)
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_news_add")
async def admin_news_add(callback: types.CallbackQuery, state: FSMContext):
    try:
        if not await admin_check(callback):
            return
        await callback.message.answer("📰 Отправь текст новости.")
        await state.set_state(NewsForm.waiting_text)
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_duma")
async def admin_duma(callback: types.CallbackQuery):
    try:
        if not await admin_check(callback):
            return
        buttons = [
            [InlineKeyboardButton(text="🗳 Начать выборы", callback_data="admin_duma_start")],
            [InlineKeyboardButton(text="🛑 Завершить досрочно", callback_data="admin_duma_finish_now")],
            [InlineKeyboardButton(text="📊 Результаты", callback_data="admin_duma_results")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")],
        ]
        try:
            await callback.message.edit_text("🗳 ГОСДУМА", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        except Exception:
            await callback.message.answer("🗳 ГОСДУМА", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_duma_start")
async def admin_duma_start(callback: types.CallbackQuery, state: FSMContext):
    try:
        if not await admin_check(callback):
            return
        if await get_active_duma_election():
            await callback.answer("Выборы уже идут.", show_alert=True)
            return
        await callback.message.answer(
            "🗳 Отправь ДАТУ окончания.\n\n"
            "Форматы:\n2027-01-15 20:00\n15-01-2027 20:00\n15.01.2027 20:00"
        )
        await state.set_state(ElectionForm.waiting_date_end)
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_duma_finish_now")
async def admin_duma_finish_now(callback: types.CallbackQuery):
    try:
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("Только админ.", show_alert=True)
            return
        active = await get_active_duma_election()
        if not active:
            await callback.answer("Нет активных выборов.", show_alert=True)
            return
        winners = await finish_duma_election(active["id"])
        text = "🛑 ВЫБОРЫ ЗАВЕРШЕНЫ ДОСРОЧНО!\n\n"
        for w in winners:
            text += f"{w['place']}. {w['party']} ({w['votes']}) — {', '.join(w['deputies'])}\n"
        await callback.message.answer(text)
        for s in await get_all_subjects():
            if s["user_id"] and s["user_id"] > 0:
                try:
                    await callback.bot.send_message(s["user_id"], "🛑 ВЫБОРЫ В ГОСДУМУ ЗАВЕРШЕНЫ ДОСРОЧНО!\n\nСмотри результаты: /duma")
                except Exception:
                    pass
        await callback.answer("Готово!")
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_pres_finish_now")
async def admin_pres_finish_now(callback: types.CallbackQuery):
    try:
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("Только админ.", show_alert=True)
            return
        term = await get_active_president_term()
        if not term:
            await callback.answer("Президент не выбран.", show_alert=True)
            return
        await force_finish_president()
        await callback.message.answer(f"👑 Президент ({term['username']}) снят досрочно.")
        await callback.answer("Готово!")
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_duma_results")
async def admin_duma_results(callback: types.CallbackQuery):
    try:
        if not await admin_check(callback):
            return
        async with db_pool.acquire() as conn:
            elections = await conn.fetch("SELECT * FROM duma_elections ORDER BY id DESC LIMIT 5")
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
                    text += f"  {r.get('place')}. {r['party']} ({r['votes']}) — {', '.join(r.get('deputies', []))}\n"
            text += "\n"
        if not elections:
            text += "Не было."
        buttons = [[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_duma")]]
        try:
            await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        except Exception:
            await callback.message.answer(text)
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_results")
async def admin_results(callback: types.CallbackQuery):
    try:
        if not await admin_check(callback):
            return
        await callback.message.answer(await build_results_text())
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_status")
async def admin_status(callback: types.CallbackQuery):
    try:
        if not await admin_check(callback):
            return
        await callback.message.answer(await build_status_text())
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_add_vote")
async def admin_add_vote(callback: types.CallbackQuery):
    try:
        if not await admin_check(callback):
            return
        try:
            await callback.message.edit_text("✍️ ВНЕСТИ ГОЛОС\n\nЗа кого?", reply_markup=build_admin_add_vote_keyboard())
        except Exception:
            await callback.message.answer("✍️ ВНЕСТИ ГОЛОС", reply_markup=build_admin_add_vote_keyboard())
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("admin_addvote_subj|"))
async def admin_addvote_subj(callback: types.CallbackQuery):
    try:
        if not await admin_check(callback):
            return
        username = callback.data.split("|", 1)[1]
        info = VOTERS.get(username)
        if not info:
            await callback.answer("Не найден.", show_alert=True)
            return
        try:
            await callback.message.edit_text(f"✍️ {info['name']}\n\nЗа кого?", reply_markup=build_admin_add_candidate_keyboard(username))
        except Exception:
            await callback.message.answer(f"✍️ {info['name']}", reply_markup=build_admin_add_candidate_keyboard(username))
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("admin_addvote_cand|"))
async def admin_addvote_cand(callback: types.CallbackQuery):
    try:
        if not await admin_check(callback):
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
            await callback.message.edit_text(f"✅ {info['name']} → {CANDIDATES[cid]['name']}")
        except Exception:
            await callback.message.answer(f"✅ {info['name']} → {CANDIDATES[cid]['name']}")
        await callback.answer("Готово!")
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_reset_confirm")
async def admin_reset_confirm(callback: types.CallbackQuery):
    try:
        if not await admin_check(callback):
            return
        try:
            await callback.message.edit_text("⚠️ СБРОСИТЬ ВСЕ ГОЛОСА?", reply_markup=build_admin_confirm_reset_keyboard())
        except Exception:
            await callback.message.answer("⚠️ СБРОСИТЬ?", reply_markup=build_admin_confirm_reset_keyboard())
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_reset_yes")
async def admin_reset_yes(callback: types.CallbackQuery):
    try:
        if not await admin_check(callback):
            return
        await clear_votes()
        try:
            await callback.message.edit_text("🔄 Сброшено.")
        except Exception:
            await callback.message.answer("🔄 Сброшено.")
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


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
        print(f"Ошибка: {e}")
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
        await callback.answer("Пометка")
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
        suffix = "\n\nМожешь ещё." if tester else ""
        caption = f"━━━━━━━━━━━━━━━━━━━━━\n✅ ГОЛОС ПРИНЯТ!\n━━━━━━━━━━━━━━━━━━━━━\n\n👤 {voter_name}\n🗳 {candidate_name}{suffix}"
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
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.message(Command("results"))
async def cmd_results(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Только админ.")
        return
    if not await get_all_votes():
        await message.answer("📊 Никто не голосовал.")
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
                        print(f"Не смог {uid}: {e}")
                if ADMIN_ID not in sent_to:
                    try:
                        await bot.send_message(ADMIN_ID, text)
                    except Exception:
                        pass
                flags["election_end_notified"] = True

            try:
                active_e = await get_active_duma_election()
                if active_e and active_e["ends_at"] and now_msk() >= from_db_dt(active_e["ends_at"]):
                    winners = await finish_duma_election(active_e["id"])
                    text = "🗳 ВЫБОРЫ В ГОСДУМУ ЗАВЕРШЕНЫ!\n\n"
                    for w in winners:
                        text += f"{w['place']}. {w['party']} ({w['votes']} голосов)\n   Депутаты: {', '.join(w['deputies'])}\n\n"
                    await add_news("🗳 Выборы в ГосДуму завершены!")
                    for s in await get_all_subjects():
                        if s["user_id"] and s["user_id"] > 0:
                            try:
                                await bot.send_message(s["user_id"], text)
                            except Exception:
                                pass
            except Exception as e:
                print(f"duma watcher: {e}")

            try:
                term = await get_active_president_term()
                if term and term["ends_at"] and now_msk() >= from_db_dt(term["ends_at"]):
                    await force_finish_president()
                    try:
                        await bot.send_message(ADMIN_ID, "👑 Срок Президента истёк. Нужны новые выборы.")
                    except Exception:
                        pass
            except Exception as e:
                print(f"pres watcher: {e}")

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

# ===== КОНЕЦ ЧАСТИ 3 =====
