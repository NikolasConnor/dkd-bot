import asyncio
import os
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ================= НАСТРОЙКИ =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 7934244888

# Кандидаты (основные)
CANDIDATES = {
    "1": {
        "name": "Блошихин Кирилл Вадимович",
        "bio": "Перепел Гороха, и тот передал ему власть, стал временно исполняющий обязанности президента, сейчас находится на этой должности.",
        "type": "main",
    },
    "2": {
        "name": "Сергей Сергеевич Косарев",
        "bio": "Главный генератор сбора шашлычных банкетов, а ещё у него есть борода.",
        "type": "main",
    },
    "3": {
        "name": "Кирилл Поселков Романович",
        "bio": "Единственный имеет девушку (интересный персонаж уже), главный генератор сбора на хате.",
        "type": "main",
    },
    "4": {
        "name": "Горохов Никита Александрович",
        "bio": "Был президентом, но после того как его Перепел Блоха, передал последнему бразды правления. Сейчас занимает должность премьер-министра.",
        "type": "additional",
    },
    "5": {
        "name": "ПРОТИВ ВСЕХ",
        "bio": "Выборы, выборы, Кандидаты пидоры...\nPS. Группа Ленинград",
        "type": "against",
    },
}

# Голосующие (username → субъект)
VOTERS = {
    "@Haiser101": "Иван",
    "@vozduhanprimee": "Тимофей",
    "@spar9d": "Владислав",
    "@Cakcer_12": "Максим",
    "@Dronus01": "Андрей",
}

# Тестовый режим — можно голосовать много раз
TEST_USERNAMES = {"@Nikolas_Connor"}

votes = []
# =============================================


dp = Dispatcher()


def build_ballot_text():
    date = datetime.now().strftime("%d.%m.%Y")
    return (
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🗳 *БЮЛЛЕТЕНЬ ДКД*\n"
        "Выборы Президента\n"
        f"Дата: {date}\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Нажми на кнопку, чтобы отдать голос.\n"
        "Один субъект — один голос."
    )


def build_ballot_keyboard():
    buttons = []
    # Основные кандидаты
    for cid in ["1", "2", "3"]:
        c = CANDIDATES[cid]
        buttons.append([
            InlineKeyboardButton(
                text=f"{cid}. {c['name']}",
                callback_data=f"vote_{cid}"
            )
        ])
    # Доп. кандидат — отдельной строкой-пометкой
    buttons.append([
        InlineKeyboardButton(text="— Доп. кандидат —", callback_data="noop")
    ])
    buttons.append([
        InlineKeyboardButton(
            text=f"4. {CANDIDATES['4']['name']}",
            callback_data="vote_4"
        )
    ])
    # Против всех
    buttons.append([
        InlineKeyboardButton(
            text=f"5. {CANDIDATES['5']['name']}",
            callback_data="vote_5"
        )
    ])
    # Кнопка биографий
    buttons.append([
        InlineKeyboardButton(text="📖 Биографии кандидатов", callback_data="bios")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_bios_text():
    text = "━━━━━━━━━━━━━━━━━━━━━\n"
    text += "📖 *БИОГРАФИИ КАНДИДАТОВ*\n"
    text += "━━━━━━━━━━━━━━━━━━━━━\n\n"

    # Основные
    for cid in ["1", "2", "3"]:
        c = CANDIDATES[cid]
        text += f"*{cid}. {c['name']}*\n_{c['bio']}_\n\n"

    # Доп. кандидат
    text += "*Доп. кандидат:*\n\n"
    c = CANDIDATES["4"]
    text += f"*4. {c['name']}*\n_{c['bio']}_\n\n"

    # Против всех
    c = CANDIDATES["5"]
    text += f"*5. {c['name']}*\n_{c['bio']}_\n\n"

    text += "━━━━━━━━━━━━━━━━━━━━━\n"
    text += "_Подпись: _______\n_"
    return text


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "🏛 *Добро пожаловать на выборы Президента ДКД!*\n\n"
        "Команды:\n"
        "/vote — получить бюллетень\n"
        "/bios — биографии кандидатов\n"
        "/results — результаты (админ)\n"
        "/reset — сбросить голоса (админ)\n"
        "/help — помощь",
        parse_mode="Markdown"
    )


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "📖 *Помощь*\n\n"
        "1. Нажми /vote\n"
        "2. Выбери кандидата кнопкой\n"
        "3. Голос учтён автоматически\n\n"
        "Один субъект — один голос.\n"
        "Голосуют только штаты-избиратели, кроме кандидатов.",
        parse_mode="Markdown"
    )


@dp.message(Command("bios"))
async def cmd_bios(message: types.Message):
    await message.answer(build_bios_text(), parse_mode="Markdown")


@dp.message(Command("vote"))
async def cmd_vote(message: types.Message):
    user = message.from_user
    username = f"@{user.username}" if user.username else None
    is_tester = username in TEST_USERNAMES

    if not is_tester and username not in VOTERS:
        await message.answer("❌ Ты не в списке голосующих субъектов.")
        return

    if not is_tester:
        already_voted = any(v["user_id"] == user.id for v in votes)
        if already_voted:
            await message.answer("⚠️ Ты уже проголосовал. Один субъект — один голос.")
            return

    prefix = "🧪 *ТЕСТОВЫЙ РЕЖИМ* — можешь голосовать много раз.\n\n" if is_tester else ""
    await message.answer(
        prefix + build_ballot_text(),
        reply_markup=build_ballot_keyboard(),
        parse_mode="Markdown"
    )


@dp.callback_query(lambda c: c.data == "bios")
async def process_bios(callback: types.CallbackQuery):
    await callback.message.answer(build_bios_text(), parse_mode="Markdown")
    await callback.answer()


@dp.callback_query(lambda c: c.data == "noop")
async def process_noop(callback: types.CallbackQuery):
    await callback.answer("Это просто пометка 🙂")


@dp.callback_query(lambda c: c.data.startswith("vote_"))
async def process_vote(callback: types.CallbackQuery):
    user = callback.from_user
    username = f"@{user.username}" if user.username else None
    is_tester = username in TEST_USERNAMES

    if not is_tester and username not in VOTERS:
        await callback.answer("Ты не в списке голосующих.", show_alert=True)
        return

    if not is_tester:
        already_voted = any(v["user_id"] == user.id for v in votes)
        if already_voted:
            await callback.answer("Ты уже голосовал!", show_alert=True)
            return

    candidate_id = callback.data.split("_")[1]
    candidate_name = CANDIDATES[candidate_id]["name"]
    voter_name = VOTERS.get(username, "🧪 Тестер") if not is_tester else "🧪 Никита (тест)"

    votes.append({
        "user_id": user.id,
        "username": username,
        "voter_name": voter_name,
        "candidate_id": candidate_id,
    })

    suffix = "\n\n_Можешь голосовать ещё раз._" if is_tester else ""
    await callback.message.edit_text(
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ *ГОЛОС ПРИНЯТ!*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 Субъект: *{voter_name}*\n"
        f"🗳 Выбор: *{candidate_name}*{suffix}",
        parse_mode="Markdown"
    )

    if is_tester:
        await callback.message.answer(
            "🧪 *Ещё раз?* Нажми /vote или выбери ниже:",
            reply_markup=build_ballot_keyboard(),
            parse_mode="Markdown"
        )


@dp.message(Command("results"))
async def cmd_results(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Только админ может смотреть результаты.")
        return

    if not votes:
        await message.answer("📊 Пока никто не голосовал.")
        return

    counter = {cid: 0 for cid in CANDIDATES}
    for v in votes:
        counter[v["candidate_id"]] += 1

    text = "━━━━━━━━━━━━━━━━━━━━━\n"
    text += "📊 *РЕЗУЛЬТАТЫ ГОЛОСОВАНИЯ*\n"
    text += "━━━━━━━━━━━━━━━━━━━━━\n\n"

    for cid, c in CANDIDATES.items():
        marker = ""
        if c["type"] == "additional":
            marker = " _(доп.)_"
        elif c["type"] == "against":
            marker = " _(особый пункт)_"
        text += f"{cid}. {c['name']}{marker} — *{counter[cid]}*\n"

    text += f"\n_Всего голосов: {len(votes)}_"

    max_votes = max(counter.values())
    winners = [cid for cid, c in counter.items() if c == max_votes]

    if len(winners) == 1:
        win_id = winners[0]
        if win_id == "5":
            text += "\n\n⚠️ *Победил «ПРОТИВ ВСЕХ» — выборы недействительны!*"
        else:
            text += f"\n\n🏆 *Победитель: {CANDIDATES[win_id]['name']}*"
    else:
        text += "\n\n⚖️ *Ничья!* Нужен второй тур."

    await message.answer(text, parse_mode="Markdown")


@dp.message(Command("reset"))
async def cmd_reset(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Только админ может сбросить голоса.")
        return

    votes.clear()
    await message.answer("🔄 Голоса сброшены.")


async def main():
    if not BOT_TOKEN:
        print("❌ ОШИБКА: переменная BOT_TOKEN не задана!")
        return

    bot = Bot(token=BOT_TOKEN)
    print("Бот запущен...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
