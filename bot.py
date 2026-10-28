import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone

import asyncpg
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder


BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/telegram_bot",
)
ADMIN_ID = 7934244888
VOTE_VIDEO_FILE_ID = (
    "BAACAgIAAxkBAANLasIfw2IcWeZwXgiPqm4Ne1fHeRAAAsapAAKmCxFKxM0YkvpfMeA9BA"
)
REMINDER_INTERVAL_SECONDS = 6 * 60 * 60

CANDIDATES = {
    "candidate_1": {"name": "Кандидат 1", "username": "candidate_1"},
    "candidate_2": {"name": "Кандидат 2", "username": "candidate_2"},
    "candidate_3": {"name": "Кандидат 3", "username": "candidate_3"},
}

DEFAULT_ROLES = [
    ("president", "Президент", "👑", 1),
    ("deputy", "Депутат ГосДумы", "🏛️", 20),
    ("minister", "Министр", "📌", 10),
    ("party_leader", "Лидер партии", "🎖️", 20),
    ("citizen", "Гражданин", "👤", 10000),
]
DEFAULT_SUBJECTS = [(ADMIN_ID, "admin", "Администратор", True, 100)]
DEFAULT_PARTIES = [
    ("Народная партия", "🟦", "Партия для граждан", None, "active"),
    ("Партия развития", "🟩", "Партия реформ и развития", None, "active"),
]


class Forms(StatesGroup):
    change_full_name = State()
    create_party = State()
    join_party = State()
    law_title = State()
    law_description = State()
    decree_title = State()
    decree_text = State()
    decree_secret_username = State()
    news_text = State()
    broadcast_text = State()
    minister_username = State()
    duma_duration = State()
    party_list = State()
    admin_subject_username = State()
    admin_application_id = State()
    admin_law_id = State()
    president_election_duration = State()
    remove_president_username = State()
    meeting_text = State()


def keyboard(rows):
    builder = InlineKeyboardBuilder()
    for row in rows:
        builder.row(
            *(InlineKeyboardButton(text=label, callback_data=data) for label, data in row)
        )
    return builder.as_markup()


def main_keyboard(is_admin=False, is_president=False, is_deputy=False):
    rows = [
        [("👤 Профиль", "menu_profile"), ("🗳 Голосования", "menu_vote")],
        [("🎉 Партии", "menu_parties"), ("📚 Документы", "menu_docs")],
        [("📰 Газета", "menu_news"), ("⚙️ Настройки", "menu_settings")],
        [("❓ Помощь", "menu_help")],
    ]
    if is_admin:
        rows.append([("🛠 Панель администратора", "menu_admin")])
    if is_president:
        rows.append([("👑 Панель президента", "menu_president")])
    if is_deputy:
        rows.append([("🏛 Панель депутата", "menu_duma")])
    return keyboard(rows)


async def get_subject(pool, user_id):
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM subjects WHERE user_id = $1", user_id
        )


async def get_subject_by_username(pool, username):
    username = username.strip().lstrip("@")
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM subjects WHERE lower(username) = lower($1)", username
        )


async def ensure_subject(pool, user_id, username, full_name):
    username = (username or f"id{user_id}").lstrip("@")
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO subjects (user_id, username, full_name, is_citizen, reputation)
            VALUES ($1, $2, $3, TRUE, 0)
            ON CONFLICT (user_id) DO UPDATE SET username = EXCLUDED.username
            """,
            user_id,
            username,
            full_name,
        )
        subject = await conn.fetchrow(
            "SELECT id FROM subjects WHERE user_id = $1", user_id
        )
        role = await conn.fetchrow("SELECT id FROM roles WHERE code = 'citizen'")
        if subject and role:
            await conn.execute(
                """
                INSERT INTO subject_roles (subject_id, role_id)
                VALUES ($1, $2) ON CONFLICT DO NOTHING
                """,
                subject["id"],
                role["id"],
            )


async def get_roles(pool, user_id):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT r.code
            FROM subject_roles sr
            JOIN roles r ON r.id = sr.role_id
            JOIN subjects s ON s.id = sr.subject_id
            WHERE s.user_id = $1
            """,
            user_id,
        )
    return {row["code"] for row in rows}


async def admin_active(pool, user_id):
    if user_id != ADMIN_ID:
        return False
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT is_active FROM admin_sessions WHERE user_id = $1", user_id
        )
    return bool(row and row["is_active"])


async def has_role(pool, user_id, role):
    return role in await get_roles(pool, user_id)


async def add_role(pool, username, role_code):
    subject = await get_subject_by_username(pool, username)
    if not subject:
        return False
    async with pool.acquire() as conn:
        role = await conn.fetchrow("SELECT id FROM roles WHERE code = $1", role_code)
        if not role:
            return False
        count = await conn.fetchval(
            """
            SELECT COUNT(*) FROM subject_roles sr
            WHERE sr.role_id = $1
            """,
            role["id"],
        )
        max_holders = await conn.fetchval(
            "SELECT max_holders FROM roles WHERE id = $1", role["id"]
        )
        exists = await conn.fetchval(
            "SELECT 1 FROM subject_roles WHERE subject_id = $1 AND role_id = $2",
            subject["id"],
            role["id"],
        )
        if not exists and max_holders and count >= max_holders:
            return False
        await conn.execute(
            """
            INSERT INTO subject_roles (subject_id, role_id)
            VALUES ($1, $2) ON CONFLICT DO NOTHING
            """,
            subject["id"],
            role["id"],
        )
    return True


async def remove_role(pool, username, role_code):
    subject = await get_subject_by_username(pool, username)
    if not subject:
        return
    async with pool.acquire() as conn:
        await conn.execute(
            """
            DELETE FROM subject_roles
            WHERE subject_id = $1
              AND role_id = (SELECT id FROM roles WHERE code = $2)
            """,
            subject["id"],
            role_code,
        )


async def notify_username(bot, pool, username, text):
    subject = await get_subject_by_username(pool, username)
    if not subject:
        return
    try:
        await bot.send_message(subject["user_id"], text)
    except Exception:
        logging.exception("Не удалось уведомить @%s", username)


async def broadcast(pool, bot, text):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT user_id FROM subjects WHERE is_citizen = TRUE"
        )
    sent = 0
    failed = 0
    for row in rows:
        try:
            await bot.send_message(row["user_id"], text)
            sent += 1
        except Exception:
            failed += 1
    return sent, failed


async def init_db(pool):
    statements = [
        """
        CREATE TABLE IF NOT EXISTS subjects (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT UNIQUE NOT NULL,
            username TEXT NOT NULL,
            full_name TEXT NOT NULL,
            is_citizen BOOLEAN NOT NULL DEFAULT TRUE,
            reputation INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS votes (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            username TEXT NOT NULL,
            voter_name TEXT NOT NULL,
            candidate_id TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (user_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS roles (
            id BIGSERIAL PRIMARY KEY,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            emoji TEXT NOT NULL DEFAULT '',
            max_holders INTEGER NOT NULL DEFAULT 0
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS subject_roles (
            subject_id BIGINT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
            role_id BIGINT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
            PRIMARY KEY (subject_id, role_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS parties (
            id BIGSERIAL PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            emoji TEXT NOT NULL DEFAULT '🎉',
            description TEXT NOT NULL DEFAULT '',
            leader_username TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS party_members (
            party_id BIGINT NOT NULL REFERENCES parties(id) ON DELETE CASCADE,
            username TEXT NOT NULL,
            PRIMARY KEY (party_id, username)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS applications (
            id BIGSERIAL PRIMARY KEY,
            type TEXT NOT NULL,
            author_username TEXT NOT NULL,
            data JSONB NOT NULL DEFAULT '{}'::jsonb,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            decided_at TIMESTAMPTZ
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS laws (
            id BIGSERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            duma_votes_for INTEGER NOT NULL DEFAULT 0,
            duma_votes_against INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS decrees (
            id BIGSERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            text TEXT NOT NULL,
            is_secret BOOLEAN NOT NULL DEFAULT FALSE,
            secret_for TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS news (
            id BIGSERIAL PRIMARY KEY,
            text TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS duma_elections (
            id BIGSERIAL PRIMARY KEY,
            ends_at TIMESTAMPTZ NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS duma_votes (
            id BIGSERIAL PRIMARY KEY,
            election_id BIGINT NOT NULL REFERENCES duma_elections(id) ON DELETE CASCADE,
            voter_username TEXT NOT NULL,
            party_id BIGINT NOT NULL REFERENCES parties(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (election_id, voter_username)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS party_lists (
            party_id BIGINT NOT NULL REFERENCES parties(id) ON DELETE CASCADE,
            election_id BIGINT NOT NULL REFERENCES duma_elections(id) ON DELETE CASCADE,
            username TEXT NOT NULL,
            PRIMARY KEY (party_id, election_id, username)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS admin_sessions (
            user_id BIGINT PRIMARY KEY,
            is_active BOOLEAN NOT NULL DEFAULT FALSE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS president_votes (
            election_id BIGINT NOT NULL,
            user_id BIGINT NOT NULL,
            username TEXT NOT NULL,
            candidate_id TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (election_id, user_id)
        )
        """,
    ]
    async with pool.acquire() as conn:
        async with conn.transaction():
            for statement in statements:
                await conn.execute(statement)
            # Migrate the previous schema where each user could vote only once ever.
            await conn.execute("ALTER TABLE president_votes ADD COLUMN IF NOT EXISTS election_id BIGINT")
            await conn.execute(
                """
                UPDATE president_votes
                SET election_id = COALESCE(
                    (SELECT id FROM applications WHERE type = 'president_election' ORDER BY id DESC LIMIT 1),
                    0
                )
                WHERE election_id IS NULL
                """
            )
            await conn.execute("ALTER TABLE president_votes ALTER COLUMN election_id SET NOT NULL")
            await conn.execute("ALTER TABLE president_votes DROP CONSTRAINT IF EXISTS president_votes_pkey")
            await conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS president_votes_election_user_uidx ON president_votes (election_id, user_id)"
            )
            await conn.execute(
                """
                INSERT INTO admin_sessions (user_id, is_active)
                VALUES ($1, FALSE) ON CONFLICT (user_id) DO NOTHING
                """,
                ADMIN_ID,
            )


async def preload_data(pool):
    async with pool.acquire() as conn:
        for code, name, emoji, max_holders in DEFAULT_ROLES:
            await conn.execute(
                """
                INSERT INTO roles (code, name, emoji, max_holders)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (code) DO UPDATE SET
                    name = EXCLUDED.name,
                    emoji = EXCLUDED.emoji,
                    max_holders = EXCLUDED.max_holders
                """,
                code,
                name,
                emoji,
                max_holders,
            )
        for user_id, username, full_name, is_citizen, reputation in DEFAULT_SUBJECTS:
            await conn.execute(
                """
                INSERT INTO subjects (user_id, username, full_name, is_citizen, reputation)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (user_id) DO UPDATE SET username = EXCLUDED.username
                """,
                user_id,
                username,
                full_name,
                is_citizen,
                reputation,
            )
        for name, emoji, description, leader_username, status in DEFAULT_PARTIES:
            await conn.execute(
                """
                INSERT INTO parties (name, emoji, description, leader_username, status)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (name) DO NOTHING
                """,
                name,
                emoji,
                description,
                leader_username,
                status,
            )
        subject = await conn.fetchrow(
            "SELECT id FROM subjects WHERE user_id = $1", ADMIN_ID
        )
        role = await conn.fetchrow("SELECT id FROM roles WHERE code = 'citizen'")
        if subject and role:
            await conn.execute(
                """
                INSERT INTO subject_roles (subject_id, role_id)
                VALUES ($1, $2) ON CONFLICT DO NOTHING
                """,
                subject["id"],
                role["id"],
            )


async def send_main(message, pool, user_id):
    roles = await get_roles(pool, user_id)
    await message.answer(
        "🏛 Добро пожаловать в государственный бот!\nВыберите раздел:",
        reply_markup=main_keyboard(
            await admin_active(pool, user_id),
            "president" in roles,
            "deputy" in roles,
        ),
    )


def register_handlers(dp, pool, bot):
    @dp.message(Command("start"))
    async def start_handler(message: Message, state: FSMContext):
        await state.clear()
        user = message.from_user
        if not user:
            return
        await ensure_subject(pool, user.id, user.username, user.full_name)
        await send_main(message, pool, user.id)

    @dp.message(Command("menu"))
    async def menu_command(message: Message):
        if message.from_user:
            await send_main(message, pool, message.from_user.id)

    @dp.callback_query(F.data == "menu_main")
    async def menu_main_handler(callback: CallbackQuery):
        roles = await get_roles(pool, callback.from_user.id)
        if callback.message:
            await callback.message.edit_text(
                "🏛 Главное меню",
                reply_markup=main_keyboard(
                    await admin_active(pool, callback.from_user.id),
                    "president" in roles,
                    "deputy" in roles,
                ),
            )
        await callback.answer()

    @dp.callback_query(F.data == "menu_profile")
    async def profile_handler(callback: CallbackQuery):
        subject = await get_subject(pool, callback.from_user.id)
        if not subject:
            await callback.answer("Профиль не найден. Используйте /start.", show_alert=True)
            return
        async with pool.acquire() as conn:
            role_rows = await conn.fetch(
                """
                SELECT r.name, r.emoji
                FROM subject_roles sr
                JOIN roles r ON r.id = sr.role_id
                JOIN subjects s ON s.id = sr.subject_id
                WHERE s.user_id = $1 ORDER BY r.name
                """,
                callback.from_user.id,
            )
        roles_text = ", ".join(
            f"{row['emoji']} {row['name']}" for row in role_rows
        ) or "Нет"
        text = (
            f"👤 <b>Профиль</b>\nФИО: {subject['full_name']}\n"
            f"Username: @{subject['username']}\n"
            f"Гражданин: {'Да' if subject['is_citizen'] else 'Нет'}\n"
            f"Репутация: {subject['reputation']}\nДолжности: {roles_text}"
        )
        if callback.message:
            await callback.message.edit_text(
                text,
                reply_markup=keyboard(
                    [
                        [("✏️ Изменить ФИО", "profile_change_name")],
                        [("⬅️ Назад", "menu_main")],
                    ]
                ),
            )
        await callback.answer()

    @dp.callback_query(F.data == "profile_change_name")
    async def profile_change_name(callback: CallbackQuery, state: FSMContext):
        await state.set_state(Forms.change_full_name)
        if callback.message:
            await callback.message.answer("Введите новое ФИО одним сообщением:")
        await callback.answer()

    @dp.message(Forms.change_full_name)
    async def save_full_name(message: Message, state: FSMContext):
        if not message.from_user or not message.text:
            await message.answer("Отправьте ФИО текстом.")
            return
        full_name = message.text.strip()
        if not 3 <= len(full_name) <= 150:
            await message.answer("ФИО должно содержать от 3 до 150 символов.")
            return
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE subjects SET full_name = $1 WHERE user_id = $2",
                full_name,
                message.from_user.id,
            )
        await state.clear()
        await message.answer("ФИО обновлено.")
        await send_main(message, pool, message.from_user.id)

    @dp.callback_query(F.data == "menu_settings")
    async def settings_handler(callback: CallbackQuery):
        if callback.message:
            await callback.message.edit_text(
                "⚙️ Настройки",
                reply_markup=keyboard(
                    [
                        [("✏️ Изменить ФИО", "profile_change_name")],
                        [("⬅️ Назад", "menu_main")],
                    ]
                ),
            )
        await callback.answer()

    @dp.callback_query(F.data == "menu_help")
    async def help_handler(callback: CallbackQuery):
        text = (
            "❓ <b>Помощь</b>\n"
            "/start — открыть меню\n"
            "/menu — вернуться в меню\n\n"
            "Используйте inline-кнопки для профиля, голосований, партий и документов."
        )
        if callback.message:
            await callback.message.edit_text(text, reply_markup=keyboard([[("⬅️ Назад", "menu_main")]]))
        await callback.answer()

    @dp.callback_query(F.data == "menu_vote")
    async def vote_menu(callback: CallbackQuery):
        async with pool.acquire() as conn:
            presidential = await conn.fetchrow(
                """
                SELECT id FROM applications
                WHERE type = 'president_election' AND status = 'active'
                  AND NULLIF(data->>'ends_at', '')::timestamptz > NOW()
                ORDER BY id DESC LIMIT 1
                """
            )
            duma = await conn.fetchrow(
                """
                SELECT id FROM duma_elections
                WHERE status = 'active' AND ends_at > NOW()
                ORDER BY id DESC LIMIT 1
                """
            )
        rows = []
        if presidential:
            rows.append([("🗳 Выборы Президента", "vote_president")])
        if duma:
            rows.append([("🏛 Выборы ГосДумы", "vote_duma")])
        rows.append([("⬅️ Назад", "menu_main")])
        if callback.message:
            await callback.message.edit_text(
                "🗳 Активные голосования:",
                reply_markup=keyboard(rows),
            )
        await callback.answer()

    @dp.callback_query(F.data == "vote_president")
    async def vote_president_menu(callback: CallbackQuery):
        async with pool.acquire() as conn:
            active = await conn.fetchrow(
                """
                SELECT id FROM applications
                WHERE type = 'president_election' AND status = 'active'
                  AND NULLIF(data->>'ends_at', '')::timestamptz > NOW()
                ORDER BY id DESC LIMIT 1
                """
            )
            existing = None
            if active:
                existing = await conn.fetchrow(
                    "SELECT user_id FROM president_votes WHERE election_id = $1 AND user_id = $2",
                    active["id"], callback.from_user.id,
                )
        if not active:
            await callback.answer("Сейчас нет активных выборов Президента.", show_alert=True)
            return
        if existing:
            await callback.answer("Вы уже проголосовали.", show_alert=True)
            return
        rows = [
            [(candidate["name"], f"president_candidate:{key}")]
            for key, candidate in CANDIDATES.items()
        ]
        rows.append([("⬅️ Назад", "menu_vote")])
        if callback.message:
            await callback.message.edit_text(
                "Выберите кандидата в Президенты:",
                reply_markup=keyboard(rows),
            )
        await callback.answer()

    @dp.callback_query(F.data.startswith("president_candidate:"))
    async def cast_president_vote(callback: CallbackQuery):
        candidate_id = callback.data.split(":", 1)[1]
        if candidate_id not in CANDIDATES:
            await callback.answer("Неизвестный кандидат.", show_alert=True)
            return
        user = callback.from_user
        username = user.username or f"id{user.id}"
        async with pool.acquire() as conn:
            active = await conn.fetchrow(
                """
                SELECT id FROM applications
                WHERE type = 'president_election' AND status = 'active'
                  AND NULLIF(data->>'ends_at', '')::timestamptz > NOW()
                ORDER BY id DESC LIMIT 1
                """
            )
            if not active:
                await callback.answer("Выборы уже завершены.", show_alert=True)
                return
            try:
                await conn.execute(
                    """
                    INSERT INTO president_votes (election_id, user_id, username, candidate_id)
                    VALUES ($1, $2, $3, $4)
                    """,
                    active["id"],
                    user.id,
                    username,
                    candidate_id,
                )
                subject = await conn.fetchrow(
                    "SELECT full_name FROM subjects WHERE user_id = $1", user.id
                )
                await conn.execute(
                    """
                    INSERT INTO votes (user_id, username, voter_name, candidate_id)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (user_id) DO UPDATE SET
                        username = EXCLUDED.username,
                        voter_name = EXCLUDED.voter_name,
                        candidate_id = EXCLUDED.candidate_id
                    """,
                    user.id,
                    username,
                    subject["full_name"] if subject else user.full_name,
                    candidate_id,
                )
            except asyncpg.UniqueViolationError:
                await callback.answer("Вы уже проголосовали.", show_alert=True)
                return
        if callback.message:
            try:
                await callback.message.answer_video(
                    VOTE_VIDEO_FILE_ID,
                    caption="Ваш голос за кандидата в Президенты учтён.",
                )
            except Exception:
                await callback.message.answer("Ваш голос за кандидата в Президенты учтён.")
            await callback.message.answer("Спасибо за участие!", reply_markup=keyboard([[("⬅️ В меню", "menu_main")]]))
        await callback.answer()

    @dp.callback_query(F.data == "vote_duma")
    async def vote_duma_menu(callback: CallbackQuery):
        username = (callback.from_user.username or f"id{callback.from_user.id}").lstrip("@")
        async with pool.acquire() as conn:
            election = await conn.fetchrow(
                """
                SELECT id FROM duma_elections
                WHERE status = 'active' AND ends_at > NOW()
                ORDER BY id DESC LIMIT 1
                """
            )
            is_leader = await conn.fetchval(
                "SELECT 1 FROM parties WHERE lower(leader_username) = lower($1) AND status = 'active' LIMIT 1",
                username,
            )
            existing = None
            if election:
                existing = await conn.fetchrow(
                    "SELECT id FROM duma_votes WHERE election_id = $1 AND lower(voter_username) = lower($2)",
                    election["id"],
                    username,
                )
            parties = await conn.fetch(
                """
                SELECT p.id, p.name, p.emoji
                FROM parties p
                WHERE p.status = 'active'
                  AND EXISTS (
                    SELECT 1 FROM party_lists pl
                    WHERE pl.party_id = p.id AND pl.election_id = $1
                  )
                ORDER BY p.name
                """,
                election["id"] if election else 0,
            )
        if not election:
            await callback.answer("Сейчас нет активных выборов ГосДумы.", show_alert=True)
            return
        if is_leader:
            await callback.answer("Лидеры партий не могут голосовать на выборах ГосДумы.", show_alert=True)
            return
        if existing:
            await callback.answer("Вы уже проголосовали.", show_alert=True)
            return
        rows = [[(f"{p['emoji']} {p['name']}", f"duma_party:{p['id']}")] for p in parties]
        rows.append([("⬅️ Назад", "menu_vote")])
        if callback.message:
            await callback.message.edit_text(
                "Выберите партию. Голос можно отдать один раз:",
                reply_markup=keyboard(rows),
            )
        await callback.answer()

    @dp.callback_query(F.data.startswith("duma_party:"))
    async def cast_duma_vote(callback: CallbackQuery):
        try:
            party_id = int(callback.data.split(":", 1)[1])
        except ValueError:
            await callback.answer("Некорректная партия.", show_alert=True)
            return
        username = (callback.from_user.username or f"id{callback.from_user.id}").lstrip("@")
        async with pool.acquire() as conn:
            election = await conn.fetchrow(
                """
                SELECT id FROM duma_elections
                WHERE status = 'active' AND ends_at > NOW()
                ORDER BY id DESC LIMIT 1
                """
            )
            is_leader = await conn.fetchval(
                "SELECT 1 FROM parties WHERE lower(leader_username) = lower($1) AND status = 'active' LIMIT 1",
                username,
            )
            eligible = await conn.fetchval(
                """
                SELECT 1 FROM party_lists
                WHERE election_id = $1 AND party_id = $2 LIMIT 1
                """,
                election["id"] if election else 0,
                party_id,
            ) if election else None
            if not election or not eligible:
                await callback.answer("Выборы или список партии недоступны.", show_alert=True)
                return
            if is_leader:
                await callback.answer("Лидеры партий не могут голосовать.", show_alert=True)
                return
            try:
                await conn.execute(
                    """
                    INSERT INTO duma_votes (election_id, voter_username, party_id)
                    VALUES ($1, $2, $3)
                    """,
                    election["id"],
                    username,
                    party_id,
                )
            except asyncpg.UniqueViolationError:
                await callback.answer("Вы уже проголосовали.", show_alert=True)
                return
        if callback.message:
            try:
                await callback.message.answer_video(
                    VOTE_VIDEO_FILE_ID,
                    caption="Ваш голос на выборах ГосДумы учтён.",
                )
            except Exception:
                await callback.message.answer("Ваш голос на выборах ГосДумы учтён.")
            await callback.message.answer("Спасибо за участие!", reply_markup=keyboard([[("⬅️ В меню", "menu_main")]]))
        await callback.answer()

    @dp.callback_query(F.data == "menu_parties")
    async def parties_menu(callback: CallbackQuery):
        async with pool.acquire() as conn:
            parties = await conn.fetch(
                """
                SELECT p.*, COUNT(pm.username) AS members_count
                FROM parties p LEFT JOIN party_members pm ON pm.party_id = p.id
                WHERE p.status = 'active'
                GROUP BY p.id ORDER BY p.name
                """
            )
        text = "🎉 <b>Партии</b>\n\n"
        if parties:
            for party in parties:
                leader = f"@{party['leader_username']}" if party["leader_username"] else "не назначен"
                text += (
                    f"{party['emoji']} <b>{party['name']}</b>\n"
                    f"{party['description']}\nЛидер: {leader}\nУчастников: {party['members_count']}\n\n"
                )
        else:
            text += "Активных партий пока нет.\n"
        rows = [
            [("➕ Заявка на создание партии", "party_create")],
            [("🤝 Вступить в партию", "party_join")],
            [("📝 Список кандидатов", "party_list_setup")],
            [("⬅️ Назад", "menu_main")],
        ]
        if callback.message:
            await callback.message.edit_text(text, reply_markup=keyboard(rows))
        await callback.answer()

    @dp.callback_query(F.data == "party_create")
    async def party_create(callback: CallbackQuery, state: FSMContext):
        await state.set_state(Forms.create_party)
        if callback.message:
            await callback.message.answer(
                "Отправьте заявку одним сообщением в формате:\n"
                "Название | эмодзи | описание"
            )
        await callback.answer()

    @dp.message(Forms.create_party)
    async def party_create_submit(message: Message, state: FSMContext):
        if not message.from_user or not message.text:
            await message.answer("Отправьте название, эмодзи и описание текстом.")
            return
        parts = [part.strip() for part in message.text.split("|", 2)]
        if len(parts) != 3 or not parts[0] or not parts[1] or not parts[2]:
            await message.answer("Формат: Название | эмодзи | описание")
            return
        data = {"name": parts[0], "emoji": parts[1], "description": parts[2]}
        username = message.from_user.username or f"id{message.from_user.id}"
        async with pool.acquire() as conn:
            app_id = await conn.fetchval(
                """
                INSERT INTO applications (type, author_username, data, status)
                VALUES ('party_create', $1, $2::jsonb, 'pending') RETURNING id
                """,
                username,
                json.dumps(data, ensure_ascii=False),
            )
        await state.clear()
        await message.answer(f"Заявка №{app_id} отправлена администратору на рассмотрение.")
        if ADMIN_ID:
            try:
                await bot.send_message(
                    ADMIN_ID,
                    f"Новая заявка на создание партии №{app_id} от @{username}.\n"
                    f"{data['emoji']} {data['name']}\n{data['description']}",
                )
            except Exception:
                logging.exception("Не удалось уведомить администратора")

    @dp.callback_query(F.data == "party_join")
    async def party_join(callback: CallbackQuery, state: FSMContext):
        async with pool.acquire() as conn:
            parties = await conn.fetch(
                "SELECT id, name, emoji FROM parties WHERE status = 'active' ORDER BY name"
            )
        rows = [[(f"{p['emoji']} {p['name']}", f"party_join_select:{p['id']}")] for p in parties]
        rows.append([("⬅️ Назад", "menu_parties")])
        if callback.message:
            await callback.message.edit_text(
                "Выберите партию, в которую хотите вступить:",
                reply_markup=keyboard(rows),
            )
        await callback.answer()

    @dp.callback_query(F.data.startswith("party_join_select:"))
    async def party_join_select(callback: CallbackQuery, state: FSMContext):
        try:
            party_id = int(callback.data.split(":", 1)[1])
        except (ValueError, AttributeError):
            await callback.answer("Некорректный ID партии.", show_alert=True)
            return
        username = callback.from_user.username or f"id{callback.from_user.id}"
        async with pool.acquire() as conn:
            party = await conn.fetchrow(
                "SELECT id, name, leader_username FROM parties WHERE id = $1 AND status = 'active'",
                party_id,
            )
            if not party:
                await callback.answer("Партия не найдена.", show_alert=True)
                return
            app_id = await conn.fetchval(
                """
                INSERT INTO applications (type, author_username, data, status)
                VALUES ('party_join', $1, $2::jsonb, 'pending') RETURNING id
                """,
                username,
                json.dumps({"party_id": party_id, "party_name": party["name"]}, ensure_ascii=False),
            )
        if party["leader_username"]:
            await notify_username(
                bot, pool, party["leader_username"],
                f"Заявка №{app_id}: @{username} хочет вступить в вашу партию «{party['name']}». "
                f"Решение может принять администратор через панель заявок.",
            )
        try:
            await bot.send_message(
                ADMIN_ID,
                f"Заявка на вступление №{app_id}: @{username} → {party['name']}.",
            )
        except Exception:
            pass
        await callback.answer("Заявка отправлена.", show_alert=True)

    @dp.callback_query(F.data == "party_list_setup")
    async def party_list_setup(callback: CallbackQuery, state: FSMContext):
        username = callback.from_user.username or f"id{callback.from_user.id}"
        async with pool.acquire() as conn:
            party = await conn.fetchrow(
                "SELECT id, name FROM parties WHERE lower(leader_username) = lower($1) AND status = 'active'",
                username,
            )
            election = await conn.fetchrow(
                "SELECT id FROM duma_elections WHERE status = 'active' AND ends_at > NOW() ORDER BY id DESC LIMIT 1"
            )
        if not party:
            await callback.answer("Только лидер партии может подать список.", show_alert=True)
            return
        if not election:
            await callback.answer("Нет активных выборов ГосДумы.", show_alert=True)
            return
        await state.set_state(Forms.party_list)
        await state.update_data(party_id=party["id"], election_id=election["id"])
        if callback.message:
            await callback.message.answer(
                f"Введите ровно 3 username через пробел для списка партии «{party['name']}».\n"
                "Лидер должен проверить, что каждый кандидат зарегистрирован в боте."
            )
        await callback.answer()

    @dp.message(Forms.party_list)
    async def save_party_list(message: Message, state: FSMContext):
        if not message.text:
            await message.answer("Введите три username текстом.")
            return
        usernames = [item.strip().lstrip("@") for item in message.text.split()]
        if len(usernames) != 3 or len(set(map(str.lower, usernames))) != 3:
            await message.answer("Нужно указать ровно три разных username через пробел.")
            return
        data = await state.get_data()
        async with pool.acquire() as conn:
            existing = await conn.fetchval(
                "SELECT COUNT(*) FROM subjects WHERE lower(username) = ANY($1::text[])",
                [name.lower() for name in usernames],
            )
            if existing != 3:
                await message.answer("Все три кандидата должны сначала открыть бота командой /start.")
                return
            await conn.execute(
                "DELETE FROM party_lists WHERE party_id = $1 AND election_id = $2",
                data["party_id"], data["election_id"],
            )
            for username in usernames:
                await conn.execute(
                    """
                    INSERT INTO party_lists (party_id, election_id, username)
                    VALUES ($1, $2, $3) ON CONFLICT DO NOTHING
                    """,
                    data["party_id"], data["election_id"], username,
                )
        await state.clear()
        await message.answer("Список из трёх кандидатов сохранён.")

    @dp.callback_query(F.data == "menu_docs")
    async def docs_menu(callback: CallbackQuery):
        if callback.message:
            await callback.message.edit_text(
                "📚 Документы",
                reply_markup=keyboard([
                    [("📜 Конституция", "docs_constitution")],
                    [("⚖️ Законы", "docs_laws")],
                    [("⬅️ Назад", "menu_main")],
                ]),
            )
        await callback.answer()

    @dp.callback_query(F.data == "docs_constitution")
    async def constitution(callback: CallbackQuery):
        text = (
            "📜 <b>Конституция</b>\n"
            "1. Все зарегистрированные участники являются субъектами государства.\n"
            "2. Президент и ГосДума действуют в рамках полномочий, назначенных в боте.\n"
            "3. Голос каждого участника учитывается согласно правилам соответствующих выборов.\n"
            "4. Решения и законы публикуются в разделе документов."
        )
        if callback.message:
            await callback.message.edit_text(text, reply_markup=keyboard([[("⬅️ Назад", "menu_docs")]]))
        await callback.answer()

    @dp.callback_query(F.data == "docs_laws")
    async def laws_menu(callback: CallbackQuery):
        async with pool.acquire() as conn:
            laws = await conn.fetch(
                "SELECT title, description, status FROM laws ORDER BY id DESC LIMIT 30"
            )
        text = "⚖️ <b>Законы</b>\n\n"
        if not laws:
            text += "Законов пока нет."
        else:
            for law in laws:
                text += f"<b>{law['title']}</b> — {law['status']}\n{law['description']}\n\n"
        if callback.message:
            await callback.message.edit_text(text, reply_markup=keyboard([[("⬅️ Назад", "menu_docs")]]))
        await callback.answer()

    @dp.callback_query(F.data == "menu_news")
    async def news_menu(callback: CallbackQuery):
        async with pool.acquire() as conn:
            news = await conn.fetch("SELECT text, created_at FROM news ORDER BY id DESC LIMIT 10")
            decrees = await conn.fetch(
                "SELECT title, text, created_at FROM decrees WHERE is_secret = FALSE ORDER BY id DESC LIMIT 10"
            )
        text = "📰 <b>Газета «Зе Туниянцы Ньюс»</b>\n\n"
        if not news and not decrees:
            text += "Публикаций пока нет."
        for item in news:
            text += f"🗞 {item['text']}\n\n"
        for decree in decrees:
            text += f"📜 <b>{decree['title']}</b>\n{decree['text']}\n\n"
        if callback.message:
            await callback.message.edit_text(text, reply_markup=keyboard([[("⬅️ Назад", "menu_main")]]))
        await callback.answer()

    @dp.callback_query(F.data == "menu_admin")
    async def admin_menu(callback: CallbackQuery):
        if not await admin_active(pool, callback.from_user.id):
            await callback.answer("Панель администратора выключена или доступ запрещён.", show_alert=True)
            return
        if callback.message:
            await callback.message.edit_text(
                "🛠 <b>Панель администратора</b>",
                reply_markup=keyboard([
                    [("🔛 Включить/выключить панель", "admin_toggle")],
                    [("👥 Субъекты", "admin_subjects"), ("🎉 Партии", "admin_parties")],
                    [("📨 Заявки", "admin_applications")],
                    [("⚖️ Законы", "admin_laws"), ("📜 Указы", "admin_decrees")],
                    [("📰 Новости / рассылка", "admin_news")],
                    [("🏛 ГосДума", "admin_duma")],
                    [("🚫 Снять Президента", "admin_remove_president")],
                    [("⬅️ Назад", "menu_main")],
                ]),
            )
        await callback.answer()

    @dp.callback_query(F.data == "admin_toggle")
    async def admin_toggle(callback: CallbackQuery):
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("Доступ запрещён.", show_alert=True)
            return
        async with pool.acquire() as conn:
            current = await conn.fetchval(
                "SELECT is_active FROM admin_sessions WHERE user_id = $1", ADMIN_ID
            )
            new_value = not bool(current)
            await conn.execute(
                "UPDATE admin_sessions SET is_active = $1 WHERE user_id = $2",
                new_value, ADMIN_ID,
            )
        if callback.message:
            await callback.message.answer(
                "Панель администратора включена." if new_value else
                "Панель администратора выключена. Для повторного включения используйте /admin_on."
            )
        await callback.answer()

    @dp.message(Command("admin_on"))
    async def admin_on(message: Message):
        if message.from_user and message.from_user.id == ADMIN_ID:
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO admin_sessions (user_id, is_active) VALUES ($1, TRUE)
                    ON CONFLICT (user_id) DO UPDATE SET is_active = TRUE
                    """,
                    ADMIN_ID,
                )
            await message.answer("Панель администратора включена.")
        else:
            await message.answer("Доступ запрещён.")

    @dp.callback_query(F.data == "admin_subjects")
    async def admin_subjects(callback: CallbackQuery, state: FSMContext):
        if not await admin_active(pool, callback.from_user.id):
            await callback.answer("Доступ запрещён.", show_alert=True)
            return
        async with pool.acquire() as conn:
            subjects = await conn.fetch(
                "SELECT username, full_name, reputation, is_citizen FROM subjects ORDER BY id DESC LIMIT 30"
            )
        text = "👥 <b>Субъекты</b>\n"
        for subject in subjects:
            text += (
                f"\n@{subject['username']} — {subject['full_name']}; "
                f"репутация {subject['reputation']}; "
                f"гражданин: {'да' if subject['is_citizen'] else 'нет'}"
            )
        text += "\n\nДля назначения министра/депутата/лидера партии нажмите «Назначить роль»."
        if callback.message:
            await callback.message.edit_text(
                text,
                reply_markup=keyboard([
                    [("🎖 Назначить роль", "admin_assign_role")],
                    [("⬅️ Назад", "menu_admin")],
                ]),
            )
        await callback.answer()

    @dp.callback_query(F.data == "admin_assign_role")
    async def admin_assign_role(callback: CallbackQuery, state: FSMContext):
        if not await admin_active(pool, callback.from_user.id):
            await callback.answer("Доступ запрещён.", show_alert=True)
            return
        await state.set_state(Forms.admin_subject_username)
        await state.update_data(action="assign_role")
        if callback.message:
            await callback.message.answer(
                "Введите username пользователя, затем роль отдельным сообщением.\n"
                "Роли: president, deputy, minister, party_leader, citizen."
            )
        await callback.answer()

    @dp.message(Forms.admin_subject_username)
    async def admin_subject_username(message: Message, state: FSMContext):
        if not message.from_user or message.from_user.id != ADMIN_ID or not await admin_active(pool, ADMIN_ID):
            await state.clear()
            await message.answer("Доступ запрещён.")
            return
        if not message.text:
            await message.answer("Введите username текстом.")
            return
        username = message.text.strip().lstrip("@")
        subject = await get_subject_by_username(pool, username)
        if not subject:
            await message.answer("Пользователь не найден. Он должен открыть бота командой /start.")
            return
        await state.update_data(target_username=username)
        await state.set_state(None)
        await message.answer(
            "Введите код роли: president, deputy, minister, party_leader или citizen."
        )
        await state.set_state(Forms.admin_application_id)
        await state.update_data(admin_action="assign_role")

    @dp.message(Forms.admin_application_id)
    async def admin_application_id_input(message: Message, state: FSMContext):
        if not message.from_user or message.from_user.id != ADMIN_ID or not await admin_active(pool, ADMIN_ID):
            await state.clear()
            await message.answer("Доступ запрещён.")
            return
        data = await state.get_data()
        if data.get("admin_action") == "assign_role":
            role_code = (message.text or "").strip()
            username = data.get("target_username")
            valid_roles = {item[0] for item in DEFAULT_ROLES}
            if role_code not in valid_roles:
                await message.answer("Неизвестная роль. Допустимо: president, deputy, minister, party_leader, citizen.")
                return
            if not await add_role(pool, username, role_code):
                await message.answer("Не удалось назначить роль: субъект не найден или лимит должности достигнут.")
                await state.clear()
                return
            await state.clear()
            await notify_username(bot, pool, username, f"Вам назначена роль: {role_code}.")
            await message.answer(f"Роль {role_code} назначена пользователю @{username}.")
            return
        try:
            app_id = int((message.text or "").strip())
        except ValueError:
            await message.answer("Введите числовой ID заявки.")
            return
        status = data.get("decision", "approved")
        await state.clear()
        await process_application_decision(message, app_id, status, pool, bot)

    async def process_application_decision(message, app_id, status, pool, bot):
        async with pool.acquire() as conn:
            app = await conn.fetchrow(
                "SELECT * FROM applications WHERE id = $1 AND status = 'pending'",
                app_id,
            )
            if not app:
                await message.answer("Ожидающая заявка с таким ID не найдена.")
                return
            data = app["data"]
            if isinstance(data, str):
                data = json.loads(data)
            if app["type"] == "party_create" and status == "approved":
                await conn.execute(
                    """
                    INSERT INTO parties (name, emoji, description, leader_username, status)
                    VALUES ($1, $2, $3, $4, 'active')
                    ON CONFLICT (name) DO NOTHING
                    """,
                    data["name"], data["emoji"], data["description"], app["author_username"],
                )
                await conn.execute(
                    "INSERT INTO party_members (party_id, username) SELECT id, $2 FROM parties WHERE name = $1 ON CONFLICT DO NOTHING",
                    data["name"], app["author_username"],
                )
                await conn.execute(
                    "UPDATE subjects SET reputation = reputation + 5 WHERE lower(username) = lower($1)",
                    app["author_username"],
                )
                await conn.execute(
                    "UPDATE applications SET status = $1, decided_at = NOW() WHERE id = $2",
                    status, app_id,
                )
                await conn.execute(
                    "UPDATE parties SET leader_username = $1 WHERE name = $2",
                    app["author_username"], data["name"],
                )
                await conn.execute(
                    "INSERT INTO subject_roles (subject_id, role_id) SELECT s.id, r.id FROM subjects s, roles r WHERE lower(s.username) = lower($1) AND r.code = 'party_leader' ON CONFLICT DO NOTHING",
                    app["author_username"],
                )
            elif app["type"] == "party_join" and status == "approved":
                party_id = int(data["party_id"])
                await conn.execute(
                    """
                    INSERT INTO party_members (party_id, username)
                    VALUES ($1, $2) ON CONFLICT DO NOTHING
                    """,
                    party_id, app["author_username"],
                )
                await conn.execute(
                    "UPDATE applications SET status = $1, decided_at = NOW() WHERE id = $2",
                    status, app_id,
                )
            else:
                await conn.execute(
                    "UPDATE applications SET status = $1, decided_at = NOW() WHERE id = $2",
                    status, app_id,
                )
            author = app["author_username"]
            app_type = app["type"]
        await notify_username(
            bot, pool, author,
            f"Ваша заявка №{app_id} ({app_type}) "
            f"{'одобрена' if status == 'approved' else 'отклонена'}.",
        )
        await message.answer(f"Заявка №{app_id} обработана: {status}.")

    @dp.callback_query(F.data == "admin_applications")
    async def admin_applications(callback: CallbackQuery):
        if not await admin_active(pool, callback.from_user.id):
            await callback.answer("Доступ запрещён.", show_alert=True)
            return
        async with pool.acquire() as conn:
            apps = await conn.fetch(
                "SELECT id, type, author_username, data, created_at FROM applications WHERE status = 'pending' ORDER BY id"
            )
        text = "📨 <b>Ожидающие заявки</b>\n"
        for app in apps:
            data = app["data"]
            if isinstance(data, str):
                data = json.loads(data)
            text += f"\n№{app['id']} — {app['type']} от @{app['author_username']}: {json.dumps(data, ensure_ascii=False)}"
        if not apps:
            text += "\nОжидающих заявок нет."
        if callback.message:
            await callback.message.edit_text(
                text,
                reply_markup=keyboard([
                    [("✅ Одобрить заявку", "admin_app_approve")],
                    [("❌ Отклонить заявку", "admin_app_reject")],
                    [("⬅️ Назад", "menu_admin")],
                ]),
            )
        await callback.answer()

    @dp.callback_query(F.data.in_({"admin_app_approve", "admin_app_reject"}))
    async def admin_app_decision_start(callback: CallbackQuery, state: FSMContext):
        if not await admin_active(pool, callback.from_user.id):
            await callback.answer("Доступ запрещён.", show_alert=True)
            return
        status = "approved" if callback.data == "admin_app_approve" else "rejected"
        await state.set_state(Forms.admin_application_id)
        await state.update_data(admin_action="decide_application", decision=status)
        if callback.message:
            await callback.message.answer("Введите ID заявки:")
        await callback.answer()

    @dp.callback_query(F.data == "admin_laws")
    async def admin_laws(callback: CallbackQuery):
        if not await admin_active(pool, callback.from_user.id):
            await callback.answer("Доступ запрещён.", show_alert=True)
            return
        async with pool.acquire() as conn:
            laws = await conn.fetch("SELECT id, title, status FROM laws ORDER BY id DESC LIMIT 20")
        text = "⚖️ <b>Законы</b>\n"
        for law in laws:
            text += f"\n№{law['id']} — {law['title']} ({law['status']})"
        if callback.message:
            await callback.message.edit_text(
                text,
                reply_markup=keyboard([
                    [("➕ Создать закон", "admin_law_create")],
                    [("🔄 Изменить статус закона", "admin_law_status")],
                    [("⬅️ Назад", "menu_admin")],
                ]),
            )
        await callback.answer()

    @dp.callback_query(F.data == "admin_law_create")
    async def admin_law_create(callback: CallbackQuery, state: FSMContext):
        if not await admin_active(pool, callback.from_user.id):
            await callback.answer("Доступ запрещён.", show_alert=True)
            return
        await state.set_state(Forms.law_title)
        if callback.message:
            await callback.message.answer("Введите название закона:")
        await callback.answer()

    @dp.message(Forms.law_title)
    async def law_title(message: Message, state: FSMContext):
        if not message.from_user or not message.text:
            await message.answer("Введите название закона текстом.")
            return
        if not ((message.from_user.id == ADMIN_ID and await admin_active(pool, ADMIN_ID))
                or await has_role(pool, message.from_user.id, "deputy")):
            await state.clear()
            await message.answer("Доступ запрещён.")
            return
        if not message.text or not message.text.strip():
            await message.answer("Введите название текстом.")
            return
        await state.update_data(law_title=message.text.strip())
        await state.set_state(Forms.law_description)
        await message.answer("Введите описание закона:")

    @dp.message(Forms.law_description)
    async def law_description(message: Message, state: FSMContext):
        if not message.from_user or not message.text:
            await message.answer("Введите описание закона текстом.")
            return
        if not ((message.from_user.id == ADMIN_ID and await admin_active(pool, ADMIN_ID))
                or await has_role(pool, message.from_user.id, "deputy")):
            await state.clear()
            await message.answer("Доступ запрещён.")
            return
        if not message.text or not message.text.strip():
            await message.answer("Введите описание текстом.")
            return
        data = await state.get_data()
        async with pool.acquire() as conn:
            law_id = await conn.fetchval(
                "INSERT INTO laws (title, description, status) VALUES ($1, $2, 'pending') RETURNING id",
                data["law_title"], message.text.strip(),
            )
        await state.clear()
        await message.answer(f"Закон №{law_id} создан со статусом «pending».")

    @dp.callback_query(F.data == "admin_law_status")
    async def admin_law_status(callback: CallbackQuery, state: FSMContext):
        if not await admin_active(pool, callback.from_user.id):
            await callback.answer("Доступ запрещён.", show_alert=True)
            return
        await state.set_state(Forms.admin_law_id)
        if callback.message:
            await callback.message.answer("Введите ID закона и новый статус через пробел: ID active/rejected")
        await callback.answer()

    @dp.message(Forms.admin_law_id)
    async def admin_law_status_save(message: Message, state: FSMContext):
        if not message.from_user or message.from_user.id != ADMIN_ID or not await admin_active(pool, ADMIN_ID):
            await state.clear()
            await message.answer("Доступ запрещён.")
            return
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) != 2 or parts[1] not in {"active", "rejected", "pending"}:
            await message.answer("Формат: ID active, ID rejected или ID pending.")
            return
        try:
            law_id = int(parts[0])
        except ValueError:
            await message.answer("ID должен быть числом.")
            return
        async with pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE laws SET status = $1 WHERE id = $2", parts[1], law_id
            )
        await state.clear()
        await message.answer("Статус закона обновлён." if result.endswith("1") else "Закон не найден.")

    @dp.callback_query(F.data == "admin_decrees")
    async def admin_decrees(callback: CallbackQuery):
        if not await admin_active(pool, callback.from_user.id):
            await callback.answer("Доступ запрещён.", show_alert=True)
            return
        if callback.message:
            await callback.message.edit_text(
                "📜 Указы",
                reply_markup=keyboard([
                    [("📢 Публичный указ", "decree_public")],
                    [("🔒 Секретный указ", "decree_secret")],
                    [("⬅️ Назад", "menu_admin")],
                ]),
            )
        await callback.answer()

    @dp.callback_query(F.data.in_({"decree_public", "decree_secret"}))
    async def decree_start(callback: CallbackQuery, state: FSMContext):
        if not await admin_active(pool, callback.from_user.id):
            await callback.answer("Доступ запрещён.", show_alert=True)
            return
        await state.update_data(decree_secret=callback.data == "decree_secret")
        await state.set_state(Forms.decree_title)
        if callback.message:
            await callback.message.answer("Введите заголовок указа:")
        await callback.answer()

    @dp.message(Forms.decree_title)
    async def decree_title(message: Message, state: FSMContext):
        if not message.from_user or not message.text:
            await message.answer("Введите заголовок указа текстом.")
            return
        data = await state.get_data()
        authorized = (
            message.from_user.id == ADMIN_ID and await admin_active(pool, ADMIN_ID)
        ) or (
            data.get("president_created") and await has_role(pool, message.from_user.id, "president")
        )
        if not authorized:
            await state.clear()
            await message.answer("Доступ запрещён.")
            return
        if not message.text or not message.text.strip():
            await message.answer("Введите заголовок текстом.")
            return
        await state.update_data(decree_title=message.text.strip())
        await state.set_state(Forms.decree_text)
        await message.answer("Введите полный текст указа:")

    @dp.message(Forms.decree_text)
    async def decree_text(message: Message, state: FSMContext):
        if not message.from_user or not message.text:
            await message.answer("Введите текст указа.")
            return
        data = await state.get_data()
        authorized = (
            message.from_user.id == ADMIN_ID and await admin_active(pool, ADMIN_ID)
        ) or (
            data.get("president_created") and await has_role(pool, message.from_user.id, "president")
        )
        if not authorized:
            await state.clear()
            await message.answer("Доступ запрещён.")
            return
        if not message.text or not message.text.strip():
            await message.answer("Введите текст указа.")
            return
        data = await state.get_data()
        if data.get("decree_secret"):
            await state.update_data(decree_text=message.text.strip())
            await state.set_state(Forms.decree_secret_username)
            await message.answer("Введите username единственного получателя секретного указа:")
            return
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO decrees (title, text, is_secret, secret_for) VALUES ($1, $2, FALSE, NULL)",
                data["decree_title"], message.text.strip(),
            )
        await state.clear()
        await message.answer("Публичный указ сохранён и опубликован в газете.")
        await broadcast(pool, bot, f"📜 Новый публичный указ: {data['decree_title']}\n\n{message.text.strip()}")

    @dp.message(Forms.decree_secret_username)
    async def decree_secret_username(message: Message, state: FSMContext):
        data = await state.get_data()
        is_admin = bool(
            message.from_user
            and message.from_user.id == ADMIN_ID
            and await admin_active(pool, ADMIN_ID)
        )
        is_president = bool(
            message.from_user
            and data.get("president_created")
            and await has_role(pool, message.from_user.id, "president")
        )
        if not message.from_user or not (is_admin or is_president):
            await state.clear()
            await message.answer("Доступ запрещён.")
            return
        username = (message.text or "").strip().lstrip("@")
        subject = await get_subject_by_username(pool, username)
        if not subject:
            await message.answer("Получатель не найден. Он должен открыть бота командой /start.")
            return
        data = await state.get_data()
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO decrees (title, text, is_secret, secret_for) VALUES ($1, $2, TRUE, $3)",
                data["decree_title"], data["decree_text"], username,
            )
        await state.clear()
        await bot.send_message(
            subject["user_id"],
            f"🔒 Секретный указ: {data['decree_title']}\n\n{data['decree_text']}",
        )
        await message.answer("Секретный указ сохранён и отправлен только получателю.")

    @dp.callback_query(F.data == "admin_news")
    async def admin_news(callback: CallbackQuery, state: FSMContext):
        if not await admin_active(pool, callback.from_user.id):
            await callback.answer("Доступ запрещён.", show_alert=True)
            return
        await state.set_state(Forms.news_text)
        if callback.message:
            await callback.message.answer(
                "Введите текст новости. Он будет сохранён в газете и разослан всем гражданам:"
            )
        await callback.answer()

    @dp.message(Forms.news_text)
    async def news_text(message: Message, state: FSMContext):
        if not message.from_user or message.from_user.id != ADMIN_ID or not await admin_active(pool, ADMIN_ID):
            await state.clear()
            await message.answer("Доступ запрещён.")
            return
        if not message.text or not message.text.strip():
            await message.answer("Введите текст новости.")
            return
        text = message.text.strip()
        async with pool.acquire() as conn:
            await conn.execute("INSERT INTO news (text) VALUES ($1)", text)
        sent, failed = await broadcast(pool, bot, f"📰 Зе Туниянцы Ньюс\n\n{text}")
        await state.clear()
        await message.answer(f"Новость опубликована. Доставлено: {sent}, ошибок: {failed}.")

    @dp.callback_query(F.data == "admin_duma")
    async def admin_duma(callback: CallbackQuery):
        if not await admin_active(pool, callback.from_user.id):
            await callback.answer("Доступ запрещён.", show_alert=True)
            return
        async with pool.acquire() as conn:
            election = await conn.fetchrow(
                "SELECT id, ends_at, status FROM duma_elections ORDER BY id DESC LIMIT 1"
            )
        status = (
            f"Последние выборы №{election['id']}: {election['status']}, окончание {election['ends_at']}."
            if election else "Выборы ГосДумы ещё не создавались."
        )
        if callback.message:
            await callback.message.edit_text(
                f"🏛 ГосДума\n{status}",
                reply_markup=keyboard([
                    [("▶️ Назначить выборы на 24 часа", "duma_start_election")],
                    [("⏹ Завершить выборы", "duma_end_election")],
                    [("📊 Результаты", "duma_results")],
                    [("⬅️ Назад", "menu_admin")],
                ]),
            )
        await callback.answer()

    @dp.callback_query(F.data == "duma_start_election")
    async def duma_start_election(callback: CallbackQuery):
        if not await admin_active(pool, callback.from_user.id):
            await callback.answer("Доступ запрещён.", show_alert=True)
            return
        async with pool.acquire() as conn:
            await conn.execute("UPDATE duma_elections SET status = 'closed' WHERE status = 'active'")
            election_id = await conn.fetchval(
                "INSERT INTO duma_elections (ends_at, status) VALUES ($1, 'active') RETURNING id",
                datetime.now(timezone.utc) + timedelta(hours=24),
            )
            parties = await conn.fetch("SELECT id, leader_username FROM parties WHERE status = 'active'")
            for party in parties:
                count = await conn.fetchval(
                    "SELECT COUNT(*) FROM party_lists WHERE party_id = $1 AND election_id = $2",
                    party["id"], election_id,
                )
                if count != 3 and party["leader_username"]:
                    await conn.execute(
                        """
                        UPDATE subjects SET reputation = reputation - 10
                        WHERE lower(username) = lower($1)
                        """,
                        party["leader_username"],
                    )
        if callback.message:
            await callback.message.answer(
                f"Выборы ГосДумы №{election_id} начались на 24 часа. "
                "Лидерам партий нужно сформировать список из трёх кандидатов."
            )
        await callback.answer()

    @dp.callback_query(F.data == "duma_end_election")
    async def duma_end_election(callback: CallbackQuery):
        if not await admin_active(pool, callback.from_user.id):
            await callback.answer("Доступ запрещён.", show_alert=True)
            return
        async with pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE duma_elections SET status = 'closed' WHERE status = 'active'"
            )
        if callback.message:
            await callback.message.answer("Выборы ГосДумы завершены.")
        await callback.answer()

    @dp.callback_query(F.data == "duma_results")
    async def duma_results(callback: CallbackQuery):
        if not await admin_active(pool, callback.from_user.id):
            await callback.answer("Доступ запрещён.", show_alert=True)
            return
        async with pool.acquire() as conn:
            election = await conn.fetchrow(
                "SELECT id FROM duma_elections ORDER BY id DESC LIMIT 1"
            )
            if not election:
                text = "Выборов ГосДумы ещё не было."
            else:
                rows = await conn.fetch(
                    """
                    SELECT p.name, p.emoji, COUNT(v.id) AS votes
                    FROM parties p
                    LEFT JOIN duma_votes v ON v.party_id = p.id AND v.election_id = $1
                    GROUP BY p.id ORDER BY votes DESC, p.name
                    """,
                    election["id"],
                )
                text = f"📊 Результаты выборов ГосДумы №{election['id']}\n"
                for row in rows:
                    text += f"\n{row['emoji']} {row['name']}: {row['votes']} голосов"
        if callback.message:
            await callback.message.answer(text)
        await callback.answer()

    @dp.callback_query(F.data == "admin_remove_president")
    async def admin_remove_president(callback: CallbackQuery, state: FSMContext):
        if not await admin_active(pool, callback.from_user.id):
            await callback.answer("Доступ запрещён.", show_alert=True)
            return
        await state.set_state(Forms.remove_president_username)
        if callback.message:
            await callback.message.answer("Введите username Президента, которого нужно снять:")
        await callback.answer()

    @dp.message(Forms.remove_president_username)
    async def remove_president(message: Message, state: FSMContext):
        if not message.from_user or message.from_user.id != ADMIN_ID or not await admin_active(pool, ADMIN_ID):
            await state.clear()
            await message.answer("Доступ запрещён.")
            return
        username = (message.text or "").strip().lstrip("@")
        await remove_role(pool, username, "president")
        await state.clear()
        await notify_username(bot, pool, username, "Ваша должность Президента снята администратором.")
        await message.answer(f"Роль Президента снята у @{username}.")

    @dp.callback_query(F.data == "menu_president")
    async def president_menu(callback: CallbackQuery):
        if not await has_role(pool, callback.from_user.id, "president"):
            await callback.answer("Доступ запрещён.", show_alert=True)
            return
        if callback.message:
            await callback.message.edit_text(
                "👑 Панель президента",
                reply_markup=keyboard([
                    [("📜 Публичный указ", "president_public_decree")],
                    [("🔒 Секретный указ", "president_secret_decree")],
                    [("📢 Обращение к народу", "president_broadcast")],
                    [("📌 Назначить министра", "president_minister")],
                    [("⬅️ Назад", "menu_main")],
                ]),
            )
        await callback.answer()

    @dp.callback_query(F.data.in_({"president_public_decree", "president_secret_decree"}))
    async def president_decree_start(callback: CallbackQuery, state: FSMContext):
        if not await has_role(pool, callback.from_user.id, "president"):
            await callback.answer("Доступ запрещён.", show_alert=True)
            return
        await state.update_data(decree_secret=callback.data == "president_secret_decree", president_created=True)
        await state.set_state(Forms.decree_title)
        if callback.message:
            await callback.message.answer("Введите заголовок указа:")
        await callback.answer()

    @dp.callback_query(F.data == "president_broadcast")
    async def president_broadcast(callback: CallbackQuery, state: FSMContext):
        if not await has_role(pool, callback.from_user.id, "president"):
            await callback.answer("Доступ запрещён.", show_alert=True)
            return
        await state.set_state(Forms.broadcast_text)
        if callback.message:
            await callback.message.answer("Введите текст обращения к народу:")
        await callback.answer()

    @dp.message(Forms.broadcast_text)
    async def president_broadcast_send(message: Message, state: FSMContext):
        if not message.from_user or not await has_role(pool, message.from_user.id, "president"):
            await state.clear()
            await message.answer("Доступ запрещён.")
            return
        if not message.text:
            await message.answer("Введите обращение текстом.")
            return
        sent, failed = await broadcast(pool, bot, f"📢 Обращение Президента\n\n{message.text.strip()}")
        await state.clear()
        await message.answer(f"Обращение отправлено. Доставлено: {sent}, ошибок: {failed}.")

    @dp.callback_query(F.data == "president_minister")
    async def president_minister(callback: CallbackQuery, state: FSMContext):
        if not await has_role(pool, callback.from_user.id, "president"):
            await callback.answer("Доступ запрещён.", show_alert=True)
            return
        await state.set_state(Forms.minister_username)
        if callback.message:
            await callback.message.answer("Введите username зарегистрированного пользователя:")
        await callback.answer()

    @dp.message(Forms.minister_username)
    async def president_minister_assign(message: Message, state: FSMContext):
        if not message.from_user or not await has_role(pool, message.from_user.id, "president"):
            await state.clear()
            await message.answer("Доступ запрещён.")
            return
        username = (message.text or "").strip().lstrip("@")
        if not await add_role(pool, username, "minister"):
            await message.answer("Не удалось назначить министра. Проверьте username и лимит должностей.")
            return
        await state.clear()
        await notify_username(bot, pool, username, "Президент назначил вас министром.")
        await message.answer(f"Пользователь @{username} назначен министром.")

    @dp.callback_query(F.data == "menu_duma")
    async def duma_menu(callback: CallbackQuery):
        if not await has_role(pool, callback.from_user.id, "deputy"):
            await callback.answer("Доступ запрещён.", show_alert=True)
            return
        if callback.message:
            await callback.message.edit_text(
                "🏛 Панель депутата",
                reply_markup=keyboard([
                    [("⚖️ Внести закон", "deputy_law")],
                    [("🗣 Созвать собрание", "deputy_meeting")],
                    [("🗳 Назначить выборы Президента", "deputy_president_election")],
                    [("⬅️ Назад", "menu_main")],
                ]),
            )
        await callback.answer()

    @dp.callback_query(F.data == "deputy_law")
    async def deputy_law(callback: CallbackQuery, state: FSMContext):
        if not await has_role(pool, callback.from_user.id, "deputy"):
            await callback.answer("Доступ запрещён.", show_alert=True)
            return
        await state.update_data(law_author="deputy")
        await state.set_state(Forms.law_title)
        if callback.message:
            await callback.message.answer("Введите название предлагаемого закона:")
        await callback.answer()

    @dp.callback_query(F.data == "deputy_meeting")
    async def deputy_meeting(callback: CallbackQuery, state: FSMContext):
        if not await has_role(pool, callback.from_user.id, "deputy"):
            await callback.answer("Доступ запрещён.", show_alert=True)
            return
        await state.set_state(Forms.meeting_text)
        if callback.message:
            await callback.message.answer("Введите тему и время собрания:")
        await callback.answer()

    @dp.message(Forms.meeting_text)
    async def meeting_text(message: Message, state: FSMContext):
        if not message.from_user or not await has_role(pool, message.from_user.id, "deputy"):
            await state.clear()
            await message.answer("Доступ запрещён.")
            return
        if not message.text:
            await message.answer("Введите тему текстом.")
            return
        sent, failed = await broadcast(pool, bot, f"🏛 Созвано собрание ГосДумы\n\n{message.text.strip()}")
        await state.clear()
        await message.answer(f"Уведомление отправлено. Доставлено: {sent}, ошибок: {failed}.")

    @dp.callback_query(F.data == "deputy_president_election")
    async def deputy_president_election(callback: CallbackQuery, state: FSMContext):
        if not await has_role(pool, callback.from_user.id, "deputy"):
            await callback.answer("Доступ запрещён.", show_alert=True)
            return
        await state.set_state(Forms.president_election_duration)
        if callback.message:
            await callback.message.answer("На сколько часов открыть выборы Президента? Введите число от 1 до 720:")
        await callback.answer()

    @dp.message(Forms.president_election_duration)
    async def president_election_create(message: Message, state: FSMContext):
        if not message.from_user or not await has_role(pool, message.from_user.id, "deputy"):
            await state.clear()
            await message.answer("Доступ запрещён.")
            return
        try:
            hours = int((message.text or "").strip())
        except ValueError:
            await message.answer("Введите число часов.")
            return
        if not 1 <= hours <= 720:
            await message.answer("Допустимый срок — от 1 до 720 часов.")
            return
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE applications SET status = 'closed' WHERE type = 'president_election' AND status = 'active'"
            )
            election_id = await conn.fetchval(
                """
                INSERT INTO applications (type, author_username, data, status)
                VALUES ('president_election', $1, $2::jsonb, 'active') RETURNING id
                """,
                message.from_user.username or f"id{message.from_user.id}",
                json.dumps({"ends_at": (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()}),
            )
        await state.clear()
        await message.answer(f"Выборы Президента №{election_id} открыты на {hours} ч.")
        await broadcast(pool, bot, "🗳 Начались выборы Президента. Откройте раздел «Голосования».")

    async def reminder_loop():
        while True:
            try:
                await asyncio.sleep(REMINDER_INTERVAL_SECONDS)
                async with pool.acquire() as conn:
                    election = await conn.fetchrow(
                        "SELECT id FROM duma_elections WHERE status = 'active' AND ends_at > NOW() ORDER BY id DESC LIMIT 1"
                    )
                    if not election:
                        continue
                    parties = await conn.fetch(
                        "SELECT id, name, leader_username FROM parties WHERE status = 'active' AND leader_username IS NOT NULL"
                    )
                    for party in parties:
                        count = await conn.fetchval(
                            "SELECT COUNT(*) FROM party_lists WHERE party_id = $1 AND election_id = $2",
                            party["id"], election["id"],
                        )
                        if count != 3:
                            await conn.execute(
                                """
                                UPDATE subjects SET reputation = reputation - 10
                                WHERE lower(username) = lower($1)
                                """,
                                party["leader_username"],
                            )
                            await notify_username(
                                bot, pool, party["leader_username"],
                                f"Напоминание: партия «{party['name']}» не имеет списка из трёх кандидатов "
                                "на текущие выборы ГосДумы. Репутация снижена на 10.",
                            )
            except asyncio.CancelledError:
                raise
            except Exception:
                logging.exception("Ошибка фоновой проверки списков партий")


async def main():
    logging.basicConfig(level=logging.INFO)
    if not BOT_TOKEN:
        raise RuntimeError("Установите переменную окружения BOT_TOKEN с токеном Telegram-бота.")
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)
    try:
        await init_db(pool)
        await preload_data(pool)
        bot = Bot(
            token=BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        dp = Dispatcher()
        register_handlers(dp, pool, bot)
        reminder_task = asyncio.create_task(reminder_loop_placeholder(pool, bot))
        try:
            await dp.start_polling(bot)
        finally:
            reminder_task.cancel()
            try:
                await reminder_task
            except asyncio.CancelledError:
                pass
            await bot.session.close()
    finally:
        await pool.close()


async def reminder_loop_placeholder(pool, bot):
    while True:
        try:
            await asyncio.sleep(REMINDER_INTERVAL_SECONDS)
            async with pool.acquire() as conn:
                election = await conn.fetchrow(
                    "SELECT id FROM duma_elections WHERE status = 'active' AND ends_at > NOW() ORDER BY id DESC LIMIT 1"
                )
                if not election:
                    continue
                parties = await conn.fetch(
                    "SELECT id, name, leader_username FROM parties WHERE status = 'active' AND leader_username IS NOT NULL"
                )
                for party in parties:
                    count = await conn.fetchval(
                        "SELECT COUNT(*) FROM party_lists WHERE party_id = $1 AND election_id = $2",
                        party["id"], election["id"],
                    )
                    if count != 3:
                        await conn.execute(
                            "UPDATE subjects SET reputation = reputation - 10 WHERE lower(username) = lower($1)",
                            party["leader_username"],
                        )
                        await notify_username(
                            bot,
                            pool,
                            party["leader_username"],
                            f"Напоминание: партия «{party['name']}» не имеет списка из трёх кандидатов. Репутация снижена на 10.",
                        )
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.exception("Ошибка фоновой проверки списков партий")


if __name__ == "__main__":
    asyncio.run(main())
