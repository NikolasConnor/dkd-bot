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
VIDEO_FILE_ID = "BAACAgIAAxkBAANLasIfw2IcWeZwXgiPqm4Ne1fHeRAAAsapAAKmCxFKxM0YkvpfMeA9BA"

CANDIDATES = {
    "1": {"name": "Блошихин Кирилл Вадимович", "type": "main"},
    "2": {"name": "Косарев Сергей Сергеевич", "type": "main"},
    "3": {"name": "Проселков Кирилл Романович", "type": "main"},
    "4": {"name": "Горохов Никита Александрович", "type": "additional"},
    "5": {"name": "ПРОТИВ ВСЕХ", "type": "against"},
}
VOTERS = {
    "@Haiser101": {"id": None, "name": "Яровой Иван Сергеевич"},
    "@vozduhanprimee": {"id": None, "name": "Бородин Тимофей Сергеевич"},
    "@spar9d": {"id": None, "name": "Глазков Владислав Юрьевич"},
    "@Cakcer_12": {"id": None, "name": "Головин Максим Сергеевич"},
    "@Dronus01": {"id": None, "name": "Морев Андрей Олегович"},
    "@Nikolas_Connor": {"id": 7934244888, "name": "Горохов Никита Александрович"},
}
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
REP_RULES = {"list_not_formed": -10}

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
class ElectionForm(StatesGroup):
    waiting_date_end = State()
class ProfileForm(StatesGroup):
    waiting_fio = State()
class BroadcastForm(StatesGroup):
    waiting_text = State()
class PresidentAddressForm(StatesGroup):
    waiting_text = State()

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
    formats = ["%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%d-%m-%Y %H:%M", "%d-%m-%Y %H.%M"]
    for fmt in formats:
        try: return datetime.strptime(t, fmt).replace(tzinfo=MSK)
        except Exception: continue
    return None

def check_secret_word(text):
    if not text: return False
    t = " ".join(text.lower().strip().split())
    parts = t.split()
    if len(parts) == 2:
        w1, w2 = parts
        if len(w1) == 3 and w1[0] == "б" and w1[1] == "о" and w1[2] == "г":
            if w2.startswith("эфиоп") or w2.startswith("ефиоп"):
                return True
    return False

async def init_db():
    async with db_pool.acquire() as conn:
        await conn.execute("""CREATE TABLE IF NOT EXISTS votes (id SERIAL PRIMARY KEY, user_id BIGINT NOT NULL, username TEXT, voter_name TEXT, candidate_id TEXT NOT NULL, voted_at TIMESTAMP DEFAULT NOW(), added_by_admin BOOLEAN DEFAULT FALSE)""")
        await conn.execute("""CREATE TABLE IF NOT EXISTS subjects (id SERIAL PRIMARY KEY, user_id BIGINT UNIQUE, username TEXT UNIQUE, full_name TEXT NOT NULL, is_citizen BOOLEAN DEFAULT FALSE, reputation INTEGER DEFAULT 0, joined_at TIMESTAMP DEFAULT NOW())""")
        await conn.execute("""CREATE TABLE IF NOT EXISTS roles (id SERIAL PRIMARY KEY, code TEXT UNIQUE NOT NULL, name TEXT NOT NULL, emoji TEXT DEFAULT '👤', max_holders INTEGER)""")
        await conn.execute("""CREATE TABLE IF NOT EXISTS subject_roles (id SERIAL PRIMARY KEY, subject_id INTEGER REFERENCES subjects(id) ON DELETE CASCADE, role_id INTEGER REFERENCES roles(id) ON DELETE CASCADE, assigned_by BIGINT, assigned_at TIMESTAMP DEFAULT NOW(), UNIQUE(subject_id, role_id))""")
        await conn.execute("""CREATE TABLE IF NOT EXISTS parties (id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL, emoji TEXT DEFAULT '🎭', description TEXT DEFAULT '', founder_username TEXT, leader_username TEXT, status TEXT DEFAULT 'active', created_at TIMESTAMP DEFAULT NOW())""")
        await conn.execute("""CREATE TABLE IF NOT EXISTS party_members (id SERIAL PRIMARY KEY, party_id INTEGER REFERENCES parties(id) ON DELETE CASCADE, username TEXT UNIQUE NOT NULL, joined_at TIMESTAMP DEFAULT NOW())""")
        await conn.execute("""CREATE TABLE IF NOT EXISTS applications (id SERIAL PRIMARY KEY, type TEXT NOT NULL, author_username TEXT NOT NULL, author_name TEXT, target_username TEXT, data JSONB DEFAULT '{}', status TEXT DEFAULT 'pending', created_at TIMESTAMP DEFAULT NOW(), decided_at TIMESTAMP, decided_by BIGINT, reason TEXT)""")
        await conn.execute("""CREATE TABLE IF NOT EXISTS laws (id SERIAL PRIMARY KEY, title TEXT NOT NULL, description TEXT, author_username TEXT, status TEXT DEFAULT 'duma', duma_votes_for INTEGER DEFAULT 0, duma_votes_against INTEGER DEFAULT 0, deadline TIMESTAMP, created_at TIMESTAMP DEFAULT NOW())""")
        await conn.execute("""CREATE TABLE IF NOT EXISTS law_votes (id SERIAL PRIMARY KEY, law_id INTEGER REFERENCES laws(id) ON DELETE CASCADE, voter_username TEXT NOT NULL, vote TEXT NOT NULL, voted_at TIMESTAMP DEFAULT NOW(), UNIQUE(law_id, voter_username))""")
        await conn.execute("""CREATE TABLE IF NOT EXISTS decrees (id SERIAL PRIMARY KEY, title TEXT NOT NULL, text TEXT, author_username TEXT, is_secret BOOLEAN DEFAULT FALSE, secret_for TEXT, created_at TIMESTAMP DEFAULT NOW())""")
        await conn.execute("""CREATE TABLE IF NOT EXISTS news (id SERIAL PRIMARY KEY, text TEXT NOT NULL, source TEXT DEFAULT 'auto', created_at TIMESTAMP DEFAULT NOW())""")
        await conn.execute("""CREATE TABLE IF NOT EXISTS duma_elections (id SERIAL PRIMARY KEY, started_at TIMESTAMP DEFAULT NOW(), ends_at TIMESTAMP, status TEXT DEFAULT 'active', results JSONB DEFAULT '[]')""")
        await conn.execute("""CREATE TABLE IF NOT EXISTS duma_votes (id SERIAL PRIMARY KEY, election_id INTEGER REFERENCES duma_elections(id) ON DELETE CASCADE, voter_username TEXT NOT NULL, party_id INTEGER NOT NULL, voted_at TIMESTAMP DEFAULT NOW(), UNIQUE(election_id, voter_username))""")
        await conn.execute("""CREATE TABLE IF NOT EXISTS president_term (id SERIAL PRIMARY KEY, username TEXT NOT NULL, started_at TIMESTAMP DEFAULT NOW(), ends_at TIMESTAMP, status TEXT DEFAULT 'active')""")
        await conn.execute("""CREATE TABLE IF NOT EXISTS party_lists (id SERIAL PRIMARY KEY, party_id INTEGER REFERENCES parties(id) ON DELETE CASCADE, election_id INTEGER REFERENCES duma_elections(id) ON DELETE CASCADE, username TEXT NOT NULL, UNIQUE(party_id, election_id, username))""")
        await conn.execute("""CREATE TABLE IF NOT EXISTS pres_elections (id SERIAL PRIMARY KEY, started_at TIMESTAMP DEFAULT NOW(), ends_at TIMESTAMP, status TEXT DEFAULT 'active')""")
        await conn.execute("""CREATE TABLE IF NOT EXISTS admin_sessions (user_id BIGINT PRIMARY KEY, is_active BOOLEAN DEFAULT FALSE)""")

async def preload_data():
    async with db_pool.acquire() as conn:
        if await conn.fetchval("SELECT COUNT(*) FROM roles") == 0:
            for r in ROLES_INITIAL:
                await conn.execute("INSERT INTO roles (code, name, emoji, max_holders) VALUES ($1, $2, $3, $4)", r["code"], r["name"], r["emoji"], r["max_holders"])
        if await conn.fetchval("SELECT COUNT(*) FROM subjects") == 0:
            for s in SUBJECTS_INITIAL:
                await conn.execute("INSERT INTO subjects (username, full_name, is_citizen) VALUES ($1, $2, TRUE)", normalize_username(s["username"]), s["full_name"])
        for ir in INITIAL_ROLES:
            uname = normalize_username(ir["username"])
            subj = await conn.fetchrow("SELECT id FROM subjects WHERE username = $1", uname)
            role = await conn.fetchrow("SELECT id FROM roles WHERE code = $1", ir["role_code"])
            if subj and role:
                await conn.execute("INSERT INTO subject_roles (subject_id, role_id) VALUES ($1, $2) ON CONFLICT DO NOTHING", subj["id"], role["id"])
        if await conn.fetchval("SELECT COUNT(*) FROM parties") == 0:
            for p in PARTIES_INITIAL:
                uname = normalize_username(p["leader_username"])
                await conn.execute("INSERT INTO parties (name, emoji, description, founder_username, leader_username) VALUES ($1, $2, $3, $4, $5)", p["name"], p["emoji"], p["description"], uname, uname)
                party = await conn.fetchrow("SELECT id FROM parties WHERE name = $1", p["name"])
                if party: await conn.execute("INSERT INTO party_members (party_id, username) VALUES ($1, $2) ON CONFLICT DO NOTHING", party["id"], uname)

async def get_subject(user_id, username):
    username = normalize_username(username)
    if username:
        s = await get_subject_by_username(username)
        if s: return s
    if user_id: return await get_subject_by_user_id(user_id)
    return None

async def get_subject_by_username(username):
    username = normalize_username(username)
    if not username: return None
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM subjects WHERE username = $1", username)

async def get_subject_by_user_id(user_id):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM subjects WHERE user_id = $1", user_id)

async def get_all_subjects():
    async with db_pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM subjects")

async def update_subject_user_id(username, user_id):
    username = normalize_username(username)
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE subjects SET user_id = $1 WHERE username = $2", user_id, username)

async def get_subject_roles(subject_id):
    async with db_pool.acquire() as conn:
        return await conn.fetch("SELECT r.* FROM roles r JOIN subject_roles sr ON sr.role_id = r.id WHERE sr.subject_id = $1", subject_id)

async def assign_role(subject_id, role_id, assigned_by):
    async with db_pool.acquire() as conn:
        cnt = await conn.fetchval("SELECT COUNT(*) FROM subject_roles WHERE subject_id = $1", subject_id)
        if cnt >= 2: return False, "Максимум 2 должности"
        role = await conn.fetchrow("SELECT * FROM roles WHERE id = $1", role_id)
        if role["max_holders"]:
            holders = await conn.fetchval("SELECT COUNT(*) FROM subject_roles WHERE role_id = $1", role_id)
            if holders >= role["max_holders"]: return False, f"Роль «{role['name']}» занята"
        await conn.execute("INSERT INTO subject_roles (subject_id, role_id, assigned_by) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING", subject_id, role_id, assigned_by)
        return True, "OK"

async def get_all_roles():
    async with db_pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM roles")

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

async def activate_admin(user_id):
    async with db_pool.acquire() as conn:
        await conn.execute("INSERT INTO admin_sessions (user_id, is_active) VALUES ($1, TRUE) ON CONFLICT (user_id) DO UPDATE SET is_active = TRUE", user_id)

async def deactivate_admin(user_id):
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE admin_sessions SET is_active = FALSE WHERE user_id = $1", user_id)

async def get_all_parties(active_only=True):
    async with db_pool.acquire() as conn:
        if active_only: return await conn.fetch("SELECT * FROM parties WHERE status = 'active'")
        return await conn.fetch("SELECT * FROM parties")

async def get_party(party_id):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM parties WHERE id = $1", party_id)

async def get_party_members(party_id):
    async with db_pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM party_members WHERE party_id = $1", party_id)

async def get_user_party(username):
    username = normalize_username(username)
    if not username: return None
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("SELECT p.* FROM parties p JOIN party_members pm ON pm.party_id = p.id WHERE pm.username = $1", username)

async def add_party_member(party_id, username):
    async with db_pool.acquire() as conn:
        await conn.execute("INSERT INTO party_members (party_id, username) VALUES ($1, $2) ON CONFLICT DO NOTHING", party_id, normalize_username(username))

async def remove_party_member(username):
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM party_members WHERE username = $1", normalize_username(username))

async def create_application(app_type, author_username, author_name, target_username, data):
    async with db_pool.acquire() as conn:
        await conn.execute("INSERT INTO applications (type, author_username, author_name, target_username, data) VALUES ($1, $2, $3, $4, $5)", app_type, normalize_username(author_username), author_name, normalize_username(target_username) if target_username else None, json.dumps(data))

async def get_pending_applications(target_username=None):
    async with db_pool.acquire() as conn:
        if target_username: return await conn.fetch("SELECT * FROM applications WHERE status = 'pending' AND target_username = $1", normalize_username(target_username))
        return await conn.fetch("SELECT * FROM applications WHERE status = 'pending'")

async def get_application(app_id):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM applications WHERE id = $1", app_id)

async def approve_application(app_id, decided_by):
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE applications SET status = 'approved', decided_by = $1 WHERE id = $2", decided_by, app_id)

async def reject_application(app_id, decided_by, reason):
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE applications SET status = 'rejected', decided_by = $1, reason = $2 WHERE id = $3", decided_by, reason, app_id)

async def notify_author(bot, app, status_text):
    if not app: return
    subj = await get_subject_by_username(app["author_username"])
    if subj and subj["user_id"]:
        try: await bot.send_message(subj["user_id"], f"📋 Заявка #{app['id']}\n\n{status_text}")
        except: pass

async def create_law(title, description, author_username):
    async with db_pool.acquire() as conn:
        await conn.execute("INSERT INTO laws (title, description, author_username, status) VALUES ($1, $2, $3, 'duma')", title, description, normalize_username(author_username))
        return await conn.fetchrow("SELECT * FROM laws ORDER BY id DESC LIMIT 1")

async def get_law(law_id):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM laws WHERE id = $1", law_id)

async def get_all_laws(status=None):
    async with db_pool.acquire() as conn:
        if status: return await conn.fetch("SELECT * FROM laws WHERE status = $1", status)
        return await conn.fetch("SELECT * FROM laws ORDER BY id DESC")

async def vote_law(law_id, username, vote):
    username = normalize_username(username)
    async with db_pool.acquire() as conn:
        if await conn.fetchrow("SELECT id FROM law_votes WHERE law_id = $1 AND voter_username = $2", law_id, username): return False, "Ты уже голосовал"
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

async def force_finish_president():
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE president_term SET status = 'finished' WHERE status = 'active'")
        role = await conn.fetchrow("SELECT id FROM roles WHERE code = 'president'")
        if role: await conn.execute("DELETE FROM subject_roles WHERE role_id = $1", role["id"])
    await add_news("👑 Президент снят досрочно.")

async def get_active_duma_election():
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM duma_elections WHERE status = 'active' ORDER BY id DESC LIMIT 1")

async def start_duma_election(ends_at):
    async with db_pool.acquire() as conn:
        await conn.execute("INSERT INTO duma_elections (ends_at) VALUES ($1)", to_db_dt(ends_at))

async def vote_duma(election_id, voter_username, party_id):
    async with db_pool.acquire() as conn:
        if await conn.fetchrow("SELECT id FROM duma_votes WHERE election_id = $1 AND voter_username = $2", election_id, normalize_username(voter_username)): return False, "Ты уже голосовал"
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
            winners.append({"party": party["name"], "deputies": deputies})
            for d in deputies:
                subj = await conn.fetchrow("SELECT id FROM subjects WHERE username = $1", d)
                if subj and role: await conn.execute("INSERT INTO subject_roles (subject_id, role_id) VALUES ($1, $2) ON CONFLICT DO NOTHING", subj["id"], role["id"])
        await conn.execute("UPDATE duma_elections SET status = 'finished', results = $1 WHERE id = $2", json.dumps(winners), election_id)
        def build_main_menu(user_id, role, admin_active=False):
    kb = [
        [InlineKeyboardButton(text="👤 Профиль", callback_data="menu_profile"), InlineKeyboardButton(text="🗳 Голосования", callback_data="menu_vote")],
        ...
    if role == "deputy" or user_id == ADMIN_ID: kb.append([InlineKeyboardButton(text="🏛 Панель Госдумы", callback_data="menu_duma")])
    if role == "president" or user_id == ADMIN_ID: kb.append([InlineKeyboardButton(text="👑 Панель Президента", callback_data="menu_president")])
    if user_id == ADMIN_ID: kb.append([InlineKeyboardButton(text="🛠 Админка", callback_data="menu_admin")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

@dp.message(Command("start", "menu"), StateFilter(None))
async def cmd_start(message: types.Message):
    user = message.from_user
    username = normalize_username(user.username)
    subject = await get_subject(user.id, username)
    if not subject:
        await message.answer("🏛 Введите кодовое слово «Бог Эфиопии» для начала регистрации:")
        return
    if subject["user_id"] != user.id: await update_subject_user_id(subject["username"], user.id)
    roles = await get_subject_roles(subject["id"])
    main_role = next((r["code"] for r in roles if r["code"] in ["president", "deputy"]), "subject")
    text = f"🏛 ДКДУСЛУГИ\n\n👤 {subject['full_name']}\n🎖 Роль: {', '.join([r['name'] for r in roles])}\n⭐ Репутация: {subject['reputation']}\n\nВыбери раздел:"
    await message.answer(text, reply_markup=build_main_menu(user.id, main_role, await is_admin_active(user.id)))

@dp.callback_query(lambda c: c.data == "menu_main")
async def back_to_main(callback: types.CallbackQuery):
    user = callback.from_user
    subject = await get_subject(user.id, normalize_username(user.username))
    roles = await get_subject_roles(subject["id"])
    main_role = next((r["code"] for r in roles if r["code"] in ["president", "deputy"]), "subject")
    text = f"🏛 ДКДУСЛУГИ\n\n👤 {subject['full_name']}\n🎖 Роль: {', '.join([r['name'] for r in roles])}\n⭐ Репутация: {subject['reputation']}\n\nВыбери раздел:"
    await callback.message.edit_text(text, reply_markup=build_main_menu(user.id, main_role, await is_admin_active(user.id)))
    await callback.answer()

@dp.callback_query(lambda c: c.data == "menu_profile")
async def menu_profile(callback: types.CallbackQuery):
    subject = await get_subject(callback.from_user.id, callback.from_user.username)
    roles = await get_subject_roles(subject["id"])
    text = f"👤 ПРОФИЛЬ\n\nФИО: {subject['full_name']}\nРоли: {', '.join([r['name'] for r in roles])}\nРепутация: {subject['reputation']}"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✍️ Изменить ФИО", callback_data="profile_edit_fio")], [InlineKeyboardButton(text="◀️ Назад", callback_data="menu_main")]])
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "profile_edit_fio")
async def profile_edit_fio_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("✍️ Введи новое ФИО:")
    await state.set_state(ProfileForm.waiting_fio)
    await callback.answer()

@dp.message(ProfileForm.waiting_fio)
async def profile_edit_fio_save(message: types.Message, state: FSMContext):
    new_fio = message.text.strip()
    subject = await get_subject(message.from_user.id, message.from_user.username)
    if subject:
        async with db_pool.acquire() as conn:
            await conn.execute("UPDATE subjects SET full_name = $1 WHERE id = $2", new_fio, subject["id"])
    await message.answer(f"✅ ФИО изменено на: {new_fio}")
    await state.clear()

@dp.callback_query(lambda c: c.data == "menu_parties")
async def menu_parties(callback: types.CallbackQuery):
    parties = await get_all_parties()
    text = "🎭 ПАРТИИ\n\n"
    buttons = [[InlineKeyboardButton(text=f"{p['emoji']} {p['name']}", callback_data=f"party_view|{p['id']}")] for p in parties]
    buttons.append([InlineKeyboardButton(text="➕ Создать", callback_data="party_create")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu_main")])
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("party_view|"))
async def party_view(callback: types.CallbackQuery):
    pid = int(callback.data.split("|")[1])
    party = await get_party(pid)
    members = await get_party_members(pid)
    text = f"{party['emoji']} {party['name']}\nЛидер: {party['leader_username']}\nСостав: {len(members)}"
    buttons = []
    if party["leader_username"] == normalize_username(callback.from_user.username):
        buttons.append([InlineKeyboardButton(text="📋 Заявки на вступление", callback_data=f"party_apps|{pid}")])
        active_el = await get_active_duma_election()
        if active_el: buttons.append([InlineKeyboardButton(text="📝 Сформировать список", callback_data=f"party_list_form|{pid}|{active_el['id']}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu_parties")])
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("party_apps|"))
async def party_apps(callback: types.CallbackQuery):
    pid = int(callback.data.split("|")[1])
    apps = await get_pending_applications(callback.from_user.username)
    join_apps = [a for a in apps if a["type"] == "join_party"]
    if not join_apps:
        await callback.message.answer("📋 Заявок нет.")
        await callback.answer()
        return
    buttons = [[InlineKeyboardButton(text=f"✅ {a['author_username']}", callback_data=f"approve_join|{a['id']}")] for a in join_apps]
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu_parties")])
    await callback.message.edit_text("📋 ЗАЯВКИ", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("approve_join|"))
async def approve_join(callback: types.CallbackQuery):
    aid = int(callback.data.split("|")[1])
    app = await get_application(aid)
    data = app["data"] if isinstance(app["data"], dict) else json.loads(app["data"])
    await add_party_member(data["party_id"], app["author_username"])
    await approve_application(aid, callback.from_user.id)
    await notify_author(callback.bot, app, "✅ Ты принят в партию!")
    await callback.message.edit_text("✅ Принят.")
    await callback.answer()

@dp.callback_query(lambda c: c.data == "menu_vote")
async def menu_vote(callback: types.CallbackQuery):
    buttons = []
    if await get_active_pres_election(): buttons.append([InlineKeyboardButton(text="🗳 Выборы Президента", callback_data="vote_pres")])
    if await get_active_duma_election(): buttons.append([InlineKeyboardButton(text="🗳 Выборы в ГосДуму", callback_data="vote_duma")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu_main")])
    await callback.message.edit_text("🗳 ГОЛОСОВАНИЯ", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(lambda c: c.data == "vote_pres")
async def vote_pres_menu(callback: types.CallbackQuery):
    buttons = [[InlineKeyboardButton(text=f"{cid}. {c['name']}", callback_data=f"sub_vp_{cid}")] for cid, c in CANDIDATES.items()]
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu_vote")])
    await callback.message.edit_text("🗳 БЮЛЛЕТЕНЬ", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("sub_vp_"))
async def sub_vp(callback: types.CallbackQuery):
    cid = callback.data.split("_")[2]
    username = normalize_username(callback.from_user.username)
    await save_vote(callback.from_user.id, username, VOTERS.get(username, {}).get("name", "Субъект"), cid)
    await callback.message.answer_video(video=VIDEO_FILE_ID, caption=f"✅ Голос принят: {CANDIDATES[cid]['name']}")
    await callback.message.edit_text("Голос учтен.")
    await callback.answer()

@dp.callback_query(lambda c: c.data == "vote_duma")
async def vote_duma_menu(callback: types.CallbackQuery):
    username = normalize_username(callback.from_user.username)
    if await has_role_by_username(username, "party_leader") or username in [c["name"] for c in CANDIDATES.values()]:
        await callback.answer("Ты не можешь голосовать!", show_alert=True)
        return
    el = await get_active_duma_election()
    parties = await get_all_parties()
    buttons = []
    for p in parties:
        async with db_pool.acquire() as conn:
            if await conn.fetchval("SELECT COUNT(*) FROM party_lists WHERE party_id = $1 AND election_id = $2", p['id'], el['id']) > 0:
                buttons.append([InlineKeyboardButton(text=f"{p['emoji']} {p['name']}", callback_data=f"sub_vd_{el['id']}_{p['id']}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu_vote")])
    await callback.message.edit_text("🗳 БЮЛЛЕТЕНЬ (ГосДума)", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("sub_vd_"))
async def sub_vd(callback: types.CallbackQuery):
    _, _, eid, pid = callback.data.split("_")
    await vote_duma(int(eid), callback.from_user.username, int(pid))
    p = await get_party(int(pid))
    await callback.message.answer_video(video=VIDEO_FILE_ID, caption=f"✅ Голос принят: {p['name']}")
    await callback.message.edit_text("Голос учтен.")
    await callback.answer()

@dp.message(StateFilter(None), lambda m: m.text and not m.text.startswith("/") and m.video is None)
async def handle_text(message: types.Message, state: FSMContext):
    if check_secret_word(message.text):
        if await get_subject(message.from_user.id, message.from_user.username): return
        await message.answer("✅ Кодовое слово принято! Введите ФИО:")
        await state.set_state(ProfileForm.waiting_fio)

@dp.callback_query(lambda c: c.data == "menu_duma")
async def menu_duma(callback: types.CallbackQuery):
    if not await has_role_by_username(callback.from_user.username, "deputy") and callback.from_user.id != ADMIN_ID:
        await callback.answer("Вы не депутат.", show_alert=True)
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📜 Внести закон", callback_data="duma_law")], [InlineKeyboardButton(text="◀️ Назад", callback_data="menu_main")]])
    await callback.message.edit_text("🏛 ПАНЕЛЬ ГОСДУМЫ", reply_markup=kb)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "duma_law")
async def duma_law(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите название закона:")
    await state.set_state(LawForm.waiting_title)
    await callback.answer()

@dp.message(LawForm.waiting_title)
async def law_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    await message.answer("Введите описание:")
    await state.set_state(LawForm.waiting_description)

@dp.message(LawForm.waiting_description)
async def law_desc(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await create_law(data["title"], message.text, message.from_user.username)
    await message.answer("✅ Закон создан.")
    await state.clear()
    @dp.callback_query(lambda c: c.data == "menu_president")
async def menu_president(callback: types.CallbackQuery):
    if not (await has_role_by_username(callback.from_user.username, "president") or callback.from_user.id == ADMIN_ID):
        await callback.answer("Вы не президент.", show_alert=True)
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📢 Указ", callback_data="pres_decree")], [InlineKeyboardButton(text="📜 Обращение", callback_data="pres_address")], [InlineKeyboardButton(text="👑 Министры", callback_data="pres_ministers")], [InlineKeyboardButton(text="◀️ Назад", callback_data="menu_main")]])
    await callback.message.edit_text("👑 ПАНЕЛЬ ПРЕЗИДЕНТА", reply_markup=kb)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "pres_decree")
async def pres_decree(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите заголовок указа:")
    await state.set_state(DecreeForm.waiting_title)
    await callback.answer()

@dp.message(DecreeForm.waiting_title)
async def decree_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    await message.answer("Введите текст указа:")
    await state.set_state(DecreeForm.waiting_text)

@dp.message(DecreeForm.waiting_text)
async def decree_text(message: types.Message, state: FSMContext):
    await state.update_data(text=message.text)
    await message.answer("Секретный? Отправьте @username или «нет»:")
    await state.set_state(DecreeForm.waiting_secret)

@dp.message(DecreeForm.waiting_secret)
async def decree_secret(message: types.Message, state: FSMContext):
    data = await state.get_data()
    secret_for = message.text if message.text.lower() != "нет" else None
    await create_decree(data["title"], data["text"], message.from_user.username, bool(secret_for), secret_for)
    await message.answer("✅ Указ создан.")
    await state.clear()

@dp.callback_query(lambda c: c.data == "pres_ministers")
async def pres_ministers(callback: types.CallbackQuery):
    subjects = await get_all_subjects()
    buttons = [[InlineKeyboardButton(text=s['full_name'], callback_data=f"set_min_{s['id']}")] for s in subjects]
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu_president")])
    await callback.message.edit_text("Выберите субъекта для назначения:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("set_min_"))
async def set_min(callback: types.CallbackQuery):
    sid = int(callback.data.split("_")[2])
    roles = await get_all_roles()
    buttons = [[InlineKeyboardButton(text=r['name'], callback_data=f"assign_{sid}_{r['id']}")] for r in roles if r['code'] == 'minister']
    await callback.message.edit_text("Выберите должность:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("assign_"))
async def assign(callback: types.CallbackQuery):
    _, sid, rid = callback.data.split("_")
    ok, msg = await assign_role(int(sid), int(rid), callback.from_user.id)
    await callback.message.edit_text("✅ Назначено." if ok else f"❌ {msg}")
    await callback.answer()

@dp.callback_query(lambda c: c.data == "menu_admin")
async def menu_admin(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID: return
    active = await is_admin_active(callback.from_user.id)
    kb = [[InlineKeyboardButton(text="🔓 Активировать" if not active else "🔒 Деактивировать", callback_data="admin_toggle")], [InlineKeyboardButton(text="◀️ Назад", callback_data="menu_main")]]
    await callback.message.edit_text("🛠 АДМИН-ПАНЕЛЬ", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_toggle")
async def admin_toggle(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID: return
    active = await is_admin_active(callback.from_user.id)
    if active: await deactivate_admin(callback.from_user.id)
    else: await activate_admin(callback.from_user.id)
    await menu_admin(callback)

async def background_watcher(bot: Bot):
    while True:
        try:
            n = now_msk()
            active_duma = await get_active_duma_election()
            if active_duma and active_duma["ends_at"] and n >= from_db_dt(active_duma["ends_at"]):
                await finish_duma_election(active_duma["id"])
        except Exception as e:
            print(f"Watcher error: {e}")
        await asyncio.sleep(60)

async def main():
    global db_pool
    if not BOT_TOKEN or not DATABASE_URL: return
    db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    await init_db()
    await preload_data()
    print("БД подключена.")
    bot = Bot(token=BOT_TOKEN)
    asyncio.create_task(background_watcher(bot))
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
