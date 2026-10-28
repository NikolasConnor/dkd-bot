import asyncio
import os
import json
from datetime import datetime, timedelta, timezone

import asyncpg
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, StateFilter
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_ID = 7934244888
MSK = timezone(timedelta(hours=3))
ELECTION_START = datetime(2026, 10, 4, 14, 0, tzinfo=MSK)
ELECTION_END = datetime(2026, 10, 6, 18, 0, tzinfo=MSK)
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
REP_RULES = {"vote": 1, "application": 2, "application_approved": 5, "application_rejected": -2, "law_approved": 10, "law_rejected": -3, "party_created": 15, "party_dissolved": -10, "list_not_formed": -10}

db_pool = None
flags = {"test_end_notified": False, "election_end_notified": False, "pres_election_notified": False}

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

class ProfileForm(StatesGroup):
    waiting_fio = State()

class BroadcastForm(StatesGroup):
    waiting_text = State()

class PresidentAddressForm(StatesGroup):
    waiting_text = State()

class PartyListForm(StatesGroup):
    waiting_members = State()

dp = Dispatcher()

def normalize_username(username):
    if not username: return None
    if not username.startswith("@"): return "@" + username
    return username

def now_msk():
    return datetime.now(MSK)

def to_db_dt(dt):
    if dt is None: return None
    if dt.tzinfo is not None: return dt.astimezone(MSK).replace(tzinfo=None)
    return dt

def from_db_dt(dt):
    if dt is None: return None
    if dt.tzinfo is None: return dt.replace(tzinfo=MSK)
    return dt

def parse_date_flexible(text):
    if not text: return None
    t = text.strip().replace(".", "-").replace("/", "-").replace(",", " ")
    formats = ["%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H.%M", "%d-%m-%Y %H:%M", "%d-%m-%Y %H.%M", "%d-%m-%y %H:%M"]
    for fmt in formats:
        try:
            dt = datetime.strptime(t, fmt)
            return dt.replace(tzinfo=MSK)
        except Exception:
            continue
    return None

def check_secret_word(text):
    if not text: return False
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
        await conn.execute("""CREATE TABLE IF NOT EXISTS party_lists (id SERIAL PRIMARY KEY, party_id INTEGER REFERENCES parties(id) ON DELETE CASCADE, election_id INTEGER REFERENCES duma_elections(id) ON DELETE CASCADE, username TEXT NOT NULL, UNIQUE(party_id, election_id, username))""")
        await conn.execute("""CREATE TABLE IF NOT EXISTS pres_elections (id SERIAL PRIMARY KEY, started_at TIMESTAMP DEFAULT NOW(), ends_at TIMESTAMP, status TEXT DEFAULT 'active')""")

async def preload_roles():
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT value FROM service_flags WHERE key = 'roles_loaded'")
        if row is not None: return
        for r in ROLES_INITIAL:
            await conn.execute("INSERT INTO roles (code, name, emoji, max_holders) VALUES ($1, $2, $3, $4) ON CONFLICT (code) DO NOTHING", r["code"], r["name"], r["emoji"], r["max_holders"])
        await conn.execute("INSERT INTO service_flags (key, value) VALUES ('roles_loaded', 'done')")

async def preload_subjects():
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT value FROM service_flags WHERE key = 'subjects_loaded'")
        if row is not None: return
        for s in SUBJECTS_INITIAL:
            await conn.execute("INSERT INTO subjects (username, full_name, is_citizen) VALUES ($1, $2, TRUE) ON CONFLICT (username) DO NOTHING", normalize_username(s["username"]), s["full_name"])
        await conn.execute("INSERT INTO service_flags (key, value) VALUES ('subjects_loaded', 'done')")

async def preload_initial_roles():
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT value FROM service_flags WHERE key = 'initial_roles_loaded'")
        if row is not None: return
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
        if row is not None: return
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
        if row is not None: return
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

async def clear_votes():
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM votes")
        await conn.execute("DELETE FROM service_flags WHERE key = 'preloaded_votes'")

async def get_subject_by_user_id(user_id):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM subjects WHERE user_id = $1", user_id)

async def get_subject_by_username(username):
    username = normalize_username(username)
    if not username: return None
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
    if not username: return
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE subjects SET reputation = reputation + $1 WHERE username = $2", amount, username)

async def get_subject_roles(subject_id):
    async with db_pool.acquire() as conn:
        return await conn.fetch("SELECT r.* FROM roles r JOIN subject_roles sr ON sr.role_id = r.id WHERE sr.subject_id = $1 ORDER BY r.id", subject_id)

async def assign_role(subject_id, role_id, assigned_by):
    async with db_pool.acquire() as conn:
        cnt = await conn.fetchval("SELECT COUNT(*) FROM subject_roles WHERE subject_id = $1", subject_id)
        if cnt >= 2: return False, "Максимум 2 должности"
        role = await conn.fetchrow("SELECT * FROM roles WHERE id = $1", role_id)
        if not role: return False, "Роль не найдена"
        if role["max_holders"] is not None:
            holders = await conn.fetchval("SELECT COUNT(*) FROM subject_roles WHERE role_id = $1", role_id)
            if holders >= role["max_holders"]: return False, f"Роль «{role['name']}» занята"
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
        if s: return s
    if user_id: return await get_subject_by_user_id(user_id)
    return None

async def has_role_by_username(username, role_code):
    username = normalize_username(username)
    if not username: return False
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT 1 FROM subjects s JOIN subject_roles sr ON sr.subject_id = s.id JOIN roles r ON r.id = sr.role_id WHERE s.username = $1 AND r.code = $2", username, role_code)
        return row is not None

async def is_admin_active(user_id):
    if user_id != ADMIN_ID: return False
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT is_active FROM admin_sessions WHERE user_id = $1", user_id)
        return row and row["is_active"]

async def can_use_pres_panel(user_id, username):
    if user_id == ADMIN_ID: return True
    return await has_role_by_username(username, "president")

async def activate_admin(user_id):
    async with db_pool.acquire() as conn:
        await conn.execute("INSERT INTO admin_sessions (user_id, is_active, activated_at) VALUES ($1, TRUE, NOW()) ON CONFLICT (user_id) DO UPDATE SET is_active = TRUE, activated_at = NOW()", user_id)

async def deactivate_admin(user_id):
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE admin_sessions SET is_active = FALSE WHERE user_id = $1", user_id)

async def get_all_parties(active_only=True):
    async with db_pool.acquire() as conn:
        if active_only: return await conn.fetch("SELECT * FROM parties WHERE status = 'active' ORDER BY id")
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
    if not username: return None
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
        if target_username: return await conn.fetch("SELECT * FROM applications WHERE status = 'pending' AND target_username = $1 ORDER BY created_at", normalize_username(target_username))
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

async def notify_author(bot, app, status_text):
    if not app: return
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
        if status: return await conn.fetch("SELECT * FROM laws WHERE status = $1 ORDER BY id DESC", status)
        return await conn.fetch("SELECT * FROM laws ORDER BY id DESC")

async def vote_law(law_id, username, vote):
    username = normalize_username(username)
    async with db_pool.acquire() as conn:
        existing = await conn.fetchrow("SELECT id FROM law_votes WHERE law_id = $1 AND voter_username = $2", law_id, username)
        if existing: return False, "Ты уже голосовал"
        await conn.execute("INSERT INTO law_votes (law_id, voter_username, vote) VALUES ($1, $2, $3)", law_id, username, vote)
        if vote == "for": await conn.execute("UPDATE laws SET duma_votes_for = duma_votes_for + 1 WHERE id = $1", law_id)
        else: await conn.execute("UPDATE laws SET duma_votes_against = duma_votes_against + 1 WHERE id = $1", law_id)
        return True, "OK"

async def create_decree(title, text, author_username, is_secret=False, secret_for=None):
    async with db_pool.acquire() as conn:
        await conn.execute("INSERT INTO decrees (title, text, author_username, is_secret, secret_for) VALUES ($1, $2, $3, $4, $5)", title, text, normalize_username(author_username), is_secret, normalize_username(secret_for) if secret_for else None)

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

async def force_finish_president():
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE president_term SET status = 'finished' WHERE status = 'active'")
        role = await conn.fetchrow("SELECT id FROM roles WHERE code = 'president'")
        if role: await conn.execute("DELETE FROM subject_roles WHERE role_id = $1", role["id"])
    await add_news("👑 Президент снят досрочно.")
    return True

async def start_duma_election(ends_at):
    async with db_pool.acquire() as conn:
        await conn.execute("INSERT INTO duma_elections (ends_at, status) VALUES ($1, 'active')", to_db_dt(ends_at))
        return await conn.fetchrow("SELECT * FROM duma_elections ORDER BY id DESC LIMIT 1")

async def get_active_duma_election():
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM duma_elections WHERE status = 'active' ORDER BY id DESC LIMIT 1")

async def start_pres_election(ends_at):
    async with db_pool.acquire() as conn:
        await conn.execute("INSERT INTO pres_elections (ends_at, status) VALUES ($1, 'active')", to_db_dt(ends_at))
        return await conn.fetchrow("SELECT * FROM pres_elections ORDER BY id DESC LIMIT 1")

async def get_active_pres_election():
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM pres_elections WHERE status = 'active' ORDER BY id DESC LIMIT 1")

async def vote_duma(election_id, voter_username, party_id):
    async with db_pool.acquire() as conn:
        existing = await conn.fetchrow("SELECT id FROM duma_votes WHERE election_id = $1 AND voter_username = $2", election_id, normalize_username(voter_username))
        if existing: return False, "Ты уже голосовал"
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
            if not party: continue
            party_list = await conn.fetch("SELECT username FROM party_lists WHERE party_id = $1 AND election_id = $2", party["id"], election_id)
            allowed = max(0, len(party_list) - idx)
            deputies = [m["username"] for m in party_list[:allowed]]
            winners.append({"party": party["name"], "votes": r["cnt"], "deputies": deputies, "place": idx + 1})
            for d in deputies:
                subj = await conn.fetchrow("SELECT id FROM subjects WHERE username = $1", d)
                if subj and role:
                    await conn.execute("INSERT INTO subject_roles (subject_id, role_id, assigned_by) VALUES ($1, $2, $3) ON CONFLICT (subject_id, role_id) DO NOTHING", subj["id"], role["id"], ADMIN_ID)
        await conn.execute("UPDATE duma_elections SET status = 'finished', results = $1 WHERE id = $2", json.dumps(winners), election_id)
        return winners
        # ===== ТЕКСТЫ И КЛАВИАТУРЫ =====
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

def build_main_menu(user_id, role, admin_active=False):
    kb = [
        [InlineKeyboardButton(text="👤 Профиль", callback_data="menu_profile"), InlineKeyboardButton(text="🗳 Голосования", callback_data="menu_vote")],
        [InlineKeyboardButton(text="🎭 Партии", callback_data="menu_parties"), InlineKeyboardButton(text="📜 Документы", callback_data="menu_docs")],
        [InlineKeyboardButton(text="📰 Газета", callback_data="menu_news"), InlineKeyboardButton(text="⚙️ Настройки", callback_data="menu_settings")],
        [InlineKeyboardButton(text="❓ Помощь", callback_data="menu_help")],
    ]
    # Кнопка Госдумы (только депутатам или админу)
    if role == "deputy" or user_id == ADMIN_ID:
        kb.append([InlineKeyboardButton(text="🏛 Панель Госдумы", callback_data="menu_duma")])
    # Кнопка Президента (только президенту или админу)
    if role == "president" or user_id == ADMIN_ID:
        kb.append([InlineKeyboardButton(text="👑 Панель Президента", callback_data="menu_president")])
    # Кнопка Админа
    if user_id == ADMIN_ID:
        txt = "🛠 Админка [🔓]" if admin_active else "🛠 Админка [🔒]"
        kb.append([InlineKeyboardButton(text=txt, callback_data="menu_admin")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def build_profile_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Изменить ФИО", callback_data="profile_edit_fio")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="menu_main")],
    ])

def build_settings_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Изменить ФИО", callback_data="profile_edit_fio")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="menu_main")],
    ])

def build_president_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Создать указ", callback_data="pres_decree")],
        [InlineKeyboardButton(text="📜 Обращение к народу", callback_data="pres_address")],
        [InlineKeyboardButton(text="📋 Заявки мне", callback_data="pres_apps")],
        [InlineKeyboardButton(text="🗳 Назначить выборы в ГосДуму", callback_data="pres_duma_start")],
        [InlineKeyboardButton(text="👑 Назначить министров", callback_data="pres_ministers_manage")],
        [InlineKeyboardButton(text="⚖️ Список правительства", callback_data="pres_ministers_list")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="menu_main")],
    ])

def build_duma_panel_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📜 Внести законопроект", callback_data="duma_panel_law")],
        [InlineKeyboardButton(text="🏛 Созвать собрание", callback_data="duma_panel_session")],
        [InlineKeyboardButton(text="📋 Список законопроектов", callback_data="duma_panel_laws_list")],
        [InlineKeyboardButton(text="🗳 Назначить выборы Президента", callback_data="duma_panel_pres_elections")],
        [InlineKeyboardButton(text="👥 Список депутатов", callback_data="duma_panel_deputies")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="menu_main")],
    ])

def build_admin_keyboard(active=False):
    btn = "🔓 Активировать" if not active else "🔒 Деактивировать"
    kb = [
        [InlineKeyboardButton(text=btn, callback_data="admin_toggle")],
    ]
    if active:
        kb.extend([
            [InlineKeyboardButton(text="👥 Субъекты", callback_data="admin_subjects"), InlineKeyboardButton(text="🎭 Партии", callback_data="admin_parties")],
            [InlineKeyboardButton(text="📋 Заявки", callback_data="admin_apps"), InlineKeyboardButton(text="📜 Законы", callback_data="admin_laws")],
            [InlineKeyboardButton(text="📢 Указы", callback_data="admin_decrees"), InlineKeyboardButton(text="📰 Новости", callback_data="admin_news")],
            [InlineKeyboardButton(text="📢 Опубликовать всем", callback_data="admin_broadcast")],
            [InlineKeyboardButton(text="🗳 ГосДума", callback_data="admin_duma"), InlineKeyboardButton(text="👑 Снять Президента", callback_data="admin_pres_finish_now")],
            [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_status"), InlineKeyboardButton(text="🔄 Сброс", callback_data="admin_reset_confirm")],
        ])
    kb.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu_main")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def build_admin_subjects_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Список", callback_data="admin_subjects_list")],
        [InlineKeyboardButton(text="➕ Выдать должность", callback_data="admin_assign_role_subj")],
        [InlineKeyboardButton(text="➖ Снять должность", callback_data="admin_remove_role_subj")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="menu_admin")],
    ])

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
    if not roles: buttons.append([InlineKeyboardButton(text="(нет)", callback_data="noop")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_subjects")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def build_admin_parties_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Список", callback_data="admin_parties_list")],
        [InlineKeyboardButton(text="🗑 Распустить", callback_data="admin_dissolve_party")],
        [InlineKeyboardButton(text="👑 Сменить лидера", callback_data="admin_change_leader")],
        [InlineKeyboardButton(text="🏆 Кладбище", callback_data="admin_party_graveyard")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="menu_admin")],
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

def build_admin_confirm_reset_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚠️ ДА", callback_data="admin_reset_yes")],
        [InlineKeyboardButton(text="◀️ Отмена", callback_data="menu_admin")],
    ])

# ===== ОБРАБОТЧИКИ КОМАНД =====
@dp.message(Command("start", "menu"), StateFilter(None))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    user = message.from_user
    username = normalize_username(user.username)
    subject = await get_subject(user.id, username)
    if not subject:
        await message.answer("🏛 Введите кодовое слово «Бог Эфиопии» для начала регистрации:")
        return
    if subject["user_id"] != user.id and user.id:
        await update_subject_user_id(subject["username"], user.id)
    
    roles = await get_subject_roles(subject["id"])
    main_role = "subject"
    for r in roles:
        if r["code"] in ["president", "premier", "deputy"]:
            main_role = r["code"]
    
    admin_active = await is_admin_active(user.id)
    text = f"🏛 ДКДУСЛУГИ\n\n👤 {subject['full_name']}\n🎖 Роль: {', '.join([r['name'] for r in roles]) or 'Субъект'}\n⭐ Репутация: {subject['reputation']}\n\nВыбери раздел:"
    await message.answer(text, reply_markup=build_main_menu(user.id, main_role, admin_active))

@dp.message(StateFilter(None), lambda m: m.text and not m.text.startswith("/") and m.video is None)
async def handle_text(message: types.Message, state: FSMContext):
    if check_secret_word(message.text):
        if await get_subject(message.from_user.id, message.from_user.username):
            await message.answer("Вы уже авторизованы.")
            return
        await message.answer("Кодовое слово принято! Введите ваше ФИО:")
        await state.set_state(ProfileForm.waiting_fio)
        return
    await message.answer("Используйте кнопки меню.")

@dp.message(ProfileForm.waiting_fio)
async def process_register_fio(message: types.Message, state: FSMContext):
    fio = message.text.strip()
    if len(fio) < 3:
        await message.answer("ФИО слишком короткое. Введите заново:")
        return
    async with db_pool.acquire() as conn:
        await conn.execute("INSERT INTO subjects (user_id, username, full_name, is_citizen) VALUES ($1, $2, $3, FALSE) ON CONFLICT (username) DO UPDATE SET full_name = $3, user_id = $1", message.from_user.id, normalize_username(message.from_user.username), fio)
    # Ищем президента
    async with db_pool.acquire() as conn:
        president = await conn.fetchrow("SELECT s.username FROM subjects s JOIN subject_roles sr ON sr.subject_id = s.id JOIN roles r ON r.id = sr.role_id WHERE r.code = 'president' LIMIT 1")
    target = president["username"] if president else None
    await create_application("citizenship", message.from_user.username, fio, target, {"user_id": message.from_user.id})
    await state.clear()
    await message.answer("✅ Заявка на гражданство отправлена Президенту. Ожидайте.")

@dp.callback_query(lambda c: c.data == "menu_main")
async def back_to_main(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    user = callback.from_user
    username = normalize_username(user.username)
    subject = await get_subject(user.id, username)
    if not subject: return
    roles = await get_subject_roles(subject["id"])
    main_role = "subject"
    for r in roles:
        if r["code"] in ["president", "premier", "deputy"]: main_role = r["code"]
    admin_active = await is_admin_active(user.id)
    text = f"🏛 ДКДУСЛУГИ\n\n👤 {subject['full_name']}\n🎖 Роль: {', '.join([r['name'] for r in roles]) or 'Субъект'}\n⭐ Репутация: {subject['reputation']}\n\nВыбери раздел:"
    try:
        await callback.message.edit_text(text, reply_markup=build_main_menu(user.id, main_role, admin_active))
    except Exception:
        await callback.message.answer(text, reply_markup=build_main_menu(user.id, main_role, admin_active))
    await callback.answer()

@dp.callback_query(lambda c: c.data == "menu_profile")
async def menu_profile(callback: types.CallbackQuery):
    try:
        user = callback.from_user
        subject = await get_subject(user.id, normalize_username(user.username))
        if not subject: return
        roles = await get_subject_roles(subject["id"])
        user_party = await get_user_party(subject["username"])
        admin_mode = await is_admin_active(user.id)
        text = build_subject_profile(subject, roles, user_party, admin_mode)
        await callback.message.edit_text(text, reply_markup=build_profile_keyboard())
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        await callback.answer("Ошибка", show_alert=True)

@dp.callback_query(lambda c: c.data == "menu_settings")
async def menu_settings(callback: types.CallbackQuery):
    await callback.message.edit_text("⚙️ НАСТРОЙКИ\n\nЗдесь можно изменить свои данные.", reply_markup=build_settings_keyboard())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "profile_edit_fio")
async def profile_edit_fio_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("✍️ Введи новое ФИО (минимум 3 символа).")
    await state.set_state(ProfileForm.waiting_fio)
    await callback.answer()

@dp.message(ProfileForm.waiting_fio)
async def profile_edit_fio_save(message: types.Message, state: FSMContext):
    new_fio = message.text.strip() if message.text else ""
    if len(new_fio) < 3:
        await message.answer("❌ Слишком короткое.")
        return
    user = message.from_user
    subject = await get_subject(user.id, normalize_username(user.username))
    if not subject:
        await message.answer("❌ Ты не зарегистрирован.")
        await state.clear()
        return
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE subjects SET full_name = $1 WHERE id = $2", new_fio, subject["id"])
    await message.answer(f"✅ ФИО изменено: {new_fio}")
    await state.clear()

@dp.callback_query(lambda c: c.data == "menu_news")
async def menu_news(callback: types.CallbackQuery):
    try:
        news = await get_news(10)
        text = "📰 ЗЕ ТУНИЯНЦЫ НЬЮС\n\n"
        if not news: text += "Новостей пока нет."
        else:
            for n in news:
                dt = n["created_at"].strftime("%d.%m %H:%M")
                text += f"[{dt}] {n['text']}\n\n"
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔄 Обновить", callback_data="menu_news"), InlineKeyboardButton(text="◀️ Назад", callback_data="menu_main")]]))
        await callback.answer()
    except Exception as e:
        await callback.answer("Ошибка", show_alert=True)

@dp.callback_query(lambda c: c.data == "menu_help")
async def menu_help(callback: types.CallbackQuery):
    text = "❓ ПОМОЩЬ\n\nБот симулирует государство ДКД.\n\n/start — меню\n/me — профиль\n/parties — партии\n/news — газета\n\nПолномочия зависят от роли."
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="menu_main")]]))
    await callback.answer()

@dp.callback_query(lambda c: c.data == "menu_docs")
async def menu_docs(callback: types.CallbackQuery):
    text = "📜 ДОКУМЕНТЫ\n\nРаздел в разработке. Скоро здесь появятся ваши личные документы."
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="menu_main")]]))
    await callback.answer()

@dp.callback_query(lambda c: c.data == "menu_duma")
async def menu_duma(callback: types.CallbackQuery):
    try:
        username = normalize_username(callback.from_user.username)
        if not await has_role_by_username(username, "deputy") and callback.from_user.id != ADMIN_ID:
            await callback.answer("Вы не депутат ГосДумы.", show_alert=True)
            return
        await callback.message.edit_text("🏛 ПАНЕЛЬ ГОСДУМЫ\n\nВыбери действие:", reply_markup=build_duma_panel_keyboard())
        await callback.answer()
    except Exception as e:
        await callback.answer("Ошибка", show_alert=True)

@dp.callback_query(lambda c: c.data == "menu_president")
async def menu_president(callback: types.CallbackQuery):
    try:
        username = normalize_username(callback.from_user.username)
        if not await can_use_pres_panel(callback.from_user.id, username):
            await callback.answer("Вы не Президент.", show_alert=True)
            return
        await callback.message.edit_text("👑 ПАНЕЛЬ ПРЕЗИДЕНТА\n\nВыбери действие:", reply_markup=build_president_keyboard())
        await callback.answer()
    except Exception as e:
        await callback.answer("Ошибка", show_alert=True)

@dp.callback_query(lambda c: c.data == "menu_admin")
async def menu_admin(callback: types.CallbackQuery):
    try:
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("Только админ.", show_alert=True)
            return
        active = await is_admin_active(callback.from_user.id)
        status = "🔓 АКТИВЕН" if active else "🔒 НЕ АКТИВЕН"
        await callback.message.edit_text(f"🛠 АДМИН-ПАНЕЛЬ\n\nСтатус: {status}\n\nВыбери действие:", reply_markup=build_admin_keyboard(active))
        await callback.answer()
    except Exception as e:
        await callback.answer("Ошибка", show_alert=True)
        # ===== ПАРТИИ =====
@dp.callback_query(lambda c: c.data == "menu_parties")
async def menu_parties(callback: types.CallbackQuery):
    try:
        parties = await get_all_parties()
        text = "🎭 ПАРТИИ\n\n"
        if not parties: text += "Пока нет."
        buttons = []
        for p in parties:
            members = await get_party_members(p["id"])
            text += f"{p['emoji']} {p['name']} — {len(members)} чел.\n"
            buttons.append([InlineKeyboardButton(text=f"{p['emoji']} {p['name']}", callback_data=f"party_view|{p['id']}")])
        buttons.append([InlineKeyboardButton(text="➕ Создать партию", callback_data="party_create")])
        buttons.append([InlineKeyboardButton(text="🏆 Кладбище партий", callback_data="party_graveyard")])
        buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu_main")])
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        await callback.answer()
    except Exception as e:
        await callback.answer("Ошибка", show_alert=True)

@dp.callback_query(lambda c: c.data.startswith("party_view|"))
async def party_view(callback: types.CallbackQuery):
    try:
        pid = int(callback.data.split("|")[1])
        party = await get_party(pid)
        if not party: return
        members = await get_party_members(pid)
        text = f"━━━━━━━━━━━━━━━━━━━━━\n{party['emoji']} {party['name'].upper()}\n━━━━━━━━━━━━━━━━━━━━━\n\n{party['description']}\n\nЛидер: {party['leader_username']}\nСостав ({len(members)}):\n"
        for m in members: text += f"  • {m['username']}\n"
        
        buttons = []
        username = normalize_username(callback.from_user.username)
        user_party = await get_user_party(username)
        
        if user_party and user_party["id"] == pid:
            buttons.append([InlineKeyboardButton(text="🚪 Выйти", callback_data=f"party_leave|{pid}")])
        elif not user_party:
            buttons.append([InlineKeyboardButton(text="✍️ Вступить", callback_data=f"party_join|{pid}")])
            
        # Если лидер и есть выборы - кнопка списка
        if party["leader_username"] == username:
            active_el = await get_active_duma_election()
            if active_el:
                buttons.append([InlineKeyboardButton(text="📝 Сформировать список в Думу", callback_data=f"party_list_form|{pid}|{active_el['id']}")])
        
        buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu_parties")])
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        await callback.answer()
    except Exception as e:
        await callback.answer("Ошибка", show_alert=True)

@dp.callback_query(lambda c: c.data.startswith("party_join|"))
async def party_join(callback: types.CallbackQuery):
    try:
        pid = int(callback.data.split("|")[1])
        party = await get_party(pid)
        username = normalize_username(callback.from_user.username)
        subject = await get_subject(callback.from_user.id, username)
        await create_application("join_party", username, subject["full_name"], party["leader_username"], {"party_id": pid, "party_name": party["name"]})
        await callback.message.answer(f"✍️ Заявка отправлена лидеру {party['leader_username']}.")
        await callback.answer()
    except Exception as e:
        await callback.answer("Ошибка", show_alert=True)

@dp.callback_query(lambda c: c.data.startswith("party_leave|"))
async def party_leave(callback: types.CallbackQuery):
    try:
        username = normalize_username(callback.from_user.username)
        await remove_party_member(username)
        await callback.message.edit_text("🚪 Ты покинул партию.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ В меню", callback_data="menu_main")]]))
        await callback.answer()
    except Exception as e:
        await callback.answer("Ошибка", show_alert=True)

@dp.callback_query(lambda c: c.data == "party_graveyard")
async def party_graveyard(callback: types.CallbackQuery):
    try:
        async with db_pool.acquire() as conn:
            dead = await conn.fetch("SELECT * FROM parties WHERE status = 'dissolved'")
        text = "🏆 КЛАДБИЩЕ ПАРТИЙ\n\n"
        for p in dead: text += f"💀 {p['emoji']} {p['name']} (RIP)\n"
        if not dead: text += "Пусто."
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="menu_parties")]]))
        await callback.answer()
    except Exception as e:
        await callback.answer("Ошибка", show_alert=True)

@dp.callback_query(lambda c: c.data == "party_create")
async def party_create(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("➕ СОЗДАНИЕ ПАРТИИ\n\nШаг 1/3. Отправь НАЗВАНИЕ (2-50 символов).")
    await state.set_state(PartyForm.waiting_name)
    await callback.answer()

@dp.message(PartyForm.waiting_name)
async def party_name(message: types.Message, state: FSMContext):
    name = message.text.strip() if message.text else ""
    if len(name) < 2 or len(name) > 50:
        await message.answer("Название 2-50 символов.")
        return
    if await get_party_by_name(name):
        await message.answer("Такое название уже есть.")
        return
    await state.update_data(party_name=name)
    await message.answer(f"Название: {name}\n\nШаг 2/3. Отправь ЭМОДЗИ.")
    await state.set_state(PartyForm.waiting_emoji)

@dp.message(PartyForm.waiting_emoji)
async def party_emoji(message: types.Message, state: FSMContext):
    emoji = message.text.strip() if message.text else "🎭"
    if len(emoji) > 5:
        await message.answer("Один эмодзи.")
        return
    await state.update_data(party_emoji=emoji)
    await message.answer(f"Эмодзи: {emoji}\n\nШаг 3/3. Отправь ПРОГРАММУ.")
    await state.set_state(PartyForm.waiting_description)

@dp.message(PartyForm.waiting_description)
async def party_description(message: types.Message, state: FSMContext):
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
    await message.answer(f"✅ Заявка на партию «{name}» отправлена Президенту.")
    await state.clear()

# ===== ПАРТИЙНЫЕ СПИСКИ =====
@dp.callback_query(lambda c: c.data.startswith("party_list_form|"))
async def party_list_form(callback: types.CallbackQuery, state: FSMContext):
    try:
        _, pid, eid = callback.data.split("|")
        pid, eid = int(pid), int(eid)
        async with db_pool.acquire() as conn:
            exists = await conn.fetch("SELECT username FROM party_lists WHERE party_id = $1 AND election_id = $2", pid, eid)
        if exists:
            await callback.answer("Список уже сформирован!", show_alert=True)
            return
        
        members = await get_party_members(pid)
        buttons = []
        for m in members:
            buttons.append([InlineKeyboardButton(text=m['username'], callback_data=f"add_to_list|{pid}|{eid}|{m['username']}")])
        buttons.append([InlineKeyboardButton(text="✅ Готово", callback_data=f"list_done|{pid}|{eid}")])
        
        await state.update_data(pl_pid=pid, pl_eid=eid, pl_selected=[])
        await callback.message.answer(f"📝 ФОРМИРОВАНИЕ СПИСКА\n\nВыбери до 3 человек из своей партии (нажимай на имена):", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        await callback.answer()
    except Exception as e:
        await callback.answer("Ошибка", show_alert=True)

@dp.callback_query(lambda c: c.data.startswith("add_to_list|"))
async def add_to_list(callback: types.CallbackQuery, state: FSMContext):
    try:
        _, pid, eid, uname = callback.data.split("|")
        data = await state.get_data()
        selected = data.get("pl_selected", [])
        if uname in selected:
            await callback.answer("Уже выбран", show_alert=True)
            return
        if len(selected) >= 3:
            await callback.answer("Максимум 3 человека", show_alert=True)
            return
        
        selected.append(uname)
        await state.update_data(pl_selected=selected)
        
        # Обновляем кнопки (убираем выбранного)
        members = await get_party_members(int(pid))
        buttons = []
        for m in members:
            if m['username'] not in selected:
                buttons.append([InlineKeyboardButton(text=m['username'], callback_data=f"add_to_list|{pid}|{eid}|{m['username']}")])
        buttons.append([InlineKeyboardButton(text=f"✅ Готово ({len(selected)}/3)", callback_data=f"list_done|{pid}|{eid}")])
        
        await callback.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        await callback.answer(f"Добавлен: {uname}")
    except Exception as e:
        await callback.answer("Ошибка", show_alert=True)

@dp.callback_query(lambda c: c.data.startswith("list_done|"))
async def list_done(callback: types.CallbackQuery, state: FSMContext):
    try:
        _, pid, eid = callback.data.split("|")
        pid, eid = int(pid), int(eid)
        data = await state.get_data()
        selected = data.get("pl_selected", [])
        
        if not selected:
            await callback.answer("Выбери хотя бы одного", show_alert=True)
            return
        
        async with db_pool.acquire() as conn:
            for u in selected:
                await conn.execute("INSERT INTO party_lists (party_id, election_id, username) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING", pid, eid, u)
        
        party = await get_party(pid)
        await callback.message.edit_text(f"✅ Список партии «{party['name']}» сформирован!\n\nКандидаты:\n" + "\n".join([f"• {u}" for u in selected]), reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ В меню", callback_data="menu_main")]]))
        await state.clear()
        await callback.answer()
    except Exception as e:
        await callback.answer("Ошибка", show_alert=True)

# ===== ВЫБОРЫ (ГОЛОСОВАНИЕ) =====
@dp.callback_query(lambda c: c.data == "menu_vote")
async def menu_vote(callback: types.CallbackQuery):
    try:
        buttons = []
        # Выборы Президента
        pres_el = await get_active_pres_election()
        if pres_el:
            buttons.append([InlineKeyboardButton(text="🗳 Выборы Президента", callback_data="vote_pres")])
        # Выборы в Думу
        duma_el = await get_active_duma_election()
        if duma_el:
            buttons.append([InlineKeyboardButton(text="🗳 Выборы в ГосДуму", callback_data="vote_duma")])
            
        buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu_main")])
        text = "🗳 ГОЛОСОВАНИЯ\n\nВыбери активное голосование:"
        if len(buttons) == 1: text = "🗳 ГОЛОСОВАНИЯ\n\nСейчас нет активных голосований."
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        await callback.answer()
    except Exception as e:
        await callback.answer("Ошибка", show_alert=True)

@dp.callback_query(lambda c: c.data == "vote_pres")
async def vote_pres_menu(callback: types.CallbackQuery):
    try:
        if await user_has_voted(callback.from_user.id):
            await callback.answer("Вы уже голосовали!", show_alert=True)
            return
        
        buttons = []
        for cid, c in CANDIDATES.items():
            buttons.append([InlineKeyboardButton(text=f"{cid}. {c['name']}", callback_data=f"sub_vp_{cid}")])
        buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu_vote")])
        await callback.message.edit_text("🗳 БЮЛЛЕТЕНЬ (Президент)\n\nВыбери кандидата:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        await callback.answer()
    except Exception as e:
        await callback.answer("Ошибка", show_alert=True)

@dp.callback_query(lambda c: c.data.startswith("sub_vp_"))
async def sub_vp(callback: types.CallbackQuery):
    try:
        cid = callback.data.split("_")[2]
        username = normalize_username(callback.from_user.username)
        voter_name = VOTERS.get(username, {}).get("name", "Субъект")
        
        await save_vote(callback.from_user.id, username, voter_name, cid)
        c_name = CANDIDATES[cid]["name"]
        
        caption = f"━━━━━━━━━━━━━━━━━━━━━\n✅ ГОЛОС ПРИНЯТ!\n━━━━━━━━━━━━━━━━━━━━━\n\n👤 {voter_name}\n🗳 {c_name}"
        try:
            await callback.message.answer_video(video=VIDEO_FILE_ID, caption=caption)
        except Exception:
            await callback.message.answer(caption)
            
        await callback.message.edit_text("Голос учтен.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ В меню", callback_data="menu_main")]]))
        await callback.answer()
    except Exception as e:
        await callback.answer("Ошибка", show_alert=True)

@dp.callback_query(lambda c: c.data == "vote_duma")
async def vote_duma_menu(callback: types.CallbackQuery):
    try:
        username = normalize_username(callback.from_user.username)
        if await has_role_by_username(username, "party_leader"):
            await callback.answer("Лидеры партий не голосуют на выборах в Думу!", show_alert=True)
            return
            
        el = await get_active_duma_election()
        if not el: return
        
        async with db_pool.acquire() as conn:
            voted = await conn.fetchrow("SELECT id FROM duma_votes WHERE election_id = $1 AND voter_username = $2", el['id'], username)
        if voted:
            await callback.answer("Вы уже голосовали!", show_alert=True)
            return
            
        # Показываем только партии со списками
        parties = await get_all_parties()
        buttons = []
        for p in parties:
            async with db_pool.acquire() as conn:
                has_list = await conn.fetchval("SELECT COUNT(*) FROM party_lists WHERE party_id = $1 AND election_id = $2", p['id'], el['id'])
            if has_list > 0:
                buttons.append([InlineKeyboardButton(text=f"{p['emoji']} {p['name']}", callback_data=f"sub_vd_{el['id']}_{p['id']}")])
        
        if not buttons:
            await callback.message.answer("Нет партий со списками.")
            return
            
        buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu_vote")])
        await callback.message.edit_text("🗳 БЮЛЛЕТЕНЬ (ГосДума)\n\nВыбери партию:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        await callback.answer()
    except Exception as e:
        await callback.answer("Ошибка", show_alert=True)

@dp.callback_query(lambda c: c.data.startswith("sub_vd_"))
async def sub_vd(callback: types.CallbackQuery):
    try:
        _, _, eid, pid = callback.data.split("_")
        eid, pid = int(eid), int(pid)
        username = normalize_username(callback.from_user.username)
        subject = await get_subject(callback.from_user.id, username)
        
        await vote_duma(eid, username, pid)
        p = await get_party(pid)
        
        caption = f"━━━━━━━━━━━━━━━━━━━━━\n✅ ГОЛОС ПРИНЯТ!\n━━━━━━━━━━━━━━━━━━━━━\n\n👤 {subject['full_name']}\n🗳 {p['emoji']} {p['name']}"
        try:
            await callback.message.answer_video(video=VIDEO_FILE_ID, caption=caption)
        except Exception:
            await callback.message.answer(caption)
            
        await callback.message.edit_text("Голос учтен.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ В меню", callback_data="menu_main")]]))
        await callback.answer()
    except Exception as e:
        await callback.answer("Ошибка", show_alert=True)

# ===== ПАНЕЛЬ ПРЕЗИДЕНТА (ФУНКЦИИ) =====
@dp.callback_query(lambda c: c.data == "pres_apps")
async def pres_apps(callback: types.CallbackQuery):
    try:
        username = normalize_username(callback.from_user.username)
        apps = await get_pending_applications(username)
        if not apps:
            await callback.message.edit_text("📋 Заявок нет.", reply_markup=build_president_keyboard())
            await callback.answer()
            return
        buttons = []
        text = "📋 ЗАЯВКИ ПРЕЗИДЕНТУ\n\n"
        for a in apps:
            text += f"#{a['id']} — {a['type']} от {a['author_username']}\n"
            buttons.append([InlineKeyboardButton(text=f"#{a['id']} открыть", callback_data=f"pres_app_view|{a['id']}")])
        buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu_main")])
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        await callback.answer()
    except Exception as e:
        await callback.answer("Ошибка", show_alert=True)

@dp.callback_query(lambda c: c.data.startswith("pres_app_view|"))
async def pres_app_view(callback: types.CallbackQuery):
    try:
        aid = int(callback.data.split("|")[1])
        app = await get_application(aid)
        data = app["data"]
        if isinstance(data, str): data = json.loads(data)
        
        text = f"📋 ЗАЯВКА #{aid}\n\nТип: {app['type']}\nАвтор: {app['author_username']}\n"
        if data: text += f"Данные: {json.dumps(data, ensure_ascii=False)}\n"
        buttons = [
            [InlineKeyboardButton(text="✅ Одобрить", callback_data=f"pres_app_approve|{aid}")],
            [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"pres_app_reject|{aid}")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="pres_apps")],
        ]
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        await callback.answer()
    except Exception as e:
        await callback.answer("Ошибка", show_alert=True)

@dp.callback_query(lambda c: c.data.startswith("pres_app_approve|"))
async def pres_app_approve(callback: types.CallbackQuery):
    try:
        aid = int(callback.data.split("|")[1])
        app = await get_application(aid)
        data = app["data"]
        if isinstance(data, str): data = json.loads(data)
        
        if app["type"] == "citizenship":
            await approve_application(aid, callback.from_user.id)
            async with db_pool.acquire() as conn:
                await conn.execute("UPDATE subjects SET is_citizen = TRUE WHERE username = $1", app["author_username"])
        elif app["type"] == "create_party":
            await create_party(data.get("name"), data.get("emoji"), data.get("description"), app["author_username"])
            await approve_application(aid, callback.from_user.id)
        elif app["type"] == "join_party":
            await add_party_member(data.get("party_id"), app["author_username"])
            await approve_application(aid, callback.from_user.id)
        
        await callback.message.edit_text(f"✅ Заявка #{aid} одобрена.", reply_markup=build_president_keyboard())
        await callback.answer()
    except Exception as e:
        await callback.answer("Ошибка", show_alert=True)

@dp.callback_query(lambda c: c.data.startswith("pres_app_reject|"))
async def pres_app_reject(callback: types.CallbackQuery):
    try:
        aid = int(callback.data.split("|")[1])
        await reject_application(aid, callback.from_user.id, "Отклонено Президентом")
        await callback.message.edit_text(f"❌ Заявка #{aid} отклонена.", reply_markup=build_president_keyboard())
        await callback.answer()
    except Exception as e:
        await callback.answer("Ошибка", show_alert=True)

@dp.callback_query(lambda c: c.data == "pres_duma_start")
async def pres_duma_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("🗳 НАЗНАЧЕНИЕ ВЫБОРОВ В ГОСДУМУ\n\nОтправь ДАТУ ОКОНЧАНИЯ (например 2027-01-15 20:00):")
    await state.set_state(ElectionForm.waiting_date_end)
    await callback.answer()

@dp.message(ElectionForm.waiting_date_end)
async def duma_date_end(message: types.Message, state: FSMContext):
    dt = parse_date_flexible(message.text)
    if not dt or dt <= now_msk():
        await message.answer("❌ Неверный формат или дата в прошлом.")
        return
    await start_duma_election(dt)
    await message.answer(f"✅ Выборы назначены! До {dt.strftime('%d.%m.%Y %H:%M')} МСК")
    await state.clear()

# ===== ПАНЕЛЬ ПРЕЗИДЕНТА (МИНИСТРЫ) =====
@dp.callback_query(lambda c: c.data == "pres_ministers_list")
async def pres_ministers_list(callback: types.CallbackQuery):
    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT s.full_name, r.name as role_name, r.emoji
                FROM subjects s JOIN subject_roles sr ON sr.subject_id = s.id
                JOIN roles r ON r.id = sr.role_id
                WHERE r.code IN ('minister', 'premier', 'cbank', 'advisor')
            """)
        text = "⚖️ ПРАВИТЕЛЬСТВО\n\n"
        if not rows: text += "Пока никого."
        for r in rows: text += f"{r['emoji']} {r['role_name']}: {r['full_name']}\n"
        await callback.message.edit_text(text, reply_markup=build_president_keyboard())
        await callback.answer()
    except Exception as e:
        await callback.answer("Ошибка", show_alert=True)

@dp.callback_query(lambda c: c.data == "pres_ministers_manage")
async def pres_ministers_manage(callback: types.CallbackQuery):
    try:
        subjects = await get_all_subjects()
        buttons = []
        for s in subjects:
            buttons.append([InlineKeyboardButton(text=s['full_name'], callback_data=f"pres_ministers_pick|{s['id']}")])
        buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu_main")])
        await callback.message.edit_text("👑 НАЗНАЧЕНИЕ МИНИСТРОВ\n\nШаг 1/2. Выбери субъекта:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        await callback.answer()
    except Exception as e:
        await callback.answer("Ошибка", show_alert=True)

@dp.callback_query(lambda c: c.data.startswith("pres_ministers_pick|"))
async def pres_ministers_pick(callback: types.CallbackQuery):
    try:
        sid = int(callback.data.split("|")[1])
        roles = await get_all_roles()
        buttons = []
        for r in roles:
            if r["code"] in ["president", "deputy", "subject", "party_leader"]: continue
            buttons.append([InlineKeyboardButton(text=f"{r['emoji']} {r['name']}", callback_data=f"pres_ministers_set|{sid}|{r['id']}")])
        buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="pres_ministers_manage")])
        await callback.message.edit_text("👑 Шаг 2/2. Выбери ДОЛЖНОСТЬ:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        await callback.answer()
    except Exception as e:
        await callback.answer("Ошибка", show_alert=True)

@dp.callback_query(lambda c: c.data.startswith("pres_ministers_set|"))
async def pres_ministers_set(callback: types.CallbackQuery):
    try:
        _, sid, rid = callback.data.split("|")
        ok, msg = await assign_role(int(sid), int(rid), callback.from_user.id)
        if ok:
            await callback.message.edit_text("✅ Назначено.", reply_markup=build_president_keyboard())
        else:
            await callback.message.answer(f"❌ {msg}")
        await callback.answer()
    except Exception as e:
        await callback.answer("Ошибка", show_alert=True)

# ===== УКАЗЫ И ОБРАЩЕНИЯ =====
@dp.callback_query(lambda c: c.data == "pres_decree")
async def pres_decree(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("📢 СОЗДАНИЕ УКАЗА\n\nШаг 1/3. Отправь ЗАГОЛОВОК.")
    await state.set_state(DecreeForm.waiting_title)
    await callback.answer()

@dp.message(DecreeForm.waiting_title)
async def decree_title(message: types.Message, state: FSMContext):
    await state.update_data(decree_title=message.text)
    await message.answer("Шаг 2/3. Отправь ТЕКСТ указа.")
    await state.set_state(DecreeForm.waiting_text)

@dp.message(DecreeForm.waiting_text)
async def decree_text(message: types.Message, state: FSMContext):
    await state.update_data(decree_text=message.text)
    await message.answer("Шаг 3/3. Секретный? Отправь @username или «нет».")
    await state.set_state(DecreeForm.waiting_secret)

@dp.message(DecreeForm.waiting_secret)
async def decree_secret(message: types.Message, state: FSMContext):
    ans = message.text.lower()
    data = await state.get_data()
    is_sec = ans != "нет" and ans.startswith("@")
    sec_for = normalize_username(ans) if is_sec else None
    username = normalize_username(message.from_user.username)
    
    await create_decree(data["decree_title"], data["decree_text"], username, is_sec, sec_for)
    
    if is_sec:
        subj = await get_subject_by_username(sec_for)
        if subj and subj["user_id"]:
            try:
                await message.bot.send_message(subj["user_id"], f"🔒 СЕКРЕТНЫЙ УКАЗ\n\n{data['decree_title']}\n\n{data['decree_text']}")
            except Exception: pass
        await message.answer("✅ Секретный указ создан (никто не узнает).")
    else:
        await add_news(f"📢 Указ: «{data['decree_title']}»")
        subjects = await get_all_subjects()
        for s in subjects:
            if s["user_id"]:
                try: await message.bot.send_message(s["user_id"], f"📢 УКАЗ ПРЕЗИДЕНТА\n\n{data['decree_title']}\n\n{data['decree_text']}")
                except Exception: pass
        await message.answer("✅ Указ разослан всем.")
    await state.clear()

@dp.callback_query(lambda c: c.data == "pres_address")
async def pres_address(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("📜 Отправь текст ОБРАЩЕНИЯ К НАРОДУ.")
    await state.set_state(PresidentAddressForm.waiting_text)
    await callback.answer()

@dp.message(PresidentAddressForm.waiting_text)
async def president_address_send(message: types.Message, state: FSMContext):
    text = message.text.strip()
    await add_news(f"📜 ОБРАЩЕНИЕ ПРЕЗИДЕНТА:\n\n{text}")
    subjects = await get_all_subjects()
    sent = 0
    for s in subjects:
        if s["user_id"]:
            try:
                await message.bot.send_message(s["user_id"], f"📜 ОБРАЩЕНИЕ ПРЕЗИДЕНТА\n\n{text}")
                sent += 1
            except Exception: pass
    await message.answer(f"✅ Обращение разослано! Доставлено: {sent}")
    await state.clear()

# ===== АДМИН-ПАНЕЛЬ ОБРАБОТЧИКИ =====
@dp.callback_query(lambda c: c.data == "admin_toggle")
async def admin_toggle(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID: return
    active = await is_admin_active(callback.from_user.id)
    if active: await deactivate_admin(callback.from_user.id)
    else: await activate_admin(callback.from_user.id)
    active = await is_admin_active(callback.from_user.id)
    await callback.message.edit_text(f"🛠 АДМИН-ПАНЕЛЬ\nСтатус: {'🔓' if active else '🔒'}", reply_markup=build_admin_keyboard(active))
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_subjects")
async def admin_subjects(callback: types.CallbackQuery):
    if not await is_admin_active(callback.from_user.id): return
    await callback.message.edit_text("👥 СУБЪЕКТЫ", reply_markup=build_admin_subjects_keyboard())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_subjects_list")
async def admin_subjects_list(callback: types.CallbackQuery):
    if not await is_admin_active(callback.from_user.id): return
    kb = await build_admin_subjects_list_keyboard()
    await callback.message.edit_text("👥 ВЫБЕРИ СУБЪЕКТА", reply_markup=kb)
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("admin_subj_view|"))
async def admin_subj_view(callback: types.CallbackQuery):
    if not await is_admin_active(callback.from_user.id): return
    sid = int(callback.data.split("|")[1])
    async with db_pool.acquire() as conn:
        s = await conn.fetchrow("SELECT * FROM subjects WHERE id = $1", sid)
    roles = await get_subject_roles(sid)
    await callback.message.answer(build_subject_profile(s, roles, None, False))
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_assign_role_subj")
async def admin_assign_role_subj(callback: types.CallbackQuery):
    if not await is_admin_active(callback.from_user.id): return
    kb = await build_admin_assign_role_subj_keyboard()
    await callback.message.edit_text("➕ ВЫДАТЬ ДОЛЖНОСТЬ", reply_markup=kb)
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("admin_assign_subj|"))
async def admin_assign_subj(callback: types.CallbackQuery):
    if not await is_admin_active(callback.from_user.id): return
    sid = int(callback.data.split("|")[1])
    kb = await build_admin_assign_role_keyboard(sid)
    await callback.message.edit_text("➕ ВЫБЕРИ ДОЛЖНОСТЬ", reply_markup=kb)
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("admin_assign_role|"))
async def admin_assign_role(callback: types.CallbackQuery):
    if not await is_admin_active(callback.from_user.id): return
    _, sid, rid = callback.data.split("|")
    ok, msg = await assign_role(int(sid), int(rid), ADMIN_ID)
    if ok: await callback.message.edit_text("✅ Назначено.")
    else: await callback.message.answer(f"❌ {msg}")
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_apps")
async def admin_apps(callback: types.CallbackQuery):
    if not await is_admin_active(callback.from_user.id): return
    apps = await get_pending_applications()
    if not apps:
        await callback.message.edit_text("📋 Заявок нет.", reply_markup=build_admin_keyboard(True))
        await callback.answer()
        return
    text = "📋 ЗАЯВКИ\n\n"
    buttons = []
    for a in apps:
        text += f"#{a['id']} — {a['type']} от {a['author_username']}\n"
        buttons.append([InlineKeyboardButton(text=f"#{a['id']} открыть", callback_data=f"admin_app_view|{a['id']}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu_admin")])
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("admin_app_view|"))
async def admin_app_view(callback: types.CallbackQuery):
    if not await is_admin_active(callback.from_user.id): return
    aid = int(callback.data.split("|")[1])
    app = await get_application(aid)
    data = app["data"]
    if isinstance(data, str): data = json.loads(data)
    text = f"📋 ЗАЯВКА #{aid}\n\nТип: {app['type']}\nАвтор: {app['author_username']}\n"
    if data: text += f"Данные: {json.dumps(data, ensure_ascii=False)}\n"
    buttons = [
        [InlineKeyboardButton(text="✅ Одобрить", callback_data=f"admin_app_approve|{aid}")],
        [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin_app_reject|{aid}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_apps")],
    ]
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("admin_app_approve|"))
async def admin_app_approve(callback: types.CallbackQuery):
    if not await is_admin_active(callback.from_user.id): return
    aid = int(callback.data.split("|")[1])
    app = await get_application(aid)
    data = app["data"]
    if isinstance(data, str): data = json.loads(data)
    
    if app["type"] == "citizenship":
        await approve_application(aid, ADMIN_ID)
        async with db_pool.acquire() as conn:
            await conn.execute("UPDATE subjects SET is_citizen = TRUE WHERE username = $1", app["author_username"])
    elif app["type"] == "create_party":
        await create_party(data.get("name"), data.get("emoji"), data.get("description"), app["author_username"])
        await approve_application(aid, ADMIN_ID)
    elif app["type"] == "join_party":
        await add_party_member(data.get("party_id"), app["author_username"])
        await approve_application(aid, ADMIN_ID)
    
    await callback.message.edit_text(f"✅ Заявка #{aid} одобрена.")
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("admin_app_reject|"))
async def admin_app_reject(callback: types.CallbackQuery):
    if not await is_admin_active(callback.from_user.id): return
    aid = int(callback.data.split("|")[1])
    await reject_application(aid, ADMIN_ID, "Отклонено Админом")
    await callback.message.edit_text(f"❌ Заявка #{aid} отклонена.")
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_pres_finish_now")
async def admin_pres_finish_now(callback: types.CallbackQuery):
    if not await is_admin_active(callback.from_user.id): return
    await force_finish_president()
    await callback.message.answer("👑 Президент снят досрочно.")
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_duma")
async def admin_duma(callback: types.CallbackQuery):
    if not await is_admin_active(callback.from_user.id): return
    buttons = [
        [InlineKeyboardButton(text="🗳 Начать выборы", callback_data="admin_duma_start")],
        [InlineKeyboardButton(text="🛑 Завершить досрочно", callback_data="admin_duma_finish_now")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="menu_admin")],
    ]
    await callback.message.edit_text("🗳 ГОСДУМА", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_duma_start")
async def admin_duma_start(callback: types.CallbackQuery, state: FSMContext):
    if not await is_admin_active(callback.from_user.id): return
    await callback.message.answer("🗳 Отправь ДАТУ окончания (например 2027-01-15 20:00):")
    await state.set_state(ElectionForm.waiting_date_end)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_duma_finish_now")
async def admin_duma_finish_now(callback: types.CallbackQuery):
    if not await is_admin_active(callback.from_user.id): return
    await force_finish_duma_election()
    await callback.message.answer("🛑 Выборы в Думу завершены досрочно.")
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_broadcast")
async def admin_broadcast(callback: types.CallbackQuery, state: FSMContext):
    if not await is_admin_active(callback.from_user.id): return
    await callback.message.answer("📢 Отправь текст новости для рассылки ВСЕМ.")
    await state.set_state(BroadcastForm.waiting_text)
    await callback.answer()

@dp.message(BroadcastForm.waiting_text)
async def broadcast_send(message: types.Message, state: FSMContext):
    text = message.text.strip()
    await add_news(f"📢 {text}")
    subjects = await get_all_subjects()
    sent = 0
    for s in subjects:
        if s["user_id"]:
            try:
                await message.bot.send_message(s["user_id"], f"📢 НОВОСТЬ ДКД\n\n{text}")
                sent += 1
            except Exception: pass
    await message.answer(f"✅ Рассылка завершена! Доставлено: {sent}")
    await state.clear()

@dp.callback_query(lambda c: c.data == "admin_reset_confirm")
async def admin_reset_confirm(callback: types.CallbackQuery):
    if not await is_admin_active(callback.from_user.id): return
    await callback.message.edit_text("⚠️ СБРОСИТЬ ВСЕ ГОЛОСА?", reply_markup=build_admin_confirm_reset_keyboard())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_reset_yes")
async def admin_reset_yes(callback: types.CallbackQuery):
    if not await is_admin_active(callback.from_user.id): return
    await clear_votes()
    await callback.message.edit_text("🔄 Сброшено.")
    await callback.answer()

# ===== ПАНЕЛЬ ГОСДУМЫ =====
@dp.callback_query(lambda c: c.data == "duma_panel_law")
async def duma_panel_law(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("📜 ВНЕСЕНИЕ ЗАКОНА\n\nШаг 1/2. Отправь НАЗВАНИЕ.")
    await state.set_state(LawForm.waiting_title)
    await callback.answer()

@dp.message(LawForm.waiting_title)
async def law_title(message: types.Message, state: FSMContext):
    await state.update_data(law_title=message.text)
    await message.answer("Шаг 2/2. Отправь ОПИСАНИЕ.")
    await state.set_state(LawForm.waiting_description)

@dp.message(LawForm.waiting_description)
async def law_description(message: types.Message, state: FSMContext):
    data = await state.get_data()
    username = normalize_username(message.from_user.username)
    law = await create_law(data["law_title"], message.text, username)
    await add_news(f"📜 Внесён закон «{data['law_title']}»")
    await message.answer(f"✅ Законопроект #{law['id']} создан! /laws")
    await state.clear()

@dp.callback_query(lambda c: c.data == "duma_panel_deputies")
async def duma_panel_deputies(callback: types.CallbackQuery):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT s.full_name FROM subjects s JOIN subject_roles sr ON sr.subject_id = s.id JOIN roles r ON r.id = sr.role_id WHERE r.code = 'deputy'")
    text = "👥 ДЕПУТАТЫ\n\n" + "\n".join([f"• {r['full_name']}" for r in rows])
    await callback.message.edit_text(text, reply_markup=build_duma_panel_keyboard())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "duma_panel_laws_list")
async def duma_panel_laws_list(callback: types.CallbackQuery):
    laws = await get_all_laws()
    text = "📋 ЗАКОНЫ\n\n"
    for l in laws[:10]: text += f"#{l['id']} {l['title']} ({l['status']})\n"
    await callback.message.edit_text(text, reply_markup=build_duma_panel_keyboard())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "duma_panel_session")
async def duma_panel_session(callback: types.CallbackQuery):
    laws = await get_all_laws(status="duma")
    if not laws:
        await callback.answer("Нет законов на голосование.", show_alert=True)
        return
    buttons = []
    for l in laws: buttons.append([InlineKeyboardButton(text=f"#{l['id']} {l['title']}", callback_data=f"law_view|{l['id']}")])
    await callback.message.edit_text("🏛 СОЗЫВ СОБРАНИЯ\n\nВыбери закон:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("law_view|"))
async def law_view(callback: types.CallbackQuery):
    lid = int(callback.data.split("|")[1])
    law = await get_law(lid)
    text = f"📜 #{lid} «{law['title']}»\n\n{law['description']}\nСтатус: {law['status']}\nГолоса: За {law['duma_votes_for']} / Против {law['duma_votes_against']}"
    username = normalize_username(callback.from_user.username)
    buttons = []
    if law["status"] == "duma" and await has_role_by_username(username, "deputy"):
        buttons.append([InlineKeyboardButton(text="✅ За", callback_data=f"law_vote|{lid}|for")])
        buttons.append([InlineKeyboardButton(text="❌ Против", callback_data=f"law_vote|{lid}|against")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu_duma")])
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("law_vote|"))
async def law_vote(callback: types.CallbackQuery):
    _, lid, vote = callback.data.split("|")
    username = normalize_username(callback.from_user.username)
    ok, msg = await vote_law(int(lid), username, vote)
    await callback.answer(msg if not ok else "Голос принят!")
    await callback.message.edit_text(f"✅ Голос учтен: {vote}")

@dp.callback_query(lambda c: c.data == "duma_panel_pres_elections")
async def duma_panel_pres_elections(callback: types.CallbackQuery):
    await callback.message.answer("🗳 Функция в разработке.")
    await callback.answer()

# ===== ФОНОВЫЕ ЗАДАЧИ =====
async def background_watcher(bot: Bot):
    global flags
    last_reminder = datetime.now(MSK)
    
    while True:
        try:
            n = now_msk()
            # 1. Напоминания о списках (каждые 6 часов)
            if (n - last_reminder).total_seconds() > 6 * 3600:
                active_duma = await get_active_duma_election()
                if active_duma:
                    async with db_pool.acquire() as conn:
                        parties = await conn.fetch("SELECT * FROM parties WHERE status = 'active'")
                    for p in parties:
                        async with db_pool.acquire() as conn:
                            has_list = await conn.fetchval("SELECT COUNT(*) FROM party_lists WHERE party_id = $1 AND election_id = $2", p['id'], active_duma['id'])
                        if has_list == 0:
                            await add_reputation(p['leader_username'], REP_RULES["list_not_formed"])
                            subj = await get_subject_by_username(p['leader_username'])
                            if subj and subj["user_id"]:
                                try:
                                    await bot.send_message(subj["user_id"], f"⚠️ ВЫ НЕ СФОРМИРОВАЛИ СПИСОК!\nПартия «{p['name']}» не участвует в выборах. Репутация -10.")
                                except Exception: pass
                last_reminder = n

            # 2. Завершение выборов
            if not flags["election_end_notified"] and n >= ELECTION_END:
                flags["election_end_notified"] = True
            
            # 3. Завершение выборов в Думу
            active_duma = await get_active_duma_election()
            if active_duma and active_duma["ends_at"] and n >= from_db_dt(active_duma["ends_at"]):
                winners = await finish_duma_election(active_duma["id"])
                text = "🗳 ВЫБОРЫ В ГОСДУМУ ЗАВЕРШЕНЫ!\n\n"
                for w in winners: text += f"{w['place']}. {w['party']} — {', '.join(w['deputies'])}\n"
                await add_news("🗳 Выборы в ГосДуму завершены!")
                for s in await get_all_subjects():
                    if s["user_id"]:
                        try: await bot.send_message(s["user_id"], text)
                        except Exception: pass

            # 4. Снятие президента по сроку
            term = await get_active_president_term()
            if term and term["ends_at"] and n >= from_db_dt(term["ends_at"]):
                await force_finish_president()
                try: await bot.send_message(ADMIN_ID, "👑 Срок Президента истёк.")
                except Exception: pass

        except Exception as e:
            print(f"Watcher error: {e}")
        await asyncio.sleep(60)

# ===== ЗАПУСК =====
async def main():
    global db_pool
    if not BOT_TOKEN or not DATABASE_URL:
        print("❌ ОШИБКА: BOT_TOKEN или DATABASE_URL не заданы!")
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
