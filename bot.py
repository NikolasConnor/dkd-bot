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
