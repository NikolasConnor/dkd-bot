import asyncio
import os
from datetime import datetime, timedelta, timezone

import asyncpg
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

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
    "1": {
        "name": "Блошихин Кирилл Вадимович",
        "bio": "Перепил Горохова, и тот передал ему власть. Стал временно исполняющим обязанности президента.",
        "type": "main",
    },
    "2": {
        "name": "Сергей Сергеевич Косарев",
        "bio": "Главный генератор сбора шашлычных банкетов, а ещё у него есть борода.",
        "type": "main",
    },
    "3": {
        "name": "Кирилл Поселков Романович",
        "bio": "Единственный имеет девушку. Главный генератор сбора на хате.",
        "type": "main",
    },
    "4": {
        "name": "Горохов Никита Александрович",
        "bio": "Был президентом, но его перепил Блошихин. Сейчас премьер-министр.",
        "type": "additional",
    },
    "5": {
        "name": "ПРОТИВ ВСЕХ",
        "bio": "Выборы, выборы, кандидаты пидоры...\nPS. Группа «Ленинград».",
        "type": "against",
    },
}

VOTERS = {
    "@Haiser101": {"id": None, "name": "Иван"},
    "@vozduhanprimee": {"id": None, "name": "Тимофей"},
    "@spar9d": {"id": None, "name": "Владислав"},
    "@Cakcer_12": {"id": None, "name": "Максим"},
    "@Dronus01": {"id": None, "name": "Андрей"},
    "@Nikolas_Connor": {"id": 7934244888, "name": "Никита"},
    "@wwwLenGrad": {"id": None, "name": "Никита (2-й аккаунт)"},
}

PRELOADED_VOTES = [
    {"username": "@Cakcer_12", "voter_name": "Максим", "candidate_id": "3"},
    {"username": "@Dronus01", "voter_name": "Андрей", "candidate_id": "3"},
    {"username": "@vozduhanprimee", "voter_name": "Тимофей", "candidate_id": "3"},
]

db_pool = None
flags = {
    "test_end_notified": False,
    "election_end_notified": False,
}
# =============================================


dp = Dispatcher()


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
        # МИГРАЦИЯ: добавляем столбец, если база старая
        await conn.execute("""
            ALTER TABLE votes ADD COLUMN IF NOT EXISTS added_by_admin BOOLEAN DEFAULT FALSE
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS service_flags (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)


async def preload_votes():
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT value FROM service_flags WHERE key = 'preloaded_votes'"
        )
        if row is not None:
            return
        for v in PRELOADED_VOTES:
            await conn.execute("""
                INSERT INTO votes (user_id, username, voter_name, candidate_id)
                VALUES ($1, $2, $3, $4)
            """, -1, v["username"], v["voter_name"], v["candidate_id"])
        await conn.execute("""
            INSERT INTO service_flags (key, value) VALUES ('preloaded_votes', 'done')
        """)
        print(f"Добавлены предзаписанные голоса: {len(PRELOADED_VOTES)}")


async def save_vote(user_id, username, voter_name, candidate_id, added_by_admin=False):
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
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM votes WHERE username = $1", username
        )
        return row is not None


async def delete_vote_by_username(username):
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM votes WHERE username = $1", username)


async def clear_votes():
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM votes")
        await conn.execute("DELETE FROM service_flags WHERE key = 'preloaded_votes'")


# ===== ВСПОМОГАТЕЛЬНЫЕ =====
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
    if username in VOTERS:
        return True
    for uname, info in VOTERS.items():
        if info.get("id") == user_id:
            return True
    return False


def get_voter_name(user_id, username):
    if username in VOTERS:
        return VOTERS[username]["name"]
    for uname, info in VOTERS.items():
        if info.get("id") == user_id:
            return info["name"]
    return "Субъект"


# ===== ТЕКСТЫ =====
def build_ballot_text():
    status = get_election_status()
    n = now_msk()
    date = n.strftime("%d.%m.%Y %H:%M")

    if status == "before":
        delta = ELECTION_START - n
        return (
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "🗳 *БЮЛЛЕТЕНЬ ДКД*\n"
            "Выборы Президента\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "⏳ *Выборы ещё не начались.*\n\n"
            "Старт: 04.10.2026, 14:00 МСК\n"
            "Конец: 07.10.2026, 20:00 МСК\n\n"
            f"До старта: *{format_delta(delta)}*"
        )

    if status == "during":
        delta = ELECTION_END - n
        return (
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "🗳 *БЮЛЛЕТЕНЬ ДКД*\n"
            "Выборы Президента\n"
            f"Дата: {date} МСК\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"⏳ До конца голосования: *{format_delta(delta)}*\n\n"
            "Нажми на кнопку, чтобы отдать голос.\n"
            "Один субъект — один голос."
        )

    return (
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🗳 *БЮЛЛЕТЕНЬ ДКД*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🔒 *Выборы завершены.*\n\n"
        "Голосование проходило с 04.10.2026 14:00\n"
        "по 07.10.2026 20:00 МСК.\n\n"
        "Смотри результаты: /results"
    )


def build_ballot_keyboard():
    buttons = [
        [InlineKeyboardButton(text=f"{cid}. {CANDIDATES[cid]['name']}",
                              callback_data=f"vote_{cid}")]
        for cid in ["1", "2", "3"]
    ]
    buttons.append([InlineKeyboardButton(text="— Доп. кандидат —", callback_data="noop")])
    buttons.append([InlineKeyboardButton(text=f"4. {CANDIDATES['4']['name']}",
                                          callback_data="vote_4")])
    buttons.append([InlineKeyboardButton(text=f"5. {CANDIDATES['5']['name']}",
                                          callback_data="vote_5")])
    buttons.append([InlineKeyboardButton(text="📖 Биографии кандидатов", callback_data="bios")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_bios_text():
    text = "━━━━━━━━━━━━━━━━━━━━━\n"
    text += "📖 БИОГРАФИИ КАНДИДАТОВ\n"
    text += "━━━━━━━━━━━━━━━━━━━━━\n\n"
    for cid in ["1", "2", "3"]:
        c = CANDIDATES[cid]
        text += f"{cid}. {c['name']}\n"
        text += f"{c['bio']}\n\n"
    text += "Доп. кандидат:\n\n"
    c = CANDIDATES["4"]
    text += f"4. {c['name']}\n"
    text += f"{c['bio']}\n\n"
    c = CANDIDATES["5"]
    text += f"5. {c['name']}\n"
    text += f"{c['bio']}\n\n"
    text += "━━━━━━━━━━━━━━━━━━━━━\n"
    return text


async def build_results_text():
    all_votes = await get_all_votes()
    counter = {cid: 0 for cid in CANDIDATES}
    for v in all_votes:
        counter[v["candidate_id"]] += 1

    text = "━━━━━━━━━━━━━━━━━━━━━\n"
    text += "📊 РЕЗУЛЬТАТЫ ГОЛОСОВАНИЯ\n"
    text += "━━━━━━━━━━━━━━━━━━━━━\n\n"
    for cid, c in CANDIDATES.items():
        marker = ""
        if c["type"] == "additional":
            marker = " (доп.)"
        elif c["type"] == "against":
            marker = " (особый пункт)"
        text += f"{cid}. {c['name']}{marker} — {counter[cid]}\n"
    text += f"\nВсего голосов: {len(all_votes)}"

    max_votes = max(counter.values()) if counter else 0
    winners = [cid for cid, c in counter.items() if c == max_votes]
    if len(winners) == 1:
        win_id = winners[0]
        if win_id == "5":
            text += (
                "\n\n━━━━━━━━━━━━━━━━━━━━━\n"
                "⚠️ ВЫБОРЫ НЕДЕЙСТВИТЕЛЬНЫ\n"
                "━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Победил «ПРОТИВ ВСЕХ».\n\n"
                "Назначается ВТОРОЙ ТУР.\n"
                "Дата: 8–9 октября 2026.\n"
                "Кандидаты: определяются."
            )
        else:
            text += f"\n\n🏆 Победитель: {CANDIDATES[win_id]['name']}"
    else:
        text += "\n\n⚖️ Ничья! Нужен второй тур."
    return text


async def build_status_text():
    all_votes = await get_all_votes()
    voted_usernames = set()
    for v in all_votes:
        if v["username"]:
            voted_usernames.add(v["username"])

    voted_list = []
    not_voted_list = []

    for uname, info in VOTERS.items():
        if uname in voted_usernames:
            voted_list.append(f"✅ {info['name']} ({uname})")
        else:
            not_voted_list.append(f"❌ {info['name']} ({uname})")

    text = "━━━━━━━━━━━━━━━━━━━━━\n"
    text += "👥 СТАТУС ГОЛОСОВАНИЯ\n"
    text += "━━━━━━━━━━━━━━━━━━━━━\n\n"
    text += f"*Проголосовали ({len(voted_list)}):*\n"
    text += "\n".join(voted_list) if voted_list else "—"
    text += f"\n\n*Не голосовали ({len(not_voted_list)}):*\n"
    text += "\n".join(not_voted_list) if not_voted_list else "—"
    text += f"\n\n*Всего: {len(voted_list)} / {len(VOTERS)}*"
    return text


async def build_votes_list_text():
    all_votes = await get_all_votes()
    by_candidate = {cid: [] for cid in CANDIDATES}
    for v in all_votes:
        cid = v["candidate_id"]
        added = v.get("added_by_admin", False)
        marker = " (админ)" if added else ""
        by_candidate[cid].append(f"{v['voter_name']}{marker}")

    text = "━━━━━━━━━━━━━━━━━━━━━\n"
    text += "📋 СПИСОК ГОЛОСОВ\n"
    text += "━━━━━━━━━━━━━━━━━━━━━\n\n"
    for cid, c in CANDIDATES.items():
        voters = by_candidate[cid]
        text += f"*{cid}. {c['name']}* — {len(voters)} голос(ов)\n"
        for voter in voters:
            text += f"  • {voter}\n"
        text += "\n"
    return text


# ===== АДМИН-ПАНЕЛЬ =====
def build_admin_keyboard():
    buttons = [
        [InlineKeyboardButton(text="📊 Результаты", callback_data="admin_results")],
        [InlineKeyboardButton(text="👥 Кто проголосовал", callback_data="admin_status")],
        [InlineKeyboardButton(text="📋 Список голосов", callback_data="admin_votes")],
        [InlineKeyboardButton(text="✍️ Внести голос", callback_data="admin_add_vote")],
        [InlineKeyboardButton(text="🗑 Удалить голос", callback_data="admin_del_vote")],
        [InlineKeyboardButton(text="🔄 Сбросить всё", callback_data="admin_reset_confirm")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_admin_add_vote_keyboard():
    buttons = []
    for uname, info in VOTERS.items():
        buttons.append([InlineKeyboardButton(
            text=f"{info['name']} ({uname})",
            callback_data=f"admin_addvote_subj|{uname}"
        )])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_admin_add_candidate_keyboard(username):
    buttons = []
    for cid, c in CANDIDATES.items():
        buttons.append([InlineKeyboardButton(
            text=f"{cid}. {c['name']}",
            callback_data=f"admin_addvote_cand|{username}|{cid}"
        )])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_add_vote")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_admin_del_vote_keyboard():
    buttons = []
    for uname, info in VOTERS.items():
        buttons.append([InlineKeyboardButton(
            text=f"🗑 {info['name']} ({uname})",
            callback_data=f"admin_delvote|{uname}"
        )])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_admin_confirm_reset_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚠️ ДА, СБРОСИТЬ ВСЁ", callback_data="admin_reset_yes")],
        [InlineKeyboardButton(text="◀️ Отмена", callback_data="admin_back")],
    ])


@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Только админ.")
        return
    await message.answer(
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🛠 *АДМИН-ПАНЕЛЬ ДКД*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Выбери действие:",
        reply_markup=build_admin_keyboard(),
        parse_mode="Markdown"
    )


@dp.callback_query(lambda c: c.data == "admin_back")
async def admin_back(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Только админ.", show_alert=True)
        return
    await callback.message.edit_text(
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🛠 *АДМИН-ПАНЕЛЬ ДКД*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Выбери действие:",
        reply_markup=build_admin_keyboard(),
        parse_mode="Markdown"
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data == "admin_results")
async def admin_results(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Только админ.", show_alert=True)
        return
    try:
        text = await build_results_text()
        await callback.message.answer(text, parse_mode="Markdown")
    except Exception as e:
        await callback.message.answer(f"Ошибка: {e}")
    await callback.answer()


@dp.callback_query(lambda c: c.data == "admin_status")
async def admin_status(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Только админ.", show_alert=True)
        return
    try:
        text = await build_status_text()
        await callback.message.answer(text, parse_mode="Markdown")
    except Exception as e:
        await callback.message.answer(f"Ошибка: {e}")
    await callback.answer()


@dp.callback_query(lambda c: c.data == "admin_votes")
async def admin_votes(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Только админ.", show_alert=True)
        return
    try:
        text = await build_votes_list_text()
        await callback.message.answer(text, parse_mode="Markdown")
    except Exception as e:
        await callback.message.answer(f"Ошибка: {e}")
    await callback.answer()


@dp.callback_query(lambda c: c.data == "admin_add_vote")
async def admin_add_vote(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Только админ.", show_alert=True)
        return
    await callback.message.edit_text(
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "✍️ ВНЕСТИ ГОЛОС\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "За кого вносим голос?",
        reply_markup=build_admin_add_vote_keyboard(),
        parse_mode="Markdown"
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith("admin_addvote_subj|"))
async def admin_addvote_subj(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Только админ.", show_alert=True)
        return
    username = callback.data.split("|", 1)[1]
    info = VOTERS.get(username)
    if not info:
        await callback.answer("Не найден.", show_alert=True)
        return
    await callback.message.edit_text(
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"✍️ ГОЛОС ЗА: {info['name']}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"За какого кандидата?",
        reply_markup=build_admin_add_candidate_keyboard(username),
        parse_mode="Markdown"
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith("admin_addvote_cand|"))
async def admin_addvote_cand(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Только админ.", show_alert=True)
        return
    parts = callback.data.split("|")
    if len(parts) != 3:
        await callback.answer("Ошибка формата.", show_alert=True)
        return
    username = parts[1]
    cid = parts[2]

    info = VOTERS.get(username)
    if not info:
        await callback.answer("Субъект не найден.", show_alert=True)
        return

    await delete_vote_by_username(username)
    await save_vote(
        user_id=-1,
        username=username,
        voter_name=info["name"],
        candidate_id=cid,
        added_by_admin=True
    )

    cand_name = CANDIDATES[cid]["name"]
    await callback.message.edit_text(
        f"✅ ГОЛОС ВНЕСЁН\n\n"
        f"Субъект: {info['name']}\n"
        f"Кандидат: {cand_name}\n\n"
        f"_Голос добавлен от имени администратора._",
        parse_mode="Markdown"
    )
    await callback.answer("Готово!")


@dp.callback_query(lambda c: c.data == "admin_del_vote")
async def admin_del_vote(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Только админ.", show_alert=True)
        return
    await callback.message.edit_text(
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🗑 УДАЛИТЬ ГОЛОС\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "У кого удалить голос?",
        reply_markup=build_admin_del_vote_keyboard(),
        parse_mode="Markdown"
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith("admin_delvote|"))
async def admin_delvote(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Только админ.", show_alert=True)
        return
    username = callback.data.split("|", 1)[1]
    info = VOTERS.get(username)
    if not info:
        await callback.answer("Не найден.", show_alert=True)
        return
    await delete_vote_by_username(username)
    await callback.message.edit_text(
        f"✅ ГОЛОС УДАЛЁН\n\n"
        f"Субъект: {info['name']} ({username})",
        parse_mode="Markdown"
    )
    await callback.answer("Готово!")


@dp.callback_query(lambda c: c.data == "admin_reset_confirm")
async def admin_reset_confirm(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Только админ.", show_alert=True)
        return
    await callback.message.edit_text(
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "⚠️ СБРОСИТЬ ВСЁ?\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Это удалит ВСЕ голоса, включая предзагруженные.\n"
        "Действие необратимо.",
        reply_markup=build_admin_confirm_reset_keyboard(),
        parse_mode="Markdown"
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data == "admin_reset_yes")
async def admin_reset_yes(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Только админ.", show_alert=True)
        return
    await clear_votes()
    await callback.message.edit_text("🔄 ВСЁ СБРОШЕНО.")
    await callback.answer()


# ===== ОБЫЧНЫЕ ХЕНДЛЕРЫ =====
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "🏛 *Добро пожаловать на выборы Президента ДКД!*\n\n"
        "Команды:\n"
        "/vote — получить бюллетень\n"
        "/bios — биографии кандидатов\n"
        "/help — помощь",
        parse_mode="Markdown"
    )


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "📖 *Помощь*\n\n"
        "1. Нажми /vote.\n"
        "2. Выбери кандидата кнопкой.\n"
        "3. Голос учтён автоматически.\n\n"
        "Один субъект — один голос.\n"
        "Выборы: 04.10.2026 14:00 — 07.10.2026 20:00 МСК.",
        parse_mode="Markdown"
    )


@dp.message(Command("bios"))
async def cmd_bios(message: types.Message):
    await message.answer(build_bios_text())


@dp.message(lambda m: m.video is not None)
async def get_video_id(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    file_id = message.video.file_id
    await message.answer(
        "📹 Твой file_id видео:\n\n"
        f"`{file_id}`",
        parse_mode="Markdown"
    )


@dp.message(Command("vote"))
async def cmd_vote(message: types.Message):
    user = message.from_user
    username = f"@{user.username}" if user.username else None
    tester = is_tester(username)

    if not tester and not is_allowed_to_vote(user.id, username):
        await message.answer("❌ Ты не в списке голосующих субъектов ДКД.")
        return

    status = get_election_status()
    if not tester and status != "during":
        await message.answer(build_ballot_text(), parse_mode="Markdown")
        return

    if not tester:
        already_voted = await user_has_voted(user.id)
        if not already_voted and username:
            already_voted = await username_has_voted(username)
        if already_voted:
            await message.answer("⚠️ Ты уже проголосовал. Один субъект — один голос.")
            return

    prefix = "🧪 *ТЕСТОВЫЙ РЕЖИМ* — можешь голосовать много раз.\n\n" if tester else ""
    await message.answer(
        prefix + build_ballot_text(),
        reply_markup=build_ballot_keyboard(),
        parse_mode="Markdown"
    )


@dp.callback_query(lambda c: c.data == "bios")
async def process_bios(callback: types.CallbackQuery):
    try:
        await callback.message.answer(build_bios_text())
    except Exception as e:
        await callback.message.answer(f"Ошибка: {e}")
    await callback.answer()


@dp.callback_query(lambda c: c.data == "noop")
async def process_noop(callback: types.CallbackQuery):
    await callback.answer("Это просто пометка 🙂")


@dp.callback_query(lambda c: c.data.startswith("vote_"))
async def process_vote(callback: types.CallbackQuery):
    try:
        user = callback.from_user
        username = f"@{user.username}" if user.username else None
        tester = is_tester(username)

        if not tester and not is_allowed_to_vote(user.id, username):
            await callback.answer("Ты не в списке голосующих.", show_alert=True)
            return

        status = get_election_status()
        if not tester and status != "during":
            await callback.answer("Голосование сейчас закрыто.", show_alert=True)
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
        voter_name = get_voter_name(user.id, username) if not tester else "🧪 Никита (тест)"

        await save_vote(user.id, username, voter_name, candidate_id)

        suffix = "\n\nМожешь голосовать ещё раз." if tester else ""
        caption = (
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "✅ ГОЛОС ПРИНЯТ!\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"👤 Субъект: {voter_name}\n"
            f"🗳 Выбор: {candidate_name}{suffix}"
        )

        if VIDEO_FILE_ID:
            try:
                await callback.message.answer_video(video=VIDEO_FILE_ID, caption=caption)
            except Exception as e:
                print(f"Не смог отправить видео: {e}")
                await callback.message.answer(caption)
        else:
            await callback.message.answer(caption)

        if tester:
            await callback.message.answer(
                "🧪 Ещё раз? Нажми /vote или выбери ниже:",
                reply_markup=build_ballot_keyboard()
            )

        await callback.answer()
    except Exception as e:
        print(f"Ошибка в process_vote: {e}")
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
    text = await build_results_text()
    await message.answer(text, parse_mode="Markdown")


@dp.message(Command("reset"))
async def cmd_reset(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Только админ.")
        return
    await clear_votes()
    await message.answer("🔄 Голоса сброшены.")


# ===== ФОНОВАЯ ЗАДАЧА =====
async def background_watcher(bot: Bot):
    global flags
    while True:
        try:
            n = now_msk()

            if not flags["test_end_notified"] and n >= TEST_MODE_END:
                try:
                    await bot.send_message(
                        ADMIN_ID,
                        "━━━━━━━━━━━━━━━━━━━━━\n"
                        "🧪 *ТЕСТОВЫЙ РЕЖИМ СНЯТ*\n"
                        "━━━━━━━━━━━━━━━━━━━━━\n\n"
                        "Теперь ты голосуешь как обычный субъект.\n"
                        "С 14:00 МСК откроется голосование.",
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    print(f"Ошибка при снятии тестового режима: {e}")
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
