import asyncio
import os
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ================= НАСТРОЙКИ =================
# Токен берётся из переменной окружения Railway
BOT_TOKEN = os.getenv("BOT_TOKEN")

ADMIN_ID = 7934244888

CANDIDATES = {
    "1": "Блошихин Кирилл Вадимович",
    "2": "Сергей Сергеевич Косарев",
    "3": "Кирилл Поселков Романович",
    "4": "Никита",
    "5": "ПРОТИВ ВСЕХ",
}

VOTERS = {
    "@Haiser101": "Иван",
    "@vozduhanprimee": "Тимофей",
    "@spar9d": "Владислав",
    "@Cakcer_12": "Максим",
    "@Dronus01": "Андрей",
}

TEST_USERNAMES = {
    "@Nikolas_Connor",
}

votes = []
# =============================================


dp = Dispatcher()


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "🏛 *Добро пожаловать на выборы Президента ДКД!*\n\n"
        "Команды:\n"
        "/vote — проголосовать\n"
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
        "2. Выбери кандидата\n"
        "3. Голос учтён автоматически\n\n"
        "Голосуют только штаты, кроме кандидатов.\n"
        "Один штат — один голос.",
        parse_mode="Markdown"
    )


@dp.message(Command("vote"))
async def cmd_vote(message: types.Message):
    user = message.from_user
    username = f"@{user.username}" if user.username else None

    is_tester = username in TEST_USERNAMES

    if not is_tester and username not in VOTERS:
        await message.answer("❌ Ты не в списке голосующих штатов.")
        return

    if not is_tester:
        already_voted = any(v["user_id"] == user.id for v in votes)
        if already_voted:
            await message.answer("⚠️ Ты уже проголосовал. Один штат — один голос.")
            return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"{num}. {name}", callback_data=f"vote_{num}")]
            for num, name in CANDIDATES.items()
        ]
    )

    prefix = "🧪 *ТЕСТОВЫЙ РЕЖИМ* — можешь голосовать много раз.\n\n" if is_tester else ""
    await message.answer(
        f"{prefix}🗳 *Бюллетень ДКД*\n\nВыбери кандидата:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )


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
    candidate_name = CANDIDATES[candidate_id]

    voter_name = VOTERS.get(username, "🧪 Тестер") if not is_tester else "🧪 Никита (тест)"

    votes.append({
        "user_id": user.id,
        "username": username,
        "voter_name": voter_name,
        "candidate_id": candidate_id,
    })

    suffix = "\n\n_Можешь голосовать ещё раз._" if is_tester else ""
    await callback.message.edit_text(
        f"✅ *Голос принят!*\n\n"
        f"Штат: {voter_name}\n"
        f"Выбор: {candidate_name}{suffix}",
        parse_mode="Markdown"
    )

    if is_tester:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=f"{num}. {name}", callback_data=f"vote_{num}")]
                for num, name in CANDIDATES.items()
            ]
        )
        await callback.message.answer(
            "🧪 *Ещё раз?* Нажми /vote или выбери ниже:",
            reply_markup=keyboard,
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

    text = "📊 *Результаты голосования:*\n\n"
    for cid, name in CANDIDATES.items():
        text += f"{cid}. {name} — *{counter[cid]}* голос(ов)\n"

    text += f"\n_Всего голосов: {len(votes)}_"

    max_votes = max(counter.values())
    winners = [cid for cid, c in counter.items() if c == max_votes]

    if len(winners) == 1:
        win_id = winners[0]
        if win_id == "5":
            text += "\n\n⚠️ *Победил «ПРОТИВ ВСЕХ» — выборы недействительны!*"
        else:
            text += f"\n\n🏆 *Победитель: {CANDIDATES[win_id]}*"
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
