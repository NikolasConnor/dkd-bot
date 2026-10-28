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
ELECTION_START = datetime(2026, 10, 4, 14, 0, tzinfo=MSK)
ELECTION_END = datetime(2026, 10, 6, 18, 0, tzinfo=MSK)

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
    {"code": "advisor", "name": "Советник", "emoji": "🎓", "max_holders": None},
    {"code": "minister", "name": "Министр", "emoji": "⚖️", "max_holders": None},
    {"code": "deputy", "name": "Депутат", "emoji": "📜", "max_holders": None},
    {"code": "party_leader", "name": "Лидер партии", "emoji": "🎭", "max_holders": None},
    {"code": "subject", "name": "Субъект", "emoji": "👤", "max_holders": None},
]
INITIAL_ROLES = [{"username": "@G12_inthehearts", "role_code": "president"}, {"username": "@Nikolas_Connor", "role_code": "premier"}]
PARTIES_INITIAL = [
    {"name": "Шашлык", "emoji": "🍖", "description": "За природу.", "leader_username": "@Bloha_71"},
    {"name": "Диван", "emoji": "🛋", "description": "За уют.", "leader_username": "@Cakcer_12"},
    {"name": "Хаос", "emoji": "🎲", "description": "За движ.", "leader_username": "@Nikolas_Connor"},
]

db_pool = None
class PartyForm(StatesGroup): waiting_name = State(); waiting_emoji = State(); waiting_description = State()
class LawForm(StatesGroup): waiting_title = State(); waiting_description = State()
class DecreeForm(StatesGroup): waiting_title = State(); waiting_text = State(); waiting_secret = State()
class ElectionForm(StatesGroup): waiting_date_end = State()
class ProfileForm(StatesGroup): waiting_fio = State()
class BroadcastForm(StatesGroup): waiting_text = State()
class PresidentAddressForm(StatesGroup): waiting_text = State()

dp = Dispatcher()

def normalize_username(u): return None if not u else (u if u.startswith("@") else "@" + u)
def now_msk(): return datetime.now(MSK)
def to_db_dt(dt): return None if not dt else (dt.astimezone(MSK).replace(tzinfo=None) if dt.tzinfo else dt)
def from_db_dt(dt): return None if not dt else (dt.replace(tzinfo=MSK) if dt.tzinfo is None else dt)

def check_secret_word(text):
    if not text: return False
    parts = " ".join(text.lower().strip().split()).split()
    if len(parts) == 2:
        w1, w2 = parts
        return len(w1) == 3 and w1[0] == "б" and w1[1] == "о" and w1[2] == "г" and (w2.startswith("эфиоп") or w2.startswith("ефиоп"))
    return False

async def init_db():
    async with db_pool.acquire() as conn:
        await conn.execute("CREATE TABLE IF NOT EXISTS votes (id SERIAL PRIMARY KEY, user_id BIGINT, username TEXT, voter_name TEXT, candidate_id TEXT)")
        await conn.execute("CREATE TABLE IF NOT EXISTS subjects (id SERIAL PRIMARY KEY, user_id BIGINT UNIQUE, username TEXT UNIQUE, full_name TEXT, is_citizen BOOLEAN DEFAULT FALSE, reputation INTEGER DEFAULT 0)")
        await conn.execute("CREATE TABLE IF NOT EXISTS roles (id SERIAL PRIMARY KEY, code TEXT UNIQUE, name TEXT, emoji TEXT, max_holders INTEGER)")
        await conn.execute("CREATE TABLE IF NOT EXISTS subject_roles (id SERIAL PRIMARY KEY, subject_id INTEGER, role_id INTEGER, UNIQUE(subject_id, role_id))")
        await conn.execute("CREATE TABLE IF NOT EXISTS parties (id SERIAL PRIMARY KEY, name TEXT UNIQUE, emoji TEXT, description TEXT, leader_username TEXT, status TEXT DEFAULT 'active')")
        await conn.execute("CREATE TABLE IF NOT EXISTS party_members (id SERIAL PRIMARY KEY, party_id INTEGER, username TEXT UNIQUE)")
        await conn.execute("CREATE TABLE IF NOT EXISTS applications (id SERIAL PRIMARY KEY, type TEXT, author_username TEXT, data JSONB, status TEXT DEFAULT 'pending')")
        await conn.execute("CREATE TABLE IF NOT EXISTS laws (id SERIAL PRIMARY KEY, title TEXT, description TEXT, author_username TEXT, status TEXT DEFAULT 'duma', duma_votes_for INTEGER DEFAULT 0, duma_votes_against INTEGER DEFAULT 0)")
        await conn.execute("CREATE TABLE IF NOT EXISTS law_votes (id SERIAL PRIMARY KEY, law_id INTEGER, voter_username TEXT, vote TEXT, UNIQUE(law_id, voter_username))")
        await conn.execute("CREATE TABLE IF NOT EXISTS decrees (id SERIAL PRIMARY KEY, title TEXT, text TEXT, author_username TEXT, is_secret BOOLEAN, secret_for TEXT)")
        await conn.execute("CREATE TABLE IF NOT EXISTS news (id SERIAL PRIMARY KEY, text TEXT, created_at TIMESTAMP DEFAULT NOW())")
        await conn.execute("CREATE TABLE IF NOT EXISTS duma_elections (id SERIAL PRIMARY KEY, ends_at TIMESTAMP, status TEXT DEFAULT 'active', results JSONB DEFAULT '[]')")
        await conn.execute("CREATE TABLE IF NOT EXISTS duma_votes (id SERIAL PRIMARY KEY, election_id INTEGER, voter_username TEXT, party_id INTEGER, UNIQUE(election_id, voter_username))")
        await conn.execute("CREATE TABLE IF NOT EXISTS party_lists (id SERIAL PRIMARY KEY, party_id INTEGER, election_id INTEGER, username TEXT, UNIQUE(party_id, election_id, username))")
        await conn.execute("CREATE TABLE IF NOT EXISTS pres_elections (id SERIAL PRIMARY KEY, status TEXT DEFAULT 'active')")
        await conn.execute("CREATE TABLE IF NOT EXISTS admin_sessions (user_id BIGINT PRIMARY KEY, is_active BOOLEAN DEFAULT FALSE)")

async def preload_data():
    async with db_pool.acquire() as conn:
        if await conn.fetchval("SELECT COUNT(*) FROM roles") == 0:
            for r in ROLES_INITIAL: await conn.execute("INSERT INTO roles (code, name, emoji, max_holders) VALUES ($1, $2, $3, $4)", r["code"], r["name"], r["emoji"], r["max_holders"])
        if await conn.fetchval("SELECT COUNT(*) FROM subjects") == 0:
            for s in SUBJECTS_INITIAL: await conn.execute("INSERT INTO subjects (username, full_name, is_citizen) VALUES ($1, $2, TRUE)", normalize_username(s["username"]), s["full_name"])
        for ir in INITIAL_ROLES:
            subj = await conn.fetchrow("SELECT id FROM subjects WHERE username = $1", normalize_username(ir["username"]))
            role = await conn.fetchrow("SELECT id FROM roles WHERE code = $1", ir["role_code"])
            if subj and role: await conn.execute("INSERT INTO subject_roles (subject_id, role_id) VALUES ($1, $2) ON CONFLICT DO NOTHING", subj["id"], role["id"])
        if await conn.fetchval("SELECT COUNT(*) FROM parties") == 0:
            for p in PARTIES_INITIAL:
                uname = normalize_username(p["leader_username"])
                await conn.execute("INSERT INTO parties (name, emoji, description, leader_username) VALUES ($1, $2, $3, $4)", p["name"], p["emoji"], p["description"], uname)
                party = await conn.fetchrow("SELECT id FROM parties WHERE name = $1", p["name"])
                if party: await conn.execute("INSERT INTO party_members (party_id, username) VALUES ($1, $2) ON CONFLICT DO NOTHING", party["id"], uname)

async def get_subject(user_id, username):
    username = normalize_username(username)
    async with db_pool.acquire() as conn:
        if username:
            s = await conn.fetchrow("SELECT * FROM subjects WHERE username = $1", username)
            if s: return s
        if user_id: return await conn.fetchrow("SELECT * FROM subjects WHERE user_id = $1", user_id)
    return None

async def get_all_subjects():
    async with db_pool.acquire() as conn: return await conn.fetch("SELECT * FROM subjects")

async def update_subject_user_id(username, user_id):
    async with db_pool.acquire() as conn: await conn.execute("UPDATE subjects SET user_id = $1 WHERE username = $2", user_id, normalize_username(username))

async def get_subject_roles(subject_id):
    async with db_pool.acquire() as conn: return await conn.fetch("SELECT r.* FROM roles r JOIN subject_roles sr ON sr.role_id = r.id WHERE sr.subject_id = $1", subject_id)

async def assign_role(subject_id, role_id, assigned_by):
    async with db_pool.acquire() as conn:
        if await conn.fetchval("SELECT COUNT(*) FROM subject_roles WHERE subject_id = $1", subject_id) >= 2: return False, "Максимум 2"
        role = await conn.fetchrow("SELECT * FROM roles WHERE id = $1", role_id)
        if role["max_holders"] and await conn.fetchval("SELECT COUNT(*) FROM subject_roles WHERE role_id = $1", role_id) >= role["max_holders"]: return False, "Занята"
        await conn.execute("INSERT INTO subject_roles (subject_id, role_id) VALUES ($1, $2) ON CONFLICT DO NOTHING", subject_id, role_id)
        return True, "OK"

async def get_all_roles():
    async with db_pool.acquire() as conn: return await conn.fetch("SELECT * FROM roles")

async def has_role_by_username(username, role_code):
    username = normalize_username(username)
    if not username: return False
    async with db_pool.acquire() as conn: return await conn.fetchrow("SELECT 1 FROM subjects s JOIN subject_roles sr ON sr.subject_id = s.id JOIN roles r ON r.id = sr.role_id WHERE s.username = $1 AND r.code = $2", username, role_code) is not None

async def is_admin_active(user_id):
    if user_id != ADMIN_ID: return False
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT is_active FROM admin_sessions WHERE user_id = $1", user_id)
        return row and row["is_active"]

async def activate_admin(user_id):
    async with db_pool.acquire() as conn: await conn.execute("INSERT INTO admin_sessions (user_id, is_active) VALUES ($1, TRUE) ON CONFLICT (user_id) DO UPDATE SET is_active = TRUE", user_id)

async def deactivate_admin(user_id):
    async with db_pool.acquire() as conn: await conn.execute("UPDATE admin_sessions SET is_active = FALSE WHERE user_id = $1", user_id)

async def get_all_parties(active_only=True):
    async with db_pool.acquire() as conn: return await conn.fetch("SELECT * FROM parties WHERE status = 'active'") if active_only else await conn.fetch("SELECT * FROM parties")

async def get_party(party_id):
    async with db_pool.acquire() as conn: return await conn.fetchrow("SELECT * FROM parties WHERE id = $1", party_id)

async def get_party_members(party_id):
    async with db_pool.acquire() as conn: return await conn.fetch("SELECT * FROM party_members WHERE party_id = $1", party_id)

async def add_party_member(party_id, username):
    async with db_pool.acquire() as conn: await conn.execute("INSERT INTO party_members (party_id, username) VALUES ($1, $2) ON CONFLICT DO NOTHING", party_id, normalize_username(username))

async def create_application(app_type, author_username, author_name, target_username, data):
    async with db_pool.acquire() as conn: await conn.execute("INSERT INTO applications (type, author_username, data) VALUES ($1, $2, $3)", app_type, normalize_username(author_username), json.dumps(data))

async def get_pending_applications(target_username=None):
    async with db_pool.acquire() as conn: return await conn.fetch("SELECT * FROM applications WHERE status = 'pending'")

async def get_application(app_id):
    async with db_pool.acquire() as conn: return await conn.fetchrow("SELECT * FROM applications WHERE id = $1", app_id)

async def approve_application(app_id, decided_by):
    async with db_pool.acquire() as conn: await conn.execute("UPDATE applications SET status = 'approved' WHERE id = $1", app_id)

async def reject_application(app_id, decided_by, reason):
    async with db_pool.acquire() as conn: await conn.execute("UPDATE applications SET status = 'rejected' WHERE id = $1", app_id)

async def notify_author(bot, app, status_text):
    if not app: return
    subj = await get_subject(None, app["author_username"])
    if subj and subj["user_id"]:
        try: await bot.send_message(subj["user_id"], f"📋 Заявка #{app['id']}\n\n{status_text}")
        except: pass

async def create_law(title, description, author_username):
    async with db_pool.acquire() as conn:
        await conn.execute("INSERT INTO laws (title, description, author_username, status) VALUES ($1, $2, $3, 'duma')", title, description, normalize_username(author_username))
        return await conn.fetchrow("SELECT * FROM laws ORDER BY id DESC LIMIT 1")

async def get_law(law_id):
    async with db_pool.acquire() as conn: return await conn.fetchrow("SELECT * FROM laws WHERE id = $1", law_id)

async def get_all_laws(status=None):
    async with db_pool.acquire() as conn: return await conn.fetch("SELECT * FROM laws WHERE status = $1", status) if status else await conn.fetch("SELECT * FROM laws ORDER BY id DESC")

async def create_decree(title, text, author_username, is_secret=False, secret_for=None):
    async with db_pool.acquire() as conn: await conn.execute("INSERT INTO decrees (title, text, author_username, is_secret, secret_for) VALUES ($1, $2, $3, $4, $5)", title, text, normalize_username(author_username), is_secret, normalize_username(secret_for) if secret_for else None)

async def add_news(text, source="auto"):
    async with db_pool.acquire() as conn: await conn.execute("INSERT INTO news (text) VALUES ($1)", text)

async def get_news(limit=20):
    async with db_pool.acquire() as conn: return await conn.fetch("SELECT * FROM news ORDER BY id DESC LIMIT $1", limit)

async def save_vote(user_id, username, voter_name, candidate_id):
    async with db_pool.acquire() as conn: await conn.execute("INSERT INTO votes (user_id, username, voter_name, candidate_id) VALUES ($1, $2, $3, $4)", user_id, username, voter_name, candidate_id)

async def get_active_duma_election():
    async with db_pool.acquire() as conn: return await conn.fetchrow("SELECT * FROM duma_elections WHERE status = 'active' ORDER BY id DESC LIMIT 1")

async def get_active_pres_election():
    async with db_pool.acquire() as conn: return await conn.fetchrow("SELECT * FROM pres_elections WHERE status = 'active'")

async def start_duma_election(ends_at):
    async with db_pool.acquire() as conn: await conn.execute("INSERT INTO duma_elections (ends_at) VALUES ($1)", to_db_dt(ends_at))

async def vote_duma(election_id, voter_username, party_id):
    async with db_pool.acquire() as conn:
        if await conn.fetchrow("SELECT id FROM duma_votes WHERE election_id = $1 AND voter_username = $2", election_id, normalize_username(voter_username)): return False
        await conn.execute("INSERT INTO duma_votes (election_id, voter_username, party_id) VALUES ($1, $2, $3)", election_id, normalize_username(voter_username), party_id)
        return True

async def finish_duma_election(election_id):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT party_id, COUNT(*) as cnt FROM duma_votes WHERE election_id = $1 GROUP BY party_id ORDER BY cnt DESC", election_id)
        await conn.execute("DELETE FROM subject_roles WHERE role_id IN (SELECT id FROM roles WHERE code = 'deputy')")
        role = await conn.fetchrow("SELECT id FROM roles WHERE code = 'deputy'")
        winners = []
        for idx, r in enumerate(rows):
            party = await conn.fetchrow("SELECT * FROM parties WHERE id = $1", r["party_id"])
            if not party: continue
            party_list = await conn.fetch("SELECT username FROM party_lists WHERE party_id = $1 AND election_id = $2", party["id"], election_id)
            deputies = [m["username"] for m in party_list]
            winners.append({"party": party["name"], "deputies": deputies})
            for d in deputies:
                subj = await conn.fetchrow("SELECT id FROM subjects WHERE username = $1", d)
                if subj and role: await conn.execute("INSERT INTO subject_roles (subject_id, role_id) VALUES ($1, $2) ON CONFLICT DO NOTHING", subj["id"], role["id"])
        await conn.execute("UPDATE duma_elections SET status = 'finished', results = $1 WHERE id = $2", json.dumps(winners), election_id)

async def force_finish_president():
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE pres_elections SET status = 'finished' WHERE status = 'active'")
        role = await conn.fetchrow("SELECT id FROM roles WHERE code = 'president'")
        if role: await conn.execute("DELETE FROM subject_roles WHERE role_id = $1", role["id"])

def build_main_menu(user_id, role, admin_active=False):
    kb = [[InlineKeyboardButton(text="👤 Профиль", callback_data="menu_profile"), InlineKeyboardButton(text="🗳 Голосования", callback_data="menu_vote")], [InlineKeyboardButton(text="🎭 Партии", callback_data="menu_parties"), InlineKeyboardButton(text="📜 Документы", callback_data="menu_docs")], [InlineKeyboardButton(text="📰 Газета", callback_data="menu_news"), InlineKeyboardButton(text="⚙️ Настройки", callback_data="menu_settings")], [InlineKeyboardButton(text="❓ Помощь", callback_data="menu_help")]]
    if role == "deputy" or user_id == ADMIN_ID: kb.append([InlineKeyboardButton(text="🏛 Панель Госдумы", callback_data="menu_duma")])
    if role == "president" or user_id == ADMIN_ID: kb.append([InlineKeyboardButton(text="👑 Панель Президента", callback_data="menu_president")])
    if user_id == ADMIN_ID: kb.append([InlineKeyboardButton(text="🛠 Админка", callback_data="menu_admin")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

@dp.message(Command("start", "menu"), StateFilter(None))
async def cmd_start(message: types.Message):
    subject = await get_subject(message.from_user.id, message.from_user.username)
    if not subject:
        await message.answer("🏛 Введите кодовое слово «Бог Эфиопии» для начала регистрации:")
        return
    if subject["user_id"] != message.from_user.id: await update_subject_user_id(subject["username"], message.from_user.id)
    roles = await get_subject_roles(subject["id"])
    main_role = next((r["code"] for r in roles if r["code"] in ["president", "deputy"]), "subject")
    text = f"🏛 ДКДУСЛУГИ\n\n👤 {subject['full_name']}\n🎖 Роль: {', '.join([r['name'] for r in roles])}\n⭐ Репутация: {subject['reputation']}\n\nВыбери раздел:"
    await message.answer(text, reply_markup=build_main_menu(message.from_user.id, main_role, await is_admin_active(message.from_user.id)))

@dp.callback_query(lambda c: c.data == "menu_main")
async def back_to_main(callback: types.CallbackQuery):
    subject = await get_subject(callback.from_user.id, callback.from_user.username)
    roles = await get_subject_roles(subject["id"])
    main_role = next((r["code"] for r in roles if r["code"] in ["president", "deputy"]), "subject")
    text = f"🏛 ДКДУСЛУГИ\n\n👤 {subject['full_name']}\n🎖 Роль: {', '.join([r['name'] for r in roles])}\n⭐ Репутация: {subject['reputation']}\n\nВыбери раздел:"
    await callback.message.edit_text(text, reply_markup=build_main_menu(callback.from_user.id, main_role, await is_admin_active(callback.from_user.id)))
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
    if check_secret_word(message.text):
        await message.answer("❌ Это кодовое слово. Введи новое ФИО.")
        return
    new_fio = message.text.strip()
    if len(new_fio) < 3:
        await message.answer("❌ Слишком короткое.")
        return
    subject = await get_subject(message.from_user.id, message.from_user.username)
    if subject:
        async with db_pool.acquire() as conn: await conn.execute("UPDATE subjects SET full_name = $1 WHERE id = $2", new_fio, subject["id"])
    await message.answer(f"✅ ФИО изменено на: {new_fio}")
    await state.clear()

@dp.callback_query(lambda c: c.data == "menu_news")
async def menu_news(callback: types.CallbackQuery):
    news = await get_news(10)
    text = "📰 ЗЕ ТУНИЯНЦЫ НЬЮС\n\n"
    if not news: text += "Новостей пока нет."
    else:
        for n in news: text += f"[{n['created_at'].strftime('%d.%m %H:%M')}] {n['text']}\n\n"
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔄 Обновить", callback_data="menu_news"), InlineKeyboardButton(text="◀️ Назад", callback_data="menu_main")]]))
    await callback.answer()

@dp.callback_query(lambda c: c.data == "menu_settings")
async def menu_settings(callback: types.CallbackQuery):
    await callback.message.edit_text("⚙️ НАСТРОЙКИ", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✍️ Изменить ФИО", callback_data="profile_edit_fio")], [InlineKeyboardButton(text="◀️ Назад", callback_data="menu_main")]]))
    await callback.answer()

@dp.callback_query(lambda c: c.data == "menu_docs")
async def menu_docs(callback: types.CallbackQuery):
    await callback.message.edit_text("📜 ДОКУМЕНТЫ", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📖 Конституция", callback_data="doc_const")], [InlineKeyboardButton(text="📜 Законы", callback_data="doc_laws")], [InlineKeyboardButton(text="◀️ Назад", callback_data="menu_main")]]))
    await callback.answer()

@dp.callback_query(lambda c: c.data == "doc_const")
async def doc_const(callback: types.CallbackQuery):
    await callback.message.edit_text("📖 КОНСТИТУЦИЯ ДКД\n\n1. Мы — Тунеядцы Алкоголики.\n2. Власть делится на ветви.\n3. Президент избирается на 3 месяца.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="menu_docs")]]))
    await callback.answer()

@dp.callback_query(lambda c: c.data == "doc_laws")
async def doc_laws(callback: types.CallbackQuery):
    laws = await get_all_laws()
    text = "📜 ЗАКОНЫ\n\n"
    if not laws: text += "Законов пока нет."
    else:
        for l in laws[:10]: text += f"#{l['id']} {l['title']} ({l['status']})\n"
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="menu_docs")]]))
    await callback.answer()

@dp.callback_query(lambda c: c.data == "menu_help")
async def menu_help(callback: types.CallbackQuery):
    await callback.message.edit_text("❓ ПОМОЩЬ\n\n• /start — главное меню\n• 👤 Профиль — твои данные\n• 🗳 Голосования — выборы\n• 🎭 Партии — партии\n• 📜 Документы — законы\n• 📰 Газета — новости\n• ⚙️ Настройки — смена ФИО", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="menu_main")]]))
    await callback.answer()

@dp.callback_query(lambda c: c.data == "menu_parties")
async def menu_parties(callback: types.CallbackQuery):
    parties = await get_all_parties()
    buttons = [[InlineKeyboardButton(text=f"{p['emoji']} {p['name']}", callback_data=f"party_view|{p['id']}")] for p in parties]
    buttons.append([InlineKeyboardButton(text="➕ Создать", callback_data="party_create")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu_main")])
    await callback.message.edit_text("🎭 ПАРТИИ", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("party_view|"))
async def party_view(callback: types.CallbackQuery):
    pid = int(callback.data.split("|")[1])
    party = await get_party(pid)
    members = await get_party_members(pid)
    text = f"{party['emoji']} {party['name']}\nЛидер: {party['leader_username']}\nСостав: {len(members)}"
    buttons = []
    if party["leader_username"] == normalize_username(callback.from_user.username): buttons.append([InlineKeyboardButton(text="📋 Заявки", callback_data=f"party_apps|{pid}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu_parties")])
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("party_apps|"))
async def party_apps(callback: types.CallbackQuery):
    apps = await get_pending_applications(callback.from_user.username)
    join_apps = [a for a in apps if a["type"] == "join_party"]
    if not join_apps:
        await callback.message.answer("📋 Заявок нет."); await callback.answer(); return
    buttons = [[InlineKeyboardButton(text=f"✅ {a['author_username']}", callback_data=f"approve_join|{a['id']}")] for a in join_apps]
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu_parties")])
    await callback.message.edit_text("📋 ЗАЯВКИ", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("approve_join|"))
async def approve_join(callback: types.CallbackQuery):
    aid = int(callback.data.split("|")[1])
    app = await get_application(aid)
    data = app["data"] if isinstance(app["data"], dict) else json.loads(app["data"])
    await add_party_member(data.get("party_id"), app["author_username"])
    await approve_application(aid, callback.from_user.id)
    await notify_author(callback.bot, app, "✅ Ты принят в партию!")
    await callback.message.edit_text("✅ Принят.")
    await callback.answer()

@dp.callback_query(lambda c: c.data == "party_create")
async def party_create(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("➕ СОЗДАНИЕ ПАРТИИ\n\nШаг 1/3. Отправь НАЗВАНИЕ:")
    await state.set_state(PartyForm.waiting_name)
    await callback.answer()

@dp.message(PartyForm.waiting_name)
async def party_name(message: types.Message, state: FSMContext):
    await state.update_data(party_name=message.text.strip())
    await message.answer(f"Название: {message.text.strip()}\n\nШаг 2/3. Отправь ЭМОДЗИ:")
    await state.set_state(PartyForm.waiting_emoji)

@dp.message(PartyForm.waiting_emoji)
async def party_emoji(message: types.Message, state: FSMContext):
    await state.update_data(party_emoji=message.text.strip())
    await message.answer(f"Эмодзи: {message.text.strip()}\n\nШаг 3/3. Отправь ПРОГРАММУ:")
    await state.set_state(PartyForm.waiting_description)

@dp.message(PartyForm.waiting_description)
async def party_description(message: types.Message, state: FSMContext):
    data = await state.get_data()
    username = normalize_username(message.from_user.username)
    await create_application("create_party", username, message.from_user.full_name, None, {"name": data.get("party_name"), "emoji": data.get("party_emoji"), "description": message.text.strip()})
    await message.answer(f"✅ Заявка на партию «{data.get('party_name')}» отправлена Президенту.")
    await state.clear()

@dp.callback_query(lambda c: c.data == "menu_vote")
async def menu_vote(callback: types.CallbackQuery):
    buttons = []
    if await get_active_pres_election(): buttons.append([InlineKeyboardButton(text="🗳 Выборы Президента", callback_data="vote_pres")])
    if await get_active_duma_election(): buttons.append([InlineKeyboardButton(text="🗳 Выборы в ГосДуму", callback_data="vote_duma")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu_main")])
    text = "🗳 ГОЛОСОВАНИЯ\n\nВыбери:" if len(buttons) > 1 else "🗳 ГОЛОСОВАНИЯ\n\nСейчас нет активных голосований."
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
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
    await callback.message.edit_text("Голос учтен.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ В меню", callback_data="menu_main")]]))
    await callback.answer()

@dp.callback_query(lambda c: c.data == "vote_duma")
async def vote_duma_menu(callback: types.CallbackQuery):
    username = normalize_username(callback.from_user.username)
    if await has_role_by_username(username, "party_leader"):
        await callback.answer("Лидеры партий не голосуют!", show_alert=True); return
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
    await callback.message.edit_text("Голос учтен.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ В меню", callback_data="menu_main")]]))
    await callback.answer()

@dp.message(StateFilter(None), lambda m: m.text and not m.text.startswith("/") and m.video is None)
async def handle_text(message: types.Message, state: FSMContext):
    if check_secret_word(message.text):
        if await get_subject(message.from_user.id, message.from_user.username): return
        await message.answer("✅ Кодовое слово принято! Введите ФИО:")
        await state.set_state(ProfileForm.waiting_fio)
        return
    await message.answer("Используйте кнопки меню.")

@dp.callback_query(lambda c: c.data == "menu_duma")
async def menu_duma(callback: types.CallbackQuery):
    if not await has_role_by_username(callback.from_user.username, "deputy") and callback.from_user.id != ADMIN_ID:
        await callback.answer("Вы не депутат.", show_alert=True); return
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
        await callback.answer("Вы не президент.", show_alert=True); return
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

@dp.callback_query(lambda c: c.data == "pres_address")
async def pres_address(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Отправьте текст обращения:")
    await state.set_state(PresidentAddressForm.waiting_text)
    await callback.answer()

@dp.message(PresidentAddressForm.waiting_text)
async def pres_address_send(message: types.Message, state: FSMContext):
    text = message.text
    await add_news(f"📜 ОБРАЩЕНИЕ: {text}")
    subjects = await get_all_subjects()
    for s in subjects:
        if s["user_id"]:
            try: await message.bot.send_message(s["user_id"], f"📜 ОБРАЩЕНИЕ ПРЕЗИДЕНТА\n\n{text}")
            except: pass
    await message.answer("✅ Разослано.")
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
    if not active:
        kb = [[InlineKeyboardButton(text="🔓 Активировать", callback_data="admin_toggle")], [InlineKeyboardButton(text="◀️ Назад", callback_data="menu_main")]]
    else:
        kb = [[InlineKeyboardButton(text="🔒 Деактивировать", callback_data="admin_toggle")], [InlineKeyboardButton(text="👥 Субъекты", callback_data="admin_subjects"), InlineKeyboardButton(text="📋 Заявки", callback_data="admin_apps")], [InlineKeyboardButton(text="🗳 ГосДума", callback_data="admin_duma"), InlineKeyboardButton(text="👑 Снять Президента", callback_data="admin_pres_finish_now")], [InlineKeyboardButton(text="📢 Опубликовать всем", callback_data="admin_broadcast")], [InlineKeyboardButton(text="🔄 Сброс", callback_data="admin_reset_confirm")], [InlineKeyboardButton(text="◀️ Назад", callback_data="menu_main")]]
    status = "🔓 АКТИВЕН" if active else "🔒 НЕ АКТИВЕН"
    await callback.message.edit_text(f"🛠 АДМИН-ПАНЕЛЬ\n\nСтатус: {status}", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_toggle")
async def admin_toggle(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID: return
    if await is_admin_active(callback.from_user.id): await deactivate_admin(callback.from_user.id)
    else: await activate_admin(callback.from_user.id)
    await menu_admin(callback)

@dp.callback_query(lambda c: c.data == "admin_subjects")
async def admin_subjects(callback: types.CallbackQuery):
    if not await is_admin_active(callback.from_user.id): return
    subjects = await get_all_subjects()
    buttons = [[InlineKeyboardButton(text=s['full_name'], callback_data=f"admin_subj_view|{s['id']}")] for s in subjects]
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu_admin")])
    await callback.message.edit_text("👥 СУБЪЕКТЫ", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("admin_subj_view|"))
async def admin_subj_view(callback: types.CallbackQuery):
    if not await is_admin_active(callback.from_user.id): return
    sid = int(callback.data.split("|")[1])
    async with db_pool.acquire() as conn: s = await conn.fetchrow("SELECT * FROM subjects WHERE id = $1", sid)
    roles = await get_subject_roles(sid)
    await callback.message.answer(f"👤 {s['full_name']}\nРоли: {', '.join([r['name'] for r in roles])}\nРепутация: {s['reputation']}")
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_apps")
async def admin_apps(callback: types.CallbackQuery):
    if not await is_admin_active(callback.from_user.id): return
    apps = await get_pending_applications()
    if not apps:
        await callback.message.edit_text("📋 Заявок нет.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="menu_admin")]])); await callback.answer(); return
    buttons = [[InlineKeyboardButton(text=f"#{a['id']} {a['type']} от {a['author_username']}", callback_data=f"admin_app_view|{a['id']}")] for a in apps]
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu_admin")])
    await callback.message.edit_text("📋 ЗАЯВКИ", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("admin_app_view|"))
async def admin_app_view(callback: types.CallbackQuery):
    if not await is_admin_active(callback.from_user.id): return
    aid = int(callback.data.split("|")[1])
    app = await get_application(aid)
    buttons = [[InlineKeyboardButton(text="✅ Одобрить", callback_data=f"admin_app_approve|{aid}")], [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin_app_reject|{aid}")], [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_apps")]]
    await callback.message.edit_text(f"Заявка #{aid}: {app['type']} от {app['author_username']}", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("admin_app_approve|"))
async def admin_app_approve(callback: types.CallbackQuery):
    if not await is_admin_active(callback.from_user.id): return
    aid = int(callback.data.split("|")[1])
    app = await get_application(aid)
    data = app["data"] if isinstance(app["data"], dict) else json.loads(app["data"])
    if app["type"] == "citizenship":
        async with db_pool.acquire() as conn: await conn.execute("UPDATE subjects SET is_citizen = TRUE WHERE username = $1", app["author_username"])
    elif app["type"] == "create_party":
        async with db_pool.acquire() as conn: await conn.execute("INSERT INTO parties (name, emoji, description, leader_username) VALUES ($1, $2, $3, $4)", data.get("name"), data.get("emoji"), data.get("description"), app["author_username"])
    elif app["type"] == "join_party":
        await add_party_member(data.get("party_id"), app["author_username"])
    await approve_application(aid, ADMIN_ID)
    await callback.message.edit_text("✅ Одобрено.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ В админку", callback_data="menu_admin")]]))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("admin_app_reject|"))
async def admin_app_reject(callback: types.CallbackQuery):
    if not await is_admin_active(callback.from_user.id): return
    aid = int(callback.data.split("|")[1])
    await reject_application(aid, ADMIN_ID, "Отклонено Админом")
    await callback.message.edit_text("❌ Отклонено.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ В админку", callback_data="menu_admin")]]))
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_duma")
async def admin_duma(callback: types.CallbackQuery):
    if not await is_admin_active(callback.from_user.id): return
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🗳 Начать выборы", callback_data="admin_duma_start")], [InlineKeyboardButton(text="🛑 Завершить", callback_data="admin_duma_finish_now")], [InlineKeyboardButton(text="◀️ Назад", callback_data="menu_admin")]])
    await callback.message.edit_text("🗳 ГОСДУМА", reply_markup=kb)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_duma_start")
async def admin_duma_start(callback: types.CallbackQuery, state: FSMContext):
    if not await is_admin_active(callback.from_user.id): return
    await callback.message.answer("Отправь ДАТУ окончания выборов (2027-01-15 20:00):")
    await state.set_state(ElectionForm.waiting_date_end)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_duma_finish_now")
async def admin_duma_finish_now(callback: types.CallbackQuery):
    if not await is_admin_active(callback.from_user.id): return
    el = await get_active_duma_election()
    if el: await finish_duma_election(el["id"]); await callback.message.answer("🛑 Выборы завершены.")
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_pres_finish_now")
async def admin_pres_finish_now(callback: types.CallbackQuery):
    if not await is_admin_active(callback.from_user.id): return
    await force_finish_president()
    await callback.message.answer("👑 Президент снят.")
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_broadcast")
async def admin_broadcast(callback: types.CallbackQuery, state: FSMContext):
    if not await is_admin_active(callback.from_user.id): return
    await callback.message.answer("📢 Текст для рассылки ВСЕМ:")
    await state.set_state(BroadcastForm.waiting_text)
    await callback.answer()

@dp.message(BroadcastForm.waiting_text)
async def broadcast_send(message: types.Message, state: FSMContext):
    text = message.text.strip()
    await add_news(f"📢 {text}")
    sent = 0
    for s in await get_all_subjects():
        if s["user_id"]:
            try: await message.bot.send_message(s["user_id"], f"📢 НОВОСТЬ ДКД\n\n{text}"); sent += 1
            except: pass
    await message.answer(f"✅ Разослано: {sent}.")
    await state.clear()

@dp.callback_query(lambda c: c.data == "admin_reset_confirm")
async def admin_reset_confirm(callback: types.CallbackQuery):
    if not await is_admin_active(callback.from_user.id): return
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⚠️ ДА", callback_data="admin_reset_yes")], [InlineKeyboardButton(text="◀️ Отмена", callback_data="menu_admin")]])
    await callback.message.edit_text("⚠️ Сбросить голоса?", reply_markup=kb)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_reset_yes")
async def admin_reset_yes(callback: types.CallbackQuery):
    if not await is_admin_active(callback.from_user.id): return
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM votes")
        await conn.execute("DELETE FROM duma_votes")
    await callback.message.edit_text("🔄 Сброшено.")
    await callback.answer()

@dp.message(ElectionForm.waiting_date_end)
async def election_date_end(message: types.Message, state: FSMContext):
    try:
        dt = datetime.strptime(message.text.strip(), "%Y-%m-%d %H:%M").replace(tzinfo=MSK)
        await start_duma_election(dt)
        await message.answer(f"✅ Назначено до {dt.strftime('%d.%m.%Y %H:%M')}")
    except: await message.answer("❌ Неверный формат.")
    await state.clear()

async def background_watcher(bot: Bot):
    while True:
        try:
            n = now_msk()
            el = await get_active_duma_election()
            if el and el["ends_at"] and n >= from_db_dt(el["ends_at"]): await finish_duma_election(el["id"])
        except Exception as e: print(f"Watcher: {e}")
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
