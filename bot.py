# === ЧАСТЬ 1 ===
import asyncio
import logging
import json
from datetime import datetime
from typing import Dict, Any

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
import asyncpg

# Конфигурация логирования и токена бота
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = "ВАШ_ТОКЕН_БОТА"
ADMIN_ID = 7934244888
DB_DSN = "postgresql://postgres:postgres@localhost:5432/telegram_bot"

CANDIDATES = {
    1: {"name": "Кандидат А", "username": "candidate_a"},
    2: {"name": "Кандидат Б", "username": "candidate_b"},
    3: {"name": "Кандидат В", "username": "candidate_c"}
}

# Инициализация бота, диспетчера и роутера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

# Стейты для FSM
class Form(StatesGroup):
    change_fio = State()
    create_party = State()
    join_party = State()
    create_law = State()
    create_decree = State()
    create_secret_decree = State()
    secret_decree_target = State()
    broadcast_news = State()
    broadcast_president = State()

async def init_db():
    conn = await asyncpg.connect(DB_DSN)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS votes (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            username VARCHAR(255),
            voter_name VARCHAR(255),
            candidate_id INT
        );
        CREATE TABLE IF NOT EXISTS subjects (
            user_id BIGINT PRIMARY KEY,
            username VARCHAR(255),
            full_name VARCHAR(255),
            is_citizen BOOLEAN DEFAULT TRUE,
            reputation INT DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS roles (
            code VARCHAR(50) PRIMARY KEY,
            name VARCHAR(255),
            emoji VARCHAR(10),
            max_holders INT
        );
        CREATE TABLE IF NOT EXISTS subject_roles (
            subject_id BIGINT REFERENCES subjects(user_id) ON DELETE CASCADE,
            role_id VARCHAR(50) REFERENCES roles(code) ON DELETE CASCADE,
            PRIMARY KEY (subject_id, role_id)
        );
        CREATE TABLE IF NOT EXISTS parties (
            name VARCHAR(255) PRIMARY KEY,
            emoji VARCHAR(10),
            description TEXT,
            leader_username VARCHAR(255),
            status VARCHAR(50)
        );
        CREATE TABLE IF NOT EXISTS party_members (
            id SERIAL PRIMARY KEY,
            party_id VARCHAR(255) REFERENCES parties(name) ON DELETE CASCADE,
            username VARCHAR(255)
        );
        CREATE TABLE IF NOT EXISTS applications (
            id SERIAL PRIMARY KEY,
            type VARCHAR(50),
            author_username VARCHAR(255),
            data JSONB,
            status VARCHAR(50)
        );
        CREATE TABLE IF NOT EXISTS laws (
            id SERIAL PRIMARY KEY,
            title VARCHAR(255),
            description TEXT,
            status VARCHAR(50),
            duma_votes_for INT DEFAULT 0,
            duma_votes_against INT DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS decrees (
            id SERIAL PRIMARY KEY,
            title VARCHAR(255),
            text TEXT,
            is_secret BOOLEAN DEFAULT FALSE,
            secret_for VARCHAR(255)
        );
        CREATE TABLE IF NOT EXISTS news (
            id SERIAL PRIMARY KEY,
            text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS duma_elections (
            id SERIAL PRIMARY KEY,
            ends_at TIMESTAMP,
            status VARCHAR(50)
        );
        CREATE TABLE IF NOT EXISTS duma_votes (
            id SERIAL PRIMARY KEY,
            election_id INT REFERENCES duma_elections(id) ON DELETE CASCADE,
            voter_username VARCHAR(255),
            party_id VARCHAR(255) REFERENCES parties(name) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS party_lists (
            id SERIAL PRIMARY KEY,
            party_id VARCHAR(255) REFERENCES parties(name) ON DELETE CASCADE,
            election_id INT REFERENCES duma_elections(id) ON DELETE CASCADE,
            username VARCHAR(255)
        );
        CREATE TABLE IF NOT EXISTS admin_sessions (
            user_id BIGINT PRIMARY KEY,
            is_active BOOLEAN DEFAULT FALSE
        );
    """)
    await conn.close()

async def preload_data(pool):
    async with pool.acquire() as conn:
        roles = [
            ('admin', 'Администратор', '👑', 1),
            ('president', 'Президент', '🏛', 1),
            ('deputy', 'Депутат', '📜', 450),
            ('minister', 'Министр', '💼', 20)
        ]
        for code, name, emoji, max_holders in roles:
            await conn.execute("""
                INSERT INTO roles (code, name, emoji, max_holders)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (code) DO NOTHING
            """, code, name, emoji, max_holders)

        await conn.execute("""
            INSERT INTO subjects (user_id, username, full_name, is_citizen, reputation)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (user_id) DO NOTHING
        """, ADMIN_ID, "admin_user", "Главный Администратор", True, 100)

        await conn.execute("""
            INSERT INTO subject_roles (subject_id, role_id)
            VALUES ($1, $2)
            ON CONFLICT DO NOTHING
        """, ADMIN_ID, 'admin')

def get_main_keyboard(is_admin=False, is_president=False, is_deputy=False):
    buttons = [
        [InlineKeyboardButton(text="👤 Профиль", callback_key="menu_profile"),
         InlineKeyboardButton(text="🗳 Голосования", callback_key="menu_vote")],
        [InlineKeyboardButton(text="🎉 Партии", callback_key="menu_parties"),
         InlineKeyboardButton(text="📄 Документы", callback_key="menu_docs")],
        [InlineKeyboardButton(text="📰 Газета", callback_key="menu_news"),
         InlineKeyboardButton(text="⚙ Настройки", callback_key="menu_settings")],
        [InlineKeyboardButton(text="❓ Помощь", callback_key="menu_help")]
    ]
    if is_admin:
        buttons.append([InlineKeyboardButton(text="👑 Панель Админа", callback_key="menu_admin")])
    if is_president:
        buttons.append([InlineKeyboardButton(text="🏛 Панель Президента", callback_key="menu_president")])
    if is_deputy:
        buttons.append([InlineKeyboardButton(text="📜 Панель Депутата", callback_key="menu_duma")])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=b.text, callback_data=b.callback_key) for b in row] for row in buttons
    ])

@router.message(Command("start"))
async def cmd_start(message: Message, pool: asyncpg.Pool):
    user_id = message.from_user.id
    username = message.from_user.username or f"user_{user_id}"
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO subjects (user_id, username, full_name, is_citizen, reputation)
            VALUES ($1, $2, $3, TRUE, 0)
            ON CONFLICT (user_id) DO UPDATE SET username = $2
        """, user_id, username, message.from_user.full_name)
        
        roles = await conn.fetch("SELECT role_id FROM subject_roles WHERE subject_id = $1", user_id)
        role_codes = [r['role_id'] for r in roles]
    
    is_admin = 'admin' in role_codes
    is_president = 'president' in role_codes
    is_deputy = 'deputy' in role_codes
    
    kb = get_main_keyboard(is_admin, is_president, is_deputy)
    await message.answer("Добро пожаловать в главное меню государственного бота!", reply_markup=kb)

@router.callback_query(F.data == "menu_main")
async def back_to_main(callback: CallbackQuery, pool: asyncpg.Pool):
    user_id = callback.from_user.id
    async with pool.acquire() as conn:
        roles = await conn.fetch("SELECT role_id FROM subject_roles WHERE subject_id = $1", user_id)
        role_codes = [r['role_id'] for r in roles]
    kb = get_main_keyboard('admin' in role_codes, 'president' in role_codes, 'deputy' in role_codes)
    await callback.message.edit_text("Главное меню государственного бота:", reply_markup=kb)

@router.callback_query(F.data == "menu_profile")
async def view_profile(callback: CallbackQuery, pool: asyncpg.Pool):
    user_id = callback.from_user.id
    async with pool.acquire() as conn:
        subject = await conn.fetchrow("SELECT * FROM subjects WHERE user_id = $1", user_id)
        roles = await conn.fetch("""
            SELECT r.name, r.emoji FROM roles r 
            JOIN subject_roles sr ON r.code = sr.role_id 
            WHERE sr.subject_id = $1
        """, user_id)
    
    role_str = ", ".join([f"{r['emoji']} {r['name']}" for r in roles]) if roles else "Нет ролей"
    text = (
        f"👤 *Профиль гражданина*\n\n"
        f"🆔 ID: {subject['user_id']}\n"
        f"🏷 Юзернейм: @{subject['username']}\n"
        f"📝 ФИО: {subject['full_name']}\n"
        f"🌍 Гражданство: {'Да' if subject['is_citizen'] else 'Нет'}\n"
        f"📈 Репутация: {subject['reputation']}\n"
        f"🎖 Роли: {role_str}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Изменить ФИО", callback_data="change_fio")],
        [InlineKeyboardButton(text="Назад в меню", callback_data="menu_main")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")

@router.callback_query(F.data == "change_fio")
async def change_fio_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.change_fio)
    await callback.message.edit_text("Введите ваше новое ФИО:")

@router.message(Form.change_fio)
async def change_fio_process(message: Message, state: FSMContext, pool: asyncpg.Pool):
    new_fio = message.text
    user_id = message.from_user.id
async with pool.acquire() as conn:
await conn.execute("UPDATE subjects SET full_name = $1 WHERE user_id = $2", new_fio, user_id)
await state.clear()
kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="В профиль", callback_data="menu_profile")]])
await message.answer("Ваше ФИО успешно обновлено!", reply_markup=kb)
@router.callback_query(F.data == "menu_vote")
async def view_votes(callback: CallbackQuery, pool: asyncpg.Pool):
kb = InlineKeyboardMarkup(inline_keyboard=[
[InlineKeyboardButton(text="Выборы Президента", callback_data="vote_president")],
[InlineKeyboardButton(text="Выборы в ГосДуму", callback_data="vote_duma")],
[InlineKeyboardButton(text="Назад", callback_data="menu_main")]
])
await callback.message.edit_text("Выберите активные выборы для голосования:", reply_markup=kb)
@router.callback_query(F.data == "vote_president")
async def vote_president_menu(callback: CallbackQuery, pool: asyncpg.Pool):
user_id = callback.from_user.id
async with pool.acquire() as conn:
voted = await conn.fetchrow("SELECT id FROM votes WHERE user_id = $1", user_id)
if voted:
await callback.answer("Вы уже отдали свой голос на выборах Президента!", show_alert=True)
return
buttons = []
for cid, info in CANDIDATES.items():
buttons.append([InlineKeyboardButton(text=info["name"], callback_data=f"cast_pres_{cid}")])
buttons.append([InlineKeyboardButton(text="Назад", callback_data="menu_vote")])
await callback.message.edit_text("Выберите кандидата на пост Президента:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
@router.callback_query(F.data.startswith("cast_pres_"))
async def cast_president_vote(callback: CallbackQuery, pool: asyncpg.Pool):
cid = int(callback.data.split(""))
user_id = callback.from_user.id
username = callback.from_user.username or f"user{user_id}"
async with pool.acquire() as conn:
subject = await conn.fetchrow("SELECT full_name FROM subjects WHERE user_id = $1", user_id)
await conn.execute("""
INSERT INTO votes (user_id, username, voter_name, candidate_id)
VALUES ($1, $2, $3, $4)
""", user_id, username, subject['full_name'], cid)
await callback.message.delete()
await callback.message.answer_video(
video="BAACAgIAAxkBAANLasIfw2IcWeZwXgiPqm4Ne1fHeRAAAsapAAKmCxFKxM0YkvpfMeA9BA",
caption="Ваш голос за Президента принят!"
)
@router.callback_query(F.data == "vote_duma")
async def vote_duma_menu(callback: CallbackQuery, pool: asyncpg.Pool):
username = callback.from_user.username
async with pool.acquire() as conn:
election = await conn.fetchrow("SELECT id FROM duma_elections WHERE status = 'active'")
if not election:
await callback.answer("В данный момент выборы в ГосДуму не проводятся.", show_alert=True)
return
is_leader = await conn.fetchrow("SELECT name FROM parties WHERE leader_username = $1", username)
if is_leader:
await callback.answer("Лидеры партий не имеют права голосовать на выборах!", show_alert=True)
return
voted = await conn.fetchrow("SELECT id FROM duma_votes WHERE election_id = $1 AND voter_username = $2", election['id'], username)
if voted:
await callback.answer("Вы уже проголосовали на этих выборах в ГосДуму!", show_alert=True)
return
parties = await conn.fetch("""
SELECT DISTINCT p.name, p.emoji FROM parties p
JOIN party_lists pl ON p.name = pl.party_id
WHERE pl.election_id = $1 AND p.status = 'approved'
""", election['id'])
if not parties:
await callback.answer("Нет партий со сформированными списками для голосования.", show_alert=True)
return
buttons = [[InlineKeyboardButton(text=f"{p['emoji']} {p['name']}", callback_data=f"cast_duma_{p['name']}")] for p in parties]
buttons.append([InlineKeyboardButton(text="Назад", callback_data="menu_vote")])
await callback.message.edit_text("Выберите партию для голосования в Государственную Думу:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
@router.callback_query(F.data.startswith("cast_duma_"))
async def cast_duma_vote(callback: CallbackQuery, pool: asyncpg.Pool):
party_name = callback.data.replace("cast_duma_", "")
username = callback.from_user.username or f"user_{callback.from_user.id}"
async with pool.acquire() as conn:
election = await conn.fetchrow("SELECT id FROM duma_elections WHERE status = 'active'")
if not election:
await callback.answer("Выборы уже завершились.", show_alert=True)
return
await conn.execute("""
INSERT INTO duma_votes (election_id, voter_username, party_id)
VALUES ($1, $2, $3)
""", election['id'], username, party_name)
await callback.message.delete()
await callback.message.answer_video(
video="BAACAgIAAxkBAANLasIfw2IcWeZwXgiPqm4Ne1fHeRAAAsapAAKmCxFKxM0YkvpfMeA9BA",
caption="Ваш голос на выборах в Государственную Думу успешно учтен!"
)
@router.callback_query(F.data == "menu_parties")
async def menu_parties_view(callback: CallbackQuery, pool: asyncpg.Pool):
async with pool.acquire() as conn:
party_rows = await conn.fetch("SELECT * FROM parties WHERE status = 'approved'")
text = "🎉 Список зарегистрированных партий:\n\n"
if not party_rows:
text += "На данный момент нет зарегистрированных партий."
for p in party_rows:
text += f"{p['emoji']} {p['name']}\n📝 {p['description']}\n👑 Лидер: @{p['leader_username']}\n\n"
kb = InlineKeyboardMarkup(inline_keyboard=[
[InlineKeyboardButton(text="Создать партию (Заявка)", callback_data="party_create_app")],
[InlineKeyboardButton(text="Подать заявку в партию", callback_data="party_join_app")],
[InlineKeyboardButton(text="Назад", callback_data="menu_main")]
])
await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
@router.callback_query(F.data == "party_create_app")
async def party_create_start(callback: CallbackQuery, state: FSMContext):
await state.set_state(Form.create_party)
await callback.message.edit_text("Введите название, эмодзи и описание партии в формате:\nНазвание | Эмодзи | Описание")
@router.message(Form.create_party)
async def party_create_process(message: Message, state: FSMContext, pool: asyncpg.Pool):
try:
parts = message.text.split("|")
name, emoji, desc = parts[0].strip(), parts[1].strip(), parts.strip()
except Exception:
await message.answer("Неверный формат. Попробуйте еще раз в формате: Название | Эмодзи | Описание")
return
username = message.from_user.username
data_json = json.dumps({"name": name, "emoji": emoji, "description": desc})
async with pool.acquire() as conn:
await conn.execute("""
INSERT INTO applications (type, author_username, data, status)
VALUES ('party_creation', $1, $2, 'pending')
""", username, data_json)
await state.clear()
await message.answer("Ваша заявка на создание партии отправлена на рассмотрение Президенту.")
@router.callback_query(F.data == "party_join_app")
async def party_join_start(callback: CallbackQuery, state: FSMContext, pool: asyncpg.Pool):
async with pool.acquire() as conn:
parties = await conn.fetch("SELECT name FROM parties WHERE status = 'approved'")
if not parties:
await callback.answer("Нет доступных партий для вступления.", show_alert=True)
return
await state.set_state(Form.join_party)
buttons = [[InlineKeyboardButton(text=p['name'], callback_data=f"select_party_{p['name']}")] for p in parties]
await callback.message.edit_text("Выберите партию, в которую хотите отправить заявку:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
@router.callback_query(Form.join_party, F.data.startswith("select_party_"))
async def party_join_process(callback: CallbackQuery, state: FSMContext, pool: asyncpg.Pool):
party_name = callback.data.replace("select_party_", "")
username = callback.from_user.username
data_json = json.dumps({"party_name": party_name})
async with pool.acquire() as conn:
await conn.execute("""
INSERT INTO applications (type, author_username, data, status)
VALUES ('party_join', $1, $2, 'pending')
""", username, data_json)
await state.clear()
await callback.message.edit_text(f"Заявка на вступление в партию {party_name} отправлена её лидеру.")
@router.callback_query(F.data == "menu_docs")
async def menu_docs_view(callback: CallbackQuery, pool: asyncpg.Pool):
async with pool.acquire() as conn:
laws_list = await conn.fetch("SELECT * FROM laws WHERE status = 'passed'")
text = "📄 Государственные Документы\n\n"
text += "📜 Конституция: Основной закон государства. Все граждане обязаны соблюдать установленный правопорядок.\n\n"
text += "⚖ Принятые Законы:\n"
if not laws_list:
text += "Принятых законов пока нет."
for l in laws_list:
text += f"🔹 {l['title']}\n{l['description']}\n(За: {l['duma_votes_for']}, Против: {l['duma_votes_against']})\n\n"
kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data="menu_main")]])
await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
@router.callback_query(F.data == "menu_news")
async def menu_news_view(callback: CallbackQuery, pool: asyncpg.Pool):
async with pool.acquire() as conn:
feed = await conn.fetch("SELECT text, created_at FROM news ORDER BY created_at DESC LIMIT 10")
text = "📰 Газета «Зе Туниянцы Ньюс»\n\n"
if not feed:
text += "Свежих новостей пока нет."
for n in feed:
date_str = n['created_at'].strftime("%Y-%m-%d %H:%M")
text += f"⏱ [{date_str}]\n{n['text']}\n\n"
kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data="menu_main")]])
await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
@router.callback_query(F.data == "menu_settings")
async def menu_settings_view(callback: CallbackQuery):
kb = InlineKeyboardMarkup(inline_keyboard=[
[InlineKeyboardButton(text="Изменить ФИО", callback_data="change_fio")],
[InlineKeyboardButton(text="Назад", callback_data="menu_main")]
])
await callback.message.edit_text("⚙ Настройки\n\nЗдесь вы можете изменить свои персональные данные.", reply_markup=kb, parse_mode="Markdown")
@router.callback_query(F.data == "menu_help")
async def menu_help_view(callback: CallbackQuery):
text = (
"❓ Справка по системе\n\n"
"Данный бот является полноценной платформой государственного управления.\n"
"Вы можете участвовать в выборах, вступать в политические партии, просматривать нормативно-правовые акты и читать свежую прессу.\n"
"При возникновении проблем обращайтесь к Администрации."
)
kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data="menu_main")]])
await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")

```python
# === ЧАСТЬ 2 ===

# --- ПАНЕЛЬ АДМИНИСТРАТОРА ---
@router.callback_query(F.data == "menu_admin")
async def menu_admin_panel(callback: CallbackQuery, pool: asyncpg.Pool):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Доступ запрещен!", show_alert=True)
        return
    async with pool.acquire() as conn:
        session = await conn.fetchrow("SELECT is_active FROM admin_sessions WHERE user_id = $1", ADMIN_ID)
        is_active = session['is_active'] if session else False
    
    status_str = "🟢 АКТИВНА" if is_active else "🔴 ДЕАКТИВИРОВАНА"
    text = f"👑 *Панель Администратора*\nСтатус панели: {status_str}\n\nВыберите раздел для управления:"
    
    buttons = [
        [InlineKeyboardButton(text="Переключить статус панели", callback_data="admin_toggle")],
    ]
    if is_active:
        buttons.extend([
            [InlineKeyboardButton(text="👥 Субъекты", callback_data="admin_subjects"),
             InlineKeyboardButton(text="🎉 Партии", callback_data="admin_parties")],
            [InlineKeyboardButton(text="📨 Заявки", callback_data="admin_apps"),
             InlineKeyboardButton(text="⚖ Законы", callback_data="admin_laws")],
            [InlineKeyboardButton(text="📜 Указы", callback_data="admin_decrees"),
             InlineKeyboardButton(text="📰 Рассылка новостей", callback_data="admin_news")],
            [InlineKeyboardButton(text="🏛 ГосДума (Старт/Стоп)", callback_data="admin_duma_toggle"),
             InlineKeyboardButton(text="❌ Снять Президента", callback_data="admin_strip_president")]
        ])
    buttons.append([InlineKeyboardButton(text="Назад в главное меню", callback_data="menu_main")])
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="Markdown")

@router.callback_query(F.data == "admin_toggle")
async def admin_toggle_status(callback: CallbackQuery, pool: asyncpg.Pool):
    if callback.from_user.id != ADMIN_ID: return
    async with pool.acquire() as conn:
        session = await conn.fetchrow("SELECT is_active FROM admin_sessions WHERE user_id = $1", ADMIN_ID)
        new_status = not session['is_active'] if session else True
        await conn.execute("""
            INSERT INTO admin_sessions (user_id, is_active) VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE SET is_active = $2
        """, ADMIN_ID, new_status)
    await callback.answer(f"Панель {'активирована' if new_status else 'деактивирована'}")
    await menu_admin_panel(callback, pool)

@router.callback_query(F.data == "admin_subjects")
async def admin_subjects_view(callback: CallbackQuery, pool: asyncpg.Pool):
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id, username, full_name, reputation FROM subjects LIMIT 20")
    text = "👥 *Список субъектов (до 20):*\n\n"
    for r in rows:
        text += f"▪ {r['full_name']} (@{r['username']}) | Репутация: {r['reputation']}\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[[[InlineKeyboardButton(text="Назад", callback_data="menu_admin")]]])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")

@router.callback_query(F.data == "admin_parties")
async def admin_parties_view(callback: CallbackQuery, pool: asyncpg.Pool):
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT name, leader_username, status FROM parties")
    text = "🎉 *Все зарегистрированные и ожидающие партии:*\n\n"
    for r in rows:
        text += f"▪ {r['name']} | Лидер: @{r['leader_username']} | Статус: {r['status']}\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[[[InlineKeyboardButton(text="Назад", callback_data="menu_admin")]]])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")

@router.callback_query(F.data == "admin_apps")
async def admin_apps_view(callback: CallbackQuery, pool: asyncpg.Pool):
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM applications WHERE status = 'pending'")
    text = "📨 *Очередь необработанных заявок:*\n\n"
    buttons = []
    if not rows: text += "Нет активных заявок."
    for r in rows:
        text += f"ID: {r['id']} | Тип: {r['type']} | Автор: @{r['author_username']}\n Данные: {r['data']}\n\n"
        buttons.append([
            InlineKeyboardButton(text=f"Одобрить #{r['id']}", callback_data=f"app_approve_{r['id']}"),
            InlineKeyboardButton(text=f"Отклонить #{r['id']}", callback_data=f"app_reject_{r['id']}")
        ])
    buttons.append([InlineKeyboardButton(text="Назад", callback_data="menu_admin")])
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@router.callback_query(F.data.startswith("app_approve_"))
async def admin_app_approve(callback: CallbackQuery, pool: asyncpg.Pool):
    app_id = int(callback.data.replace("app_approve_", ""))
    async with pool.acquire() as conn:
        app = await conn.fetchrow("SELECT * FROM applications WHERE id = $1", app_id)
        if not app: return
        await conn.execute("UPDATE applications SET status = 'approved' WHERE id = $1", app_id)
        data = json.loads(app['data'])
        
        author = await conn.fetchrow("SELECT user_id FROM subjects WHERE username = $1", app['author_username'])
        
        if app['type'] == 'party_creation':
            await conn.execute("""
                INSERT INTO parties (name, emoji, description, leader_username, status)
                VALUES ($1, $2, $3, $4, 'approved')
            """, data['name'], data['emoji'], data['description'], app['author_username'])
        elif app['type'] == 'party_join':
            await conn.execute("""
                INSERT INTO party_members (party_id, username)
                VALUES ($1, $2)
            """, data['party_name'], app['author_username'])
            
    if author:
        try:
            await bot.send_message(author['user_id'], f"🎉 Ваша заявка #{app_id} на '{app['type']}' была успешно одобрена!")
        except Exception: pass
    await callback.answer("Заявка одобрена!")
    await admin_apps_view(callback, pool)

@router.callback_query(F.data.startswith("app_reject_"))
async def admin_app_reject(callback: CallbackQuery, pool: asyncpg.Pool):
    app_id = int(callback.data.replace("app_reject_", ""))
    async with pool.acquire() as conn:
        app = await conn.fetchrow("SELECT * FROM applications WHERE id = $1", app_id)
        if not app: return
        await conn.execute("UPDATE applications SET status = 'rejected' WHERE id = $1", app_id)
        author = await conn.fetchrow("SELECT user_id FROM subjects WHERE username = $1", app['author_username'])
    if author:
        try:
            await bot.send_message(author['user_id'], f"❌ Ваша заявка #{app_id} на '{app['type']}' была отклонена администрацией.")
        except Exception: pass
    await callback.answer("Заявка отклонена.")
    await admin_apps_view(callback, pool)

@router.callback_query(F.data == "admin_laws")
async def admin_laws_view(callback: CallbackQuery, pool: asyncpg.Pool):
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, title, status FROM laws")
    text = "⚖ *Все законопроекты:*\n\n"
    for r in rows:
        text += f"ID: {r['id']} | {r['title']} | Статус: {r['status']}\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[[[InlineKeyboardButton(text="Назад", callback_data="menu_admin")]]])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")

@router.callback_query(F.data == "admin_decrees")
async def admin_decrees_view(callback: CallbackQuery, pool: asyncpg.Pool):
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, title, is_secret FROM decrees")
    text = "📜 *Выпущенные Указы:*\n\n"
    for r in rows:
        secret_str = "🔒 Секретный" if r['is_secret'] else "🔓 Публичный"
        text += f"ID: {r['id']} | {r['title']} | {secret_str}\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[[[InlineKeyboardButton(text="Назад", callback_data="menu_admin")]]])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")

@router.callback_query(F.data == "admin_news")
async def admin_news_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.broadcast_news)
    await callback.message.edit_text("Введите текст новости для публикации в газету и рассылки всем пользователям:")

@router.message(Form.broadcast_news)
async def admin_news_process(message: Message, state: FSMContext, pool: asyncpg.Pool):
    text = message.text
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO news (text) VALUES ($1)", text)
        users = await conn.fetch("SELECT user_id FROM subjects")
    await state.clear()
    await message.answer("Новость опубликована. Начинаю рассылку...")
    for u in users:
        try:
            await bot.send_message(u['user_id'], f"📰 *СВЕЖИЙ ВЫПУСК ГАЗЕТЫ:*\n\n{text}", parse_mode="Markdown")
        except Exception: pass

@router.callback_query(F.data == "admin_duma_toggle")
async def admin_duma_toggle(callback: CallbackQuery, pool: asyncpg.Pool):
    async with pool.acquire() as conn:
        active_election = await conn.fetchrow("SELECT id FROM duma_elections WHERE status = 'active'")
        if active_election:
            await conn.execute("UPDATE duma_elections SET status = 'closed' WHERE id = $1", active_election['id'])
            
            winner = await conn.fetchrow("""
                SELECT party_id, COUNT(id) as votes_count FROM duma_votes 
                WHERE election_id = $1 GROUP BY party_id ORDER BY votes_count DESC LIMIT 1
            """, active_election['id'])
            
            if winner:
                party_list_members = await conn.fetch("SELECT username FROM party_lists WHERE party_id = $1 AND election_id = $2", winner['party_id'], active_election['id'])
                await conn.execute("DELETE FROM subject_roles WHERE role_id = 'deputy'")
for m in party_list_members:
user = await conn.fetchrow("SELECT user_id FROM subjects WHERE username = $1", m['username'])
if user:
await conn.execute("INSERT INTO subject_roles (subject_id, role_id) VALUES ($1, 'deputy') ON CONFLICT DO NOTHING", user['user_id'])
try: await bot.send_message(user['user_id'], "🎖 Вы были официально назначены Депутатом Государственной Думы по партийным спискам!")
except Exception: pass
msg = f"Выборы завершены. Победила партия {winner['party_id']}. Списки назначены депутатами."
else:
msg = "Выборы завершены, голосов нет. Депутаты не назначены."
else:
await conn.execute("INSERT INTO duma_elections (ends_at, status) VALUES (CURRENT_TIMESTAMP + INTERVAL '1 day', 'active')")
all_parties = await conn.fetch("SELECT name, leader_username FROM parties WHERE status = 'approved'")
for p in all_parties:
has_list = await conn.fetchrow("SELECT id FROM party_lists WHERE party_id = $1", p['name'])
if not has_list:
leader = await conn.fetchrow("SELECT user_id, reputation FROM subjects WHERE username = $1", p['leader_username'])
if leader:
await conn.execute("UPDATE subjects SET reputation = reputation - 10 WHERE user_id = $1", leader['user_id'])
try: await bot.send_message(leader['user_id'], "⚠ Ваша партия не сформировала списки! Вы оштрафованы на 10 единиц репутации.")
except Exception: pass
msg = "Новые выборы в Государственную Думу объявлены и успешно запущены!"
await callback.answer(msg, show_alert=True)
await menu_admin_panel(callback, pool)
@router.callback_query(F.data == "admin_strip_president")
async def admin_strip_president(callback: CallbackQuery, pool: asyncpg.Pool):
async with pool.acquire() as conn:
presidents = await conn.fetch("SELECT subject_id FROM subject_roles WHERE role_id = 'president'")
await conn.execute("DELETE FROM subject_roles WHERE role_id = 'president'")
for p in presidents:
try: await bot.send_message(p['subject_id'], "🏛 Вы были сняты с должности Президента Администратором системы.")
except Exception: pass
await callback.answer("Президент успешно отрешен от должности.")

--- ПАНЕЛЬ ПРЕЗИДЕНТА ---

@router.callback_query(F.data == "menu_president")
async def menu_president_panel(callback: CallbackQuery, pool: asyncpg.Pool):
user_id = callback.from_user.id
async with pool.acquire() as conn:
is_pres = await conn.fetchrow("SELECT role_id FROM subject_roles WHERE subject_id = $1 AND role_id = 'president'", user_id)
if not is_pres and user_id != ADMIN_ID:
await callback.answer("Вы не являетесь Президентом!", show_alert=True)
return
kb = InlineKeyboardMarkup(inline_keyboard=[
[InlineKeyboardButton(text="Издать публичный указ", callback_data="pres_decree_pub")],
[InlineKeyboardButton(text="Издать секретный указ", callback_data="pres_decree_sec")],
[InlineKeyboardButton(text="Обращение к народу", callback_data="pres_broadcast")],
[InlineKeyboardButton(text="Назначить министра", callback_data="pres_appoint_min")],
[InlineKeyboardButton(text="Назад", callback_data="menu_main")]
])
await callback.message.edit_text("🏛 Панель Президента Управления\n\nВыберите государственное действие:", reply_markup=kb, parse_mode="Markdown")
@router.callback_query(F.data == "pres_decree_pub")
async def pres_decree_pub_start(callback: CallbackQuery, state: FSMContext):
await state.set_state(Form.create_decree)
await callback.message.edit_text("Введите заголовок и текст публичного указа в формате:\nЗаголовок | Текст указа")
@router.message(Form.create_decree)
async def pres_decree_pub_process(message: Message, state: FSMContext, pool: asyncpg.Pool):
try:
title, text = message.text.split("|")[0].strip(), message.text.split("|")[1].strip()
except Exception:
await message.answer("Неверный формат. Используйте разделитель '|'.")
return
async with pool.acquire() as conn:
await conn.execute("INSERT INTO decrees (title, text, is_secret) VALUES ($1, $2, FALSE)", title, text)
await conn.execute("INSERT INTO news (text) VALUES ($1)", f"🏛 ИЗДАН УКАЗ ПРЕЗИДЕНТА: {title}\n{text}")
users = await conn.fetch("SELECT user_id FROM subjects")
await state.clear()
await message.answer("Публичный указ успешно издан и внесен в летописи.")
for u in users:
try: await bot.send_message(u['user_id'], f"🏛 Официальный Указ Президента: {title}\n\n{text}", parse_mode="Markdown")
except Exception: pass
@router.callback_query(F.data == "pres_decree_sec")
async def pres_decree_sec_start(callback: CallbackQuery, state: FSMContext):
await state.set_state(Form.secret_decree_target)
await callback.message.edit_text("Введите username получателя секретного указа (без @):")
@router.message(Form.secret_decree_target)
async def pres_decree_sec_target(message: Message, state: FSMContext):
await state.update_data(target=message.text.strip())
await state.set_state(Form.create_secret_decree)
await message.answer("Теперь введите текст секретного указа:")
@router.message(Form.create_secret_decree)
async def pres_decree_sec_process(message: Message, state: FSMContext, pool: asyncpg.Pool):
data = await state.get_data()
target_username = data['target']
text = message.text
async with pool.acquire() as conn:
await conn.execute("INSERT INTO decrees (title, text, is_secret, secret_for) VALUES ('Секретный указ', $1, TRUE, $2)", text, target_username)
target_user = await conn.fetchrow("SELECT user_id FROM subjects WHERE username = $1", target_username)
await state.clear()
await message.answer("Секретный указ успешно зарегистрирован.")
if target_user:
try: await bot.send_message(target_user['user_id'], f"🔒 Вам направлен секретный указ Президента:\n\n{text}", parse_mode="Markdown")
except Exception: pass
@router.callback_query(F.data == "pres_broadcast")
async def pres_broadcast_start(callback: CallbackQuery, state: FSMContext):
await state.set_state(Form.broadcast_president)
await callback.message.edit_text("Введите текст экстренного обращения к народу:")
@router.message(Form.broadcast_president)
async def pres_broadcast_process(message: Message, state: FSMContext, pool: asyncpg.Pool):
text = message.text
async with pool.acquire() as conn:
users = await conn.fetch("SELECT user_id FROM subjects")
await state.clear()
await message.answer("Рассылка обращения запущена.")
for u in users:
try: await bot.send_message(u['user_id'], f"📢 Экстренное обращение Президента к народу:\n\n{text}", parse_mode="Markdown")
except Exception: pass
@router.callback_query(F.data == "pres_appoint_min")
async def pres_appoint_min_start(callback: CallbackQuery, pool: asyncpg.Pool):
async with pool.acquire() as conn:
subjects = await conn.fetch("SELECT username, full_name FROM subjects LIMIT 10")
buttons = [[InlineKeyboardButton(text=s['full_name'], callback_data=f"appoint_min_{s['username']}")] for s in subjects]
buttons.append([InlineKeyboardButton(text="Назад", callback_data="menu_president")])
await callback.message.edit_text("Выберите гражданина для назначения на пост Министра:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
@router.callback_query(F.data.startswith("appoint_min_"))
async def pres_appoint_min_process(callback: CallbackQuery, pool: asyncpg.Pool):
target_username = callback.data.replace("appoint_min_", "")
async with pool.acquire() as conn:
user = await conn.fetchrow("SELECT user_id FROM subjects WHERE username = $1", target_username)
if user:
await conn.execute("INSERT INTO subject_roles (subject_id, role_id) VALUES ($1, 'minister') ON CONFLICT DO NOTHING", user['user_id'])
await callback.answer(f"Пользователь @{target_username} назначен Министром.")
if user:
try: await bot.send_message(user['user_id'], "💼 Вы были официально назначены на высокую государственную должность Министра!")
except Exception: pass

--- ПАНЕЛЬ ДЕПУТАТА ---

@router.callback_query(F.data == "menu_duma")
async def menu_duma_panel(callback: CallbackQuery, pool: asyncpg.Pool):
user_id = callback.from_user.id
async with pool.acquire() as conn:
is_dep = await conn.fetchrow("SELECT role_id FROM subject_roles WHERE subject_id = $1 AND role_id = 'deputy'", user_id)
if not is_dep and user_id != ADMIN_ID:
await callback.answer("Вы не являетесь депутатом Государственной Думы!", show_alert=True)
return
kb = InlineKeyboardMarkup(inline_keyboard=[
[InlineKeyboardButton(text="Внести новый закон", callback_data="duma_add_law")],
[InlineKeyboardButton(text="Созвать экстренное собрание", callback_data="duma_call_meeting")],
[InlineKeyboardButton(text="Назначить новые выборы Президента", callback_data="duma_start_pres_elections")],
[InlineKeyboardButton(text="Назад", callback_data="menu_main")]
])
await callback.message.edit_text("📜 Панель Депутата Государственной Думы\n\nВыберите парламентское действие:", reply_markup=kb, parse_mode="Markdown")
@router.callback_query(F.data == "duma_add_law")
async def duma_add_law_start(callback: CallbackQuery, state: FSMContext):
await state.set_state(Form.create_law)
await callback.message.edit_text("Введите заголовок и описание закона в формате:\nЗаголовок | Описание")
@router.message(Form.create_law)
async def duma_add_law_process(message: Message, state: FSMContext, pool: asyncpg.Pool):
try:
title, desc = message.text.split("|")[0].strip(), message.text.split("|")[1].strip()
except Exception:
await message.answer("Некорректный формат. Попробуйте еще раз.")
return
async with pool.acquire() as conn:
await conn.execute("INSERT INTO laws (title, description, status) VALUES ($1, $2, 'passed')", title, desc)
await state.clear()
await message.answer("Законопроект успешно рассмотрен, принят и внесен в реестр действующих законов!")
@router.callback_query(F.data == "duma_call_meeting")
async def duma_call_meeting(callback: CallbackQuery, pool: asyncpg.Pool):
async with pool.acquire() as conn:
users = await conn.fetch("SELECT user_id FROM subjects")
await callback.answer("Собрание созвано.")
for u in users:
try: await bot.send_message(u['user_id'], "🏛 Внимание! Объявлен экстренный общий сбор всех депутатов Государственной Думы в зале заседаний!")
except Exception: pass
@router.callback_query(F.data == "duma_start_pres_elections")
async def duma_start_pres_elections(callback: CallbackQuery, pool: asyncpg.Pool):
async with pool.acquire() as conn:
await conn.execute("DELETE FROM votes")
users = await conn.fetch("SELECT user_id FROM subjects")
await callback.answer("Выборы Президента инициированы.")
for u in users:
try: await bot.send_message(u['user_id'], "🗳 Внимание, Граждане! Объявлено начало официального всенародного голосования за пост Президента государства! Оставьте свой голос в меню.")
except Exception: pass

--- ЗАПУСК БОТА ---

async def main():
await init_db()
pool = await asyncpg.create_pool(DB_DSN)
await preload_data(pool)
dp["pool"] = pool
await dp.start_polling(bot)
if name == 'main':
asyncio.run(main())
