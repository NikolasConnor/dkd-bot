import asyncio
import os
from datetime import datetime, timedelta, timezone

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ================= НАСТРОЙКИ =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 7934244888

MSK = timezone(timedelta(hours=3))

# ===== ОКНО ВЫБОРОВ =====
ELECTION_START = datetime(2026, 10, 4, 0, 0, tzinfo=MSK)
ELECTION_END = datetime(2026, 10, 7, 20, 0, tzinfo=MSK)

# ===== ТЕСТОВЫЙ РЕЖИМ =====
TEST_USERNAMES = {"@Nikolas_Connor"}
TEST_MODE_END = datetime(2026, 10, 4, 13, 0, tzinfo=MSK)

# ===== ВИДЕО (file_id) =====
VIDEO_FILE_ID = "BAACAgIAAxkBAANLasIfw2IcWeZwXgiPqm4Ne1fHeRAAAsapAAKmCxFKxM0YkvpfMeA9BA"

# ===== КАНДИДАТЫ =====
CANDIDATES = {
    "1": {
        "name": "Блошихин Кирилл Вадимович",
        "bio": "Перепил Горохова, и тот передал ему власть. Стал временно исполняющим обязанности президента, сейчас находится на этой должности.",
        "type": "main",
    },
    "2": {
        "name": "Сергей Сергеевич Косарев",
        "bio": "Главный генератор сбора шашлычных банкетов, а ещё у него есть борода.",
        "type": "main",
    },
    "3": {
        "name": "Кирилл Поселков Романович",
        "bio": "Единственный имеет девушку (интересный персонаж, однако). Главный генератор сбора на хате.",
        "type": "main",
    },
    "4": {
        "name": "Горохов Никита Александрович",
        "bio": "Был президентом, но после того как его перепил Блошихин, передал последнему бразды правления. Сейчас занимает должность премьер-министра.",
        "type": "additional",
    },
    "5": {
        "name": "ПРОТИВ ВСЕХ",
        "bio": "Выборы, выборы, кандидаты пидоры...\nPS. Группа «Ленинград».",
        "type": "against",
    },
}

# ===== ГОЛОСУЮЩИЕ =====
VOTERS = {
    "@Haiser101": "Иван",
    "@vozduhanprimee": "Тимофей",
    "@spar9d": "Владислав",
    "@Cakcer_12": "Максим",
    "@Dronus01": "Андрей",
    "@Nikolas_Connor": "Никита",
    "@wwwLenGrad": "Никита (2-й аккаунт)",
}

votes = []

flags = {
    "test_end_notified": False,
    "election_end_notified": False,
}
# =============================================


dp = Dispatcher()


# ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====
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


def build_results_text():
    counter = {cid: 0 for cid in CANDIDATES}
    for v in votes:
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

    text += f"\nВсего голосов: {len(votes)}"

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


# ===== ФОНОВАЯ ЗАДАЧА =====
async def background_watcher(bot: Bot):
    global flags
    while True:
        try:
            n = now_msk()

            # 1. Снятие тестового режима в 13:00 04.10.2026
            if not flags["test_end_notified"] and n >= TEST_MODE_END:
                try:
                    await bot.send_message(
                        ADMIN_ID,
                        "━━━━━━━━━━━━━━━━━━━━━\n"
                        "🧪 *ТЕСТОВЫЙ РЕЖИМ СНЯТ*\n"
                        "━━━━━━━━━━━━━━━━━━━━━\n\n"
                        "Теперь ты голосуешь как обычный субъект.\n"
                        "С 14:00 МСК откроется голосование —\n"
                        "сможешь отдать один голос.\n\n"
                        "_Голоса, отданные в тестовом режиме, обнулены._",
                        parse_mode="Markdown"
                    )
                    votes.clear()
                except Exception as e:
                    print(f"Ошибка при снятии тестового режима: {e}")
                flags["test_end_notified"] = True

            # 2. Автообъявление после 20:00 07.10.2026
            if not flags["election_end_notified"] and n >= ELECTION_END:
                text = build_results_text()
                sent_to = set()
                for v in votes:
                    uid = v["user_id"]
                    if uid in sent_to:
                        continue
                    sent_to.add(uid)
                    try:
                        await bot.send_message(uid, text)
                    except Exception as e:
                        print(f"Не смог отправить {uid}: {e}")

                if ADMIN_ID not in sent_to:
                    try:
                        await bot.send_message(ADMIN_ID, text)
                    except Exception as e:
                        print(f"Не смог отправить админу: {e}")

                flags["election_end_notified"] = True

        except Exception as e:
            print(f"Ошибка в watcher: {e}")

        await asyncio.sleep(30)


# ===== ХЕНДЛЕРЫ =====
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


# ===== ВРЕМЕННЫЙ ХЕНДЛЕР: получение file_id видео =====
@dp.message(lambda m: m.video is not None)
async def get_video_id(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    file_id = message.video.file_id
    await message.answer(
        "📹 Твой file_id видео:\n\n"
        f"`{file_id}`\n\n"
        "Скопируй его и вставь в код в переменную VIDEO_FILE_ID.",
        parse_mode="Markdown"
    )


@dp.message(Command("vote"))
async def cmd_vote(message: types.Message):
    user = message.from_user
    username = f"@{user.username}" if user.username else None
    tester = is_tester(username)

    if not tester and username not in VOTERS:
        await message.answer("❌ Ты не в списке голосующих субъектов.")
        return

    status = get_election_status()

    if not tester and status != "during":
        await message.answer(build_ballot_text(), parse_mode="Markdown")
        return

    if not tester:
        already_voted = any(v["user_id"] == user.id for v in votes)
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
    await callback.message.answer(build_bios_text())
    await callback.answer()


@dp.callback_query(lambda c: c.data == "noop")
async def process_noop(callback: types.CallbackQuery):
    await callback.answer("Это просто пометка 🙂")


@dp.callback_query(lambda c: c.data.startswith("vote_"))
async def process_vote(callback: types.CallbackQuery):
    user = callback.from_user
    username = f"@{user.username}" if user.username else None
    tester = is_tester(username)

    if not tester and username not in VOTERS:
        await callback.answer("Ты не в списке голосующих.", show_alert=True)
        return

    status = get_election_status()
    if not tester and status != "during":
        await callback.answer("Голосование сейчас закрыто.", show_alert=True)
        return

    if not tester:
        already_voted = any(v["user_id"] == user.id for v in votes)
        if already_voted:
            await callback.answer("Ты уже голосовал!", show_alert=True)
            return

    candidate_id = callback.data.split("_")[1]
    candidate_name = CANDIDATES[candidate_id]["name"]
    voter_name = VOTERS.get(username, "🧪 Тестер") if not tester else "🧪 Никита (тест)"

    votes.append({
        "user_id": user.id,
        "username": username,
        "voter_name": voter_name,
        "candidate_id": candidate_id,
    })

    suffix = "\n\nМожешь голосовать ещё раз." if tester else ""

    # Формируем подпись к видео
    caption = (
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "✅ ГОЛОС ПРИНЯТ!\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 Субъект: {voter_name}\n"
        f"🗳 Выбор: {candidate_name}{suffix}"
    )

    # Одно сообщение: видео + подпись
    if VIDEO_FILE_ID:
        try:
            await callback.message.answer_video(
                video=VIDEO_FILE_ID,
                caption=caption
            )
        except Exception as e:
            print(f"Не смог отправить видео: {e}")
            await callback.message.answer(caption)
    else:
        await callback.message.answer(caption)

    # Тестеру — предложение проголосовать ещё раз
    if tester:
        await callback.message.answer(
            "🧪 Ещё раз? Нажми /vote или выбери ниже:",
            reply_markup=build_ballot_keyboard()
        )

    await callback.answer()


@dp.message(Command("results"))
async def cmd_results(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Только админ может смотреть результаты.")
        return

    if not votes:
        await message.answer("📊 Пока никто не голосовал.")
        return

    await message.answer(build_results_text(), parse_mode="Markdown")


@dp.message(Command("reset"))
async def cmd_reset(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Только админ может сбросить голоса.")
        return

    votes.clear()
    await message.answer("🔄 Голоса сброшены.")


# ===== ЗАПУСК =====
async def main():
    if not BOT_TOKEN:
        print("❌ ОШИБКА: переменная BOT_TOKEN не задана!")
        return

    bot = Bot(token=BOT_TOKEN)

    asyncio.create_task(background_watcher(bot))

    print("Бот запущен...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
