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

# ===== КАНДИДАТЫ (для выборов Президента) =====
CANDIDATES = {
    "1": {"name": "Блошихин Кирилл Вадимович",
          "bio": "Перепил Горохова, и тот передал ему власть.",
          "type": "main"},
    "2": {"name": "Сергей Сергеевич Косарев",
          "bio": "Главный генератор сбора шашлычных банкетов.",
          "type": "main"},
    "3": {"name": "Кирилл Поселков Романович",
          "bio": "Единственный имеет девушку. Главный генератор сбора на хате.",
          "type": "main"},
    "4": {"name": "Горохов Никита Александрович",
          "bio": "Был президентом. Сейчас премьер-министр.",
          "type": "additional"},
    "5": {"name": "ПРОТИВ ВСЕХ",
          "bio": "Выборы, выборы, кандидаты пидоры...\nPS. Группа «Ленинград».",
          "type": "against"},
}

VOTERS = {
    "@Haiser101": {"id": None, "name": "Яровой Иван Сергеевич"},
    "@vozduhanprimee": {"id": None, "name": "Бородин Тимофей Сергеевич"},
    "@spar9d": {"id": None, "name": "Глазков Владислав Юрьевич"},
    "@Cakcer_12": {"id": None, "name": "Головин Максим Сергеевич"},
    "@Dronus01": {"id": None, "name": "Морев Андрей Олегович"},
    "@Nikolas_Connor": {"id": 7934244888, "name": "Горохов Никита Александрович"},
    "@wwwLenGrad": {"id": None, "name": "Никита (2-й аккаунт)"},
}

PRELOADED_VOTES = [
    {"username": "@Cakcer_12", "voter_name": "Головин Максим Сергеевич", "candidate_id": "3"},
    {"username": "@Dronus01", "voter_name": "Морев Андрей Олегович", "candidate_id": "3"},
    {"username": "@vozduhanprimee", "voter_name": "Бородин Тимофей Сергеевич", "candidate_id": "3"},
]

# ===== СУБЪЕКТЫ ДКД (9 человек) =====
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

# ===== РОЛИ (по Конституции) =====
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

# ===== НАЧАЛЬНЫЕ РОЛИ =====
INITIAL_ROLES = [
    {"username": "@G12_inthehearts", "role_code": "president"},
    {"username": "@Nikolas_Connor", "role_code": "premier"},
]

# ===== КОДОВОЕ СЛОВО =====
SECRET_WORD_VARIANTS = ["Бог Эфиопии", "бог ефиопии"]

db_pool = None
flags = {"test_end_notified": False, "election_end_notified": False}
# =============================================


dp = Dispatcher()


# ===== УТИЛИТЫ =====
def normalize_username(username):
    if not username:
        return None
    if not username.startswith("@"):
        return "@" + username
    return username


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
    uname = normalize_username(username)
    if uname in VOTERS:
        return True
    for u, info in VOTERS.items():
        if info.get("id") == user_id and user_id > 0:
            return True
    return False


def get_voter_name(user_id, username):
    uname = normalize_username(username)
    if uname in VOTERS:
        return VOTERS[uname]["name"]
    for u, info in VOTERS.items():
        if info.get("id") == user_id and user_id > 0:
            return info["name"]
    return "Субъект"


def check_secret_word(text):
    """Проверяет кодовое слово. Только именительный падеж, регистр и опечатки в буквах допускаются."""
    if not text:
        return False
    t = text.lower().strip()
    # Убираем лишние пробелы
    t = " ".join(t.split())
    # Проверяем варианты
    for variant in SECRET_WORD_VARIANTS:
        # Проверка на точное вхождение (с учётом опечаток в буквах — нечёткое сравнение)
        # Простая проверка: если t состоит из 2 слов, первое похоже на "бог", второе на "эфиопи"
        parts = t.split()
        if len(parts) == 2:
            w1, w2 = parts
            # Первое слово — «бог» (или похожее)
            if len(w1) == 3 and w1[0] == "б" and w1[1] == "о" and w1[2] == "г":
                # Второе слово — «эфиопии» / «ефиопии» и т.д.
                if w2.startswith("эфиоп") or w2.startswith("ефиоп") or w2.startswith("эфиоп"):
                    # Проверяем, что это не другой падеж (не "бога", не "эфиопию")
                    if w2.endswith("и") or w2.endswith("ия"):
                        return True
    return False


# ===== БАЗА ДАННЫХ =====
async def init_db():
    async with db_pool.acquire() as conn:
        # Голоса
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
        await conn.execute("""
            ALTER TABLE votes ADD COLUMN IF NOT EXISTS added_by_admin BOOLEAN DEFAULT FALSE
        """)
        # Служебные флаги
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS service_flags (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        # Субъекты
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS subjects (
                id SERIAL PRIMARY KEY,
                user_id BIGINT UNIQUE,
                username TEXT UNIQUE,
                full_name TEXT NOT NULL,
                is_citizen BOOLEAN DEFAULT FALSE,
                reputation INTEGER DEFAULT 0,
                joined_at TIMESTAMP DEFAULT NOW()
            )
        """)
        # Роли
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS roles (
                id SERIAL PRIMARY KEY,
                code TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                emoji TEXT DEFAULT '👤',
                description TEXT DEFAULT '',
                max_holders INTEGER,
                is_default BOOLEAN DEFAULT FALSE
            )
        """)
        # Роли субъектов
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS subject_roles (
                id SERIAL PRIMARY KEY,
                subject_id INTEGER REFERENCES subjects(id) ON DELETE CASCADE,
                role_id INTEGER REFERENCES roles(id) ON DELETE CASCADE,
                assigned_by BIGINT,
                assigned_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(subject_id, role_id)
            )
        """)


async def preload_roles():
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT value FROM service_flags WHERE key = 'roles_loaded'")
        if row is not None:
            return
        for r in ROLES_INITIAL:
            await conn.execute("""
                INSERT INTO roles (code, name, emoji, max_holders)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (code) DO NOTHING
            """, r["code"], r["name"], r["emoji"], r["max_holders"])
        await conn.execute("""
            INSERT INTO service_flags (key, value) VALUES ('roles_loaded', 'done')
        """)
        print(f"Роли загружены: {len(ROLES_INITIAL)}")


async def preload_subjects():
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT value FROM service_flags WHERE key = 'subjects_loaded'")
        if row is not None:
            return
        for s in SUBJECTS_INITIAL:
            uname = normalize_username(s["username"])
            await conn.execute("""
                INSERT INTO subjects (username, full_name, is_citizen)
                VALUES ($1, $2, TRUE)
                ON CONFLICT (username) DO NOTHING
            """, uname, s["full_name"])
        await conn.execute("""
            INSERT INTO service_flags (key, value) VALUES ('subjects_loaded', 'done')
        """)
        print(f"Субъекты загружены: {len(SUBJECTS_INITIAL)}")


async def preload_initial_roles():
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT value FROM service_flags WHERE key = 'initial_roles_loaded'")
        if row is not None:
            return
        for ir in INITIAL_ROLES:
            uname = normalize_username(ir["username"])
            subj = await conn.fetchrow("SELECT id FROM subjects WHERE username = $1", uname)
            role = await conn.fetchrow("SELECT id FROM roles WHERE code = $1", ir["role_code"])
            if subj and role:
                await conn.execute("""
                    INSERT INTO subject_roles (subject_id, role_id, assigned_by)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (subject_id, role_id) DO NOTHING
                """, subj["id"], role["id"], ADMIN_ID)
        await conn.execute("""
            INSERT INTO service_flags (key, value) VALUES ('initial_roles_loaded', 'done')
        """)
        print("Начальные роли назначены.")


async def preload_votes():
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT value FROM service_flags WHERE key = 'preloaded_votes'")
        if row is not None:
            return
        for v in PRELOADED_VOTES:
            await conn.execute("""
                INSERT INTO votes (user_id, username, voter_name, candidate_id)
                VALUES ($1, $2, $3, $4)
            """, -1, normalize_username(v["username"]), v["voter_name"], v["candidate_id"])
        await conn.execute("""
            INSERT INTO service_flags (key, value) VALUES ('preloaded_votes', 'done')
        """)
        print(f"Предзаписанные голоса: {len(PRELOADED_VOTES)}")


async def save_vote(user_id, username, voter_name, candidate_id, added_by_admin=False):
    username = normalize_username(username)
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
    username = normalize_username(username)
    if not username:
        return False
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT id FROM votes WHERE username = $1", username)
        return row is not None


async def delete_vote_by_username(username):
    username = normalize_username(username)
    if not username:
        return
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM votes WHERE username = $1", username)


async def clear_votes():
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM votes")
        await conn.execute("DELETE FROM service_flags WHERE key = 'preloaded_votes'")


# ===== СУБЪЕКТЫ =====
async def get_subject_by_user_id(user_id):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM subjects WHERE user_id = $1", user_id)


async def get_subject_by_username(username):
    username = normalize_username(username)
    if not username:
        return None
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM subjects WHERE username = $1", username)


async def get_all_subjects():
    async with db_pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM subjects ORDER BY id")


async def create_subject(user_id, username, full_name, is_citizen=True):
    username = normalize_username(username)
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO subjects (user_id, username, full_name, is_citizen)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (username) DO UPDATE SET user_id = $1
        """, user_id, username, full_name, is_citizen)


async def update_subject_user_id(username, user_id):
    username = normalize_username(username)
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE subjects SET user_id = $1 WHERE username = $2", user_id, username)


async def get_subject_roles(subject_id):
    async with db_pool.acquire() as conn:
        return await conn.fetch("""
            SELECT r.* FROM roles r
            JOIN subject_roles sr ON sr.role_id = r.id
            WHERE sr.subject_id = $1
            ORDER BY r.id
        """, subject_id)


async def assign_role(subject_id, role_id, assigned_by):
    async with db_pool.acquire() as conn:
        # Проверка: макс. ролей у субъекта — 2
        cnt = await conn.fetchval(
            "SELECT COUNT(*) FROM subject_roles WHERE subject_id = $1", subject_id
        )
        if cnt >= 2:
            return False, "Максимум 2 должности"
        # Проверка: макс. holders для роли
        role = await conn.fetchrow("SELECT * FROM roles WHERE id = $1", role_id)
        if not role:
            return False, "Роль не найдена"
        if role["max_holders"] is not None:
            holders = await conn.fetchval(
                "SELECT COUNT(*) FROM subject_roles WHERE role_id = $1", role_id
            )
            if holders >= role["max_holders"]:
                return False, f"Роль «{role['name']}» занята (макс: {role['max_holders']})"
        await conn.execute("""
            INSERT INTO subject_roles (subject_id, role_id, assigned_by)
            VALUES ($1, $2, $3)
            ON CONFLICT (subject_id, role_id) DO NOTHING
        """, subject_id, role_id, assigned_by)
        return True, "OK"


async def remove_role(subject_id, role_id):
    async with db_pool.acquire() as conn:
        await conn.execute("""
            DELETE FROM subject_roles WHERE subject_id = $1 AND role_id = $2
        """, subject_id, role_id)


async def get_all_roles():
    async with db_pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM roles ORDER BY id")


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
        text += f"{cid}. {c['name']}\n{c['bio']}\n\n"
    text += "Доп. кандидат:\n\n"
    c = CANDIDATES["4"]
    text += f"4. {c['name']}\n{c['bio']}\n\n"
    c = CANDIDATES["5"]
    text += f"5. {c['name']}\n{c['bio']}\n\n"
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
        marker = " (доп.)" if c["type"] == "additional" else (" (особый пункт)" if c["type"] == "against" else "")
        text += f"{cid}. {c['name']}{marker} — {counter[cid]}\n"
    text += f"\nВсего голосов: {len(all_votes)}"

    max_votes = max(counter.values()) if counter else 0
    winners = [cid for cid, c in counter.items() if c == max_votes]
    if len(winners) == 1:
        win_id = winners[0]
        if win_id == "5":
            text += "\n\n⚠️ Победил «ПРОТИВ ВСЕХ» — выборы недействительны."
        else:
            text += f"\n\n🏆 Победитель: {CANDIDATES[win_id]['name']}"
    else:
        text += "\n\n⚖️ Ничья!"
    return text


async def build_status_text():
    all_votes = await get_all_votes()
    voted_usernames = set()
    voted_ids = set()
    for v in all_votes:
        uname = normalize_username(v["username"])
        if uname:
            voted_usernames.add(uname)
        if v["user_id"] and v["user_id"] > 0:
            voted_ids.add(v["user_id"])

    voted_list, not_voted_list = [], []
    for uname, info in VOTERS.items():
        uname_norm = normalize_username(uname)
        uid = info.get("id")
        is_voted = uname_norm in voted_usernames or (uid and uid > 0 and uid in voted_ids)
        if is_voted:
            voted_list.append(f"✅ {info['name']} ({uname})")
        else:
            not_voted_list.append(f"❌ {info['name']} ({uname})")

    text = "━━━━━━━━━━━━━━━━━━━━━\n👥 СТАТУС ГОЛОСОВАНИЯ\n━━━━━━━━━━━━━━━━━━━━━\n\n"
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
        marker = " (админ)" if v.get("added_by_admin", False) else ""
        by_candidate[cid].append(f"{v['voter_name']}{marker}")

    text = "━━━━━━━━━━━━━━━━━━━━━\n📋 СПИСОК ГОЛОСОВ\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    for cid, c in CANDIDATES.items():
        voters = by_candidate[cid]
        text += f"*{cid}. {c['name']}* — {len(voters)} голос(ов)\n"
        for voter in voters:
            text += f"  • {voter}\n"
        text += "\n"
    return text


async def build_subject_profile_text(subject):
    roles = await get_subject_roles(subject["id"])
    roles_text = "\n".join([f"{r['emoji']} {r['name']}" for r in roles]) if roles else "👤 Субъект"

    joined = subject["joined_at"].strftime("%d.%m.%Y") if subject["joined_at"] else "—"
    citizen_text = "✅ Есть" if subject["is_citizen"] else "❌ Нет"

    text = "━━━━━━━━━━━━━━━━━━━━━\n"
    text += "👤 ПРОФИЛЬ СУБЪЕКТА\n"
    text += "━━━━━━━━━━━━━━━━━━━━━\n\n"
    text += f"{subject['full_name']}\n"
    text += f"Username: {subject['username'] or '—'}\n\n"
    text += f"Должности:\n{roles_text}\n\n"
    text += f"Гражданство: {citizen_text}\n"
    text += f"В ДКД с: {joined}\n"
    text += f"Репутация: {subject['reputation']}"
    return text

async def build_subjects_list_text():
    subjects = await get_all_subjects()
    text = "━━━━━━━━━━━━━━━━━━━━━\n👥 СУБЪЕКТЫ ДКД\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    for s in subjects:
        roles = await get_subject_roles(s["id"])
        roles_short = ", ".join([r["name"] for r in roles]) if roles else "Субъект"
        text += f"• *{s['full_name']}*\n  {roles_short}\n\n"
    text += f"Всего: {len(subjects)}"
    return text


async def build_roles_list_text():
    roles = await get_all_roles()
    text = "━━━━━━━━━━━━━━━━━━━━━\n🎭 ДОЛЖНОСТИ ДКД\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    for r in roles:
        max_text = f"макс: {r['max_holders']}" if r["max_holders"] else "без ограничений"
        text += f"{r['emoji']} *{r['name']}* ({max_text})\n"
    return text


# ===== АДМИН-ПАНЕЛЬ =====
def build_admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Субъекты", callback_data="admin_subjects")],
        [InlineKeyboardButton(text="🎭 Должности", callback_data="admin_roles")],
        [InlineKeyboardButton(text="📊 Результаты выборов", callback_data="admin_results")],
        [InlineKeyboardButton(text="👥 Кто голосовал", callback_data="admin_status")],
        [InlineKeyboardButton(text="📋 Список голосов", callback_data="admin_votes")],
        [InlineKeyboardButton(text="✍️ Внести голос", callback_data="admin_add_vote")],
        [InlineKeyboardButton(text="🗑 Удалить голос", callback_data="admin_del_vote")],
        [InlineKeyboardButton(text="🔄 Сбросить голоса", callback_data="admin_reset_confirm")],
    ])


def build_admin_subjects_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Список субъектов", callback_data="admin_subjects_list")],
        [InlineKeyboardButton(text="➕ Выдать должность", callback_data="admin_assign_role_subj")],
        [InlineKeyboardButton(text="➖ Снять должность", callback_data="admin_remove_role_subj")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")],
    ])


async def build_admin_subjects_list_keyboard():
    subjects = await get_all_subjects()
    buttons = []
    for s in subjects:
        buttons.append([InlineKeyboardButton(
            text=f"{s['full_name']}",
            callback_data=f"admin_subj_view|{s['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_subjects")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def build_admin_assign_role_subj_keyboard():
    subjects = await get_all_subjects()
    buttons = []
    for s in subjects:
        buttons.append([InlineKeyboardButton(
            text=f"{s['full_name']}",
            callback_data=f"admin_assign_subj|{s['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_subjects")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def build_admin_assign_role_keyboard(subject_id):
    roles = await get_all_roles()
    buttons = []
    for r in roles:
        buttons.append([InlineKeyboardButton(
            text=f"{r['emoji']} {r['name']}",
            callback_data=f"admin_assign_role|{subject_id}|{r['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_subjects")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def build_admin_remove_role_subj_keyboard():
    subjects = await get_all_subjects()
    buttons = []
    for s in subjects:
        buttons.append([InlineKeyboardButton(
            text=f"{s['full_name']}",
            callback_data=f"admin_remove_subj|{s['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_subjects")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def build_admin_remove_role_keyboard(subject_id):
    roles = await get_subject_roles(subject_id)
    buttons = []
    for r in roles:
        buttons.append([InlineKeyboardButton(
            text=f"🗑 {r['emoji']} {r['name']}",
            callback_data=f"admin_remove_role|{subject_id}|{r['id']}"
        )])
    if not roles:
        buttons.append([InlineKeyboardButton(text="(нет должностей)", callback_data="noop")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_subjects")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_admin_del_vote_keyboard():
    buttons = []
    for uname, info in VOTERS.items():
        buttons.append([InlineKeyboardButton(
            text=f"🗑 {info['name']}",
            callback_data=f"admin_delvote|{uname}"
        )])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_admin_add_vote_keyboard():
    buttons = []
    for uname, info in VOTERS.items():
        buttons.append([InlineKeyboardButton(
            text=info['name'],
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


def build_admin_confirm_reset_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚠️ ДА, СБРОСИТЬ", callback_data="admin_reset_yes")],
        [InlineKeyboardButton(text="◀️ Отмена", callback_data="admin_back")],
    ])


# ===== ХЕНДЛЕРЫ =====
@dp.message(Command("me"))
async def cmd_me(message: types.Message):
    user = message.from_user
    username = normalize_username(user.username)

    subject = None
    if username:
        subject = await get_subject_by_username(username)
    if not subject and user.id:
        subject = await get_subject_by_user_id(user.id)

    if not subject:
        await message.answer("❌ Ты не зарегистрирован. Напиши /start.")
        return

    text = await build_subject_profile_text(subject)
    await message.answer(text)
    # Новый пользователь — просим кодовое слово
    await message.answer(
        "🏛 *Добро пожаловать в ДКД!*\n\n"
        "Ты не в списке субъектов.\n"
        "Чтобы зарегистрироваться, отправь *кодовое слово*.",
        parse_mode="Markdown"
    )


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "📖 *Помощь*\n\n"
        "/me — профиль субъекта\n"
        "/subjects — список субъектов\n"
        "/roles — список должностей\n"
        "/vote — голосование\n\n"
        "Выборы Президента: 04.10.2026 14:00 — 07.10.2026 20:00 МСК.",
        parse_mode="Markdown"
    )


@dp.message(Command("me"))
async def cmd_me(message: types.Message):
    user = message.from_user
    username = normalize_username(user.username)

    subject = None
    if username:
        subject = await get_subject_by_username(username)
    if not subject and user.id:
        subject = await get_subject_by_user_id(user.id)

    if not subject:
        await message.answer("❌ Ты не зарегистрирован. Напиши /start.")
        return

    text = await build_subject_profile_text(subject)
    await message.answer(text, parse_mode="Markdown")


@dp.message(Command("subjects"))
async def cmd_subjects(message: types.Message):
    text = await build_subjects_list_text()
    await message.answer(text, parse_mode="Markdown")


@dp.message(Command("roles"))
async def cmd_roles(message: types.Message):
    text = await build_roles_list_text()
    await message.answer(text, parse_mode="Markdown")


# ===== ОБРАБОТКА КОДОВОГО СЛОВА =====
@dp.message(lambda m: m.text and not m.text.startswith("/"))
async def handle_text(message: types.Message):
    user = message.from_user
    username = normalize_username(user.username)

    # Проверяем, есть ли субъект
    subject = None
    if username:
        subject = await get_subject_by_username(username)
    if not subject and user.id:
        subject = await get_subject_by_user_id(user.id)

    if subject:
        # Уже зарегистрирован — игнорируем
        return

    # Проверяем кодовое слово
    if check_secret_word(message.text):
        if not username:
            await message.answer("❌ У тебя нет username в Telegram. Установи username и попробуй снова.")
            return
        # Регистрируем как нового субъекта (НЕ гражданина — ждёт одобрения Президента)
        # Но пока просто создаём запись
        await message.answer(
            "✅ Кодовое слово принято!\n\n"
            "Ты зарегистрирован как *новый субъект*.\n"
            "Ожидай одобрения Президента для получения гражданства.\n\n"
            "Пока можешь пользоваться:\n"
            "/me — профиль\n"
            "/subjects — список субъектов",
            parse_mode="Markdown"
        )
        # Уведомляем админа
        try:
            await message.bot.send_message(
                ADMIN_ID,
                f"📥 *Новый субъект*\n\n"
                f"ФИО: (не указано)\n"
                f"Username: {username}\n"
                f"User ID: {user.id}\n\n"
                f"Ждёт одобрения гражданства.",
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"Не смог уведомить админа: {e}")
    else:
        await message.answer(
            "❌ Неверное кодовое слово.\n\n"
            "Попробуй снова. Подсказка: два слова, связанные с Эфиопией и Богом."
        )


# ===== АДМИН-ПАНЕЛЬ =====
@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Только админ.")
        return
    await message.answer(
        "━━━━━━━━━━━━━━━━━━━━━\n🛠 *АДМИН-ПАНЕЛЬ ДКД*\n━━━━━━━━━━━━━━━━━━━━━\n\nВыбери действие:",
        reply_markup=build_admin_keyboard(),
        parse_mode="Markdown"
    )


@dp.callback_query(lambda c: c.data == "admin_back")
async def admin_back(callback: types.CallbackQuery):
    try:
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("Только админ.", show_alert=True)
            return
        await callback.message.edit_text(
            "━━━━━━━━━━━━━━━━━━━━━\n🛠 *АДМИН-ПАНЕЛЬ ДКД*\n━━━━━━━━━━━━━━━━━━━━━\n\nВыбери действие:",
            reply_markup=build_admin_keyboard(),
            parse_mode="Markdown"
        )
        await callback.answer()
    except Exception as e:
        print(f"Ошибка admin_back: {e}")
        try:
            await callback.answer("Ошибка", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_subjects")
async def admin_subjects(callback: types.CallbackQuery):
    try:
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("Только админ.", show_alert=True)
            return
        await callback.message.edit_text(
            "━━━━━━━━━━━━━━━━━━━━━\n👥 *СУБЪЕКТЫ*\n━━━━━━━━━━━━━━━━━━━━━\n\nВыбери действие:",
            reply_markup=build_admin_subjects_keyboard(),
            parse_mode="Markdown"
        )
        await callback.answer()
    except Exception as e:
        print(f"Ошибка admin_subjects: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_subjects_list")
async def admin_subjects_list(callback: types.CallbackQuery):
    try:
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("Только админ.", show_alert=True)
            return
        kb = await build_admin_subjects_list_keyboard()
        await callback.message.edit_text(
            "━━━━━━━━━━━━━━━━━━━━━\n👥 *СУБЪЕКТЫ*\n━━━━━━━━━━━━━━━━━━━━━\n\nВыбери субъекта:",
            reply_markup=kb,
            parse_mode="Markdown"
        )
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("admin_subj_view|"))
async def admin_subj_view(callback: types.CallbackQuery):
    try:
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("Только админ.", show_alert=True)
            return
        sid = int(callback.data.split("|")[1])
        async with db_pool.acquire() as conn:
            subject = await conn.fetchrow("SELECT * FROM subjects WHERE id = $1", sid)
        if not subject:
            await callback.answer("Не найден.", show_alert=True)
            return
        text = await build_subject_profile_text(subject)
        await callback.message.answer(text, parse_mode="Markdown")
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_assign_role_subj")
async def admin_assign_role_subj(callback: types.CallbackQuery):
    try:
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("Только админ.", show_alert=True)
            return
        kb = await build_admin_assign_role_subj_keyboard()
        await callback.message.edit_text(
            "━━━━━━━━━━━━━━━━━━━━━\n➕ *ВЫДАТЬ ДОЛЖНОСТЬ*\n━━━━━━━━━━━━━━━━━━━━━\n\nВыбери субъекта:",
            reply_markup=kb,
            parse_mode="Markdown"
        )
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("admin_assign_subj|"))
async def admin_assign_subj(callback: types.CallbackQuery):
    try:
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("Только админ.", show_alert=True)
            return
        sid = int(callback.data.split("|")[1])
        kb = await build_admin_assign_role_keyboard(sid)
        await callback.message.edit_text(
            "━━━━━━━━━━━━━━━━━━━━━\n➕ *ВЫБЕРИ ДОЛЖНОСТЬ*\n━━━━━━━━━━━━━━━━━━━━━\n\nКакую должность выдать?",
            reply_markup=kb,
            parse_mode="Markdown"
        )
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("admin_assign_role|"))
async def admin_assign_role(callback: types.CallbackQuery):
    try:
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("Только админ.", show_alert=True)
            return
        parts = callback.data.split("|")
        sid = int(parts[1])
        rid = int(parts[2])

        ok, msg = await assign_role(sid, rid, ADMIN_ID)

        if ok:
            async with db_pool.acquire() as conn:
                subject = await conn.fetchrow("SELECT * FROM subjects WHERE id = $1", sid)
                role = await conn.fetchrow("SELECT * FROM roles WHERE id = $1", rid)
            text = f"✅ *ГОТОВО!*\n\n{subject['full_name']} назначен:\n{role['emoji']} *{role['name']}*"
            try:
                await callback.message.edit_text(text, parse_mode="Markdown")
            except Exception:
                await callback.message.answer(text, parse_mode="Markdown")
        else:
            await callback.message.answer(f"❌ {msg}")
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_remove_role_subj")
async def admin_remove_role_subj(callback: types.CallbackQuery):
    try:
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("Только админ.", show_alert=True)
            return
        kb = await build_admin_remove_role_subj_keyboard()
        await callback.message.edit_text(
            "━━━━━━━━━━━━━━━━━━━━━\n➖ *СНЯТЬ ДОЛЖНОСТЬ*\n━━━━━━━━━━━━━━━━━━━━━\n\nВыбери субъекта:",
            reply_markup=kb,
            parse_mode="Markdown"
        )
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("admin_remove_subj|"))
async def admin_remove_subj(callback: types.CallbackQuery):
    try:
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("Только админ.", show_alert=True)
            return
        sid = int(callback.data.split("|")[1])
        kb = await build_admin_remove_role_keyboard(sid)
        await callback.message.edit_text(
            "━━━━━━━━━━━━━━━━━━━━━\n➖ *ВЫБЕРИ ДОЛЖНОСТЬ ДЛЯ СНЯТИЯ*\n━━━━━━━━━━━━━━━━━━━━━",
            reply_markup=kb,
            parse_mode="Markdown"
        )
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("admin_remove_role|"))
async def admin_remove_role(callback: types.CallbackQuery):
    try:
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("Только админ.", show_alert=True)
            return
        parts = callback.data.split("|")
        sid = int(parts[1])
        rid = int(parts[2])
        await remove_role(sid, rid)
        await callback.message.edit_text("✅ Должность снята.", parse_mode="Markdown")
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


# ===== ВЫБОРЫ =====
@dp.callback_query(lambda c: c.data == "admin_results")
async def admin_results(callback: types.CallbackQuery):
    try:
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("Только админ.", show_alert=True)
            return
        text = await build_results_text()
        await callback.message.answer(text, parse_mode="Markdown")
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_status")
async def admin_status(callback: types.CallbackQuery):
    try:
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("Только админ.", show_alert=True)
            return
        text = await build_status_text()
        await callback.message.answer(text, parse_mode="Markdown")
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_votes")
async def admin_votes(callback: types.CallbackQuery):
    try:
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("Только админ.", show_alert=True)
            return
        text = await build_votes_list_text()
        await callback.message.answer(text, parse_mode="Markdown")
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_add_vote")
async def admin_add_vote(callback: types.CallbackQuery):
    try:
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("Только админ.", show_alert=True)
            return
        await callback.message.edit_text(
            "✍️ *ВНЕСТИ ГОЛОС*\n\nЗа кого вносим голос?",
            reply_markup=build_admin_add_vote_keyboard(),
            parse_mode="Markdown"
        )
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("admin_addvote_subj|"))
async def admin_addvote_subj(callback: types.CallbackQuery):
    try:
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("Только админ.", show_alert=True)
            return
        username = callback.data.split("|", 1)[1]
        info = VOTERS.get(username)
        if not info:
            await callback.answer("Не найден.", show_alert=True)
            return
        await callback.message.edit_text(
            f"✍️ *ГОЛОС ЗА: {info['name']}*\n\nЗа какого кандидата?",
            reply_markup=build_admin_add_candidate_keyboard(username),
            parse_mode="Markdown"
        )
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("admin_addvote_cand|"))
async def admin_addvote_cand(callback: types.CallbackQuery):
    try:
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("Только админ.", show_alert=True)
            return
        parts = callback.data.split("|")
        username, cid = parts[1], parts[2]
        info = VOTERS.get(username)
        if not info:
            await callback.answer("Не найден.", show_alert=True)
            return
        await delete_vote_by_username(username)
        await save_vote(-1, username, info["name"], cid, added_by_admin=True)
        text = f"✅ Голос внесён.\n\n{info['name']} → {CANDIDATES[cid]['name']}"
        try:
            await callback.message.edit_text(text, parse_mode="Markdown")
        except Exception:
            await callback.message.answer(text, parse_mode="Markdown")
        await callback.answer("Готово!")
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_del_vote")
async def admin_del_vote(callback: types.CallbackQuery):
    try:
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("Только админ.", show_alert=True)
            return
        await callback.message.edit_text(
            "🗑 *УДАЛИТЬ ГОЛОС*\n\nУ кого удалить?",
            reply_markup=build_admin_del_vote_keyboard(),
            parse_mode="Markdown"
        )
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data.startswith("admin_delvote|"))
async def admin_delvote(callback: types.CallbackQuery):
    try:
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("Только админ.", show_alert=True)
            return
        username = callback.data.split("|", 1)[1]
        info = VOTERS.get(username)
        if not info:
            await callback.answer("Не найден.", show_alert=True)
            return
        await delete_vote_by_username(username)
        text = f"✅ Голос удалён: {info['name']}"
        try:
            await callback.message.edit_text(text, parse_mode="Markdown")
        except Exception:
            await callback.message.answer(text, parse_mode="Markdown")
        await callback.answer("Готово!")
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_reset_confirm")
async def admin_reset_confirm(callback: types.CallbackQuery):
    try:
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("Только админ.", show_alert=True)
            return
        await callback.message.edit_text(
            "⚠️ *СБРОСИТЬ ВСЁ?*\n\nЭто удалит все голоса.",
            reply_markup=build_admin_confirm_reset_keyboard(),
            parse_mode="Markdown"
        )
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


@dp.callback_query(lambda c: c.data == "admin_reset_yes")
async def admin_reset_yes(callback: types.CallbackQuery):
    try:
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("Только админ.", show_alert=True)
            return
        await clear_votes()
        await callback.message.edit_text("🔄 Сброшено.")
        await callback.answer()
    except Exception as e:
        print(f"Ошибка: {e}")
        try:
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        except Exception:
            pass


# ===== ГОЛОСОВАНИЕ =====
@dp.message(Command("vote"))
async def cmd_vote(message: types.Message):
    try:
        user = message.from_user
        username = normalize_username(user.username)
        tester = is_tester(username)

        if not tester and not is_allowed_to_vote(user.id, username):
            await message.answer("❌ Ты не в списке голосующих.")
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
                await message.answer("⚠️ Ты уже голосовал.")
                return

        prefix = "🧪 *ТЕСТОВЫЙ РЕЖИМ*\n\n" if tester else ""
        await message.answer(
            prefix + build_ballot_text(),
            reply_markup=build_ballot_keyboard(),
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"Ошибка cmd_vote: {e}")
        await message.answer(f"Ошибка: {e}")


@dp.callback_query(lambda c: c.data == "bios")
async def process_bios(callback: types.CallbackQuery):
    try:
        await callback.message.answer(build_bios_text())
    except Exception as e:
        print(f"Ошибка bios: {e}")
    try:
        await callback.answer()
    except Exception:
        pass


@dp.callback_query(lambda c: c.data == "noop")
async def process_noop(callback: types.CallbackQuery):
    try:
        await callback.answer("Пометка 🙂")
    except Exception:
        pass


@dp.callback_query(lambda c: c.data.startswith("vote_"))
async def process_vote(callback: types.CallbackQuery):
    try:
        user = callback.from_user
        username = normalize_username(user.username)
        tester = is_tester(username)

        if not tester and not is_allowed_to_vote(user.id, username):
            await callback.answer("Не в списке.", show_alert=True)
            return

        status = get_election_status()
        if not tester and status != "during":
            await callback.answer("Голосование закрыто.", show_alert=True)
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
        voter_name = get_voter_name(user.id, username) if not tester else "🧪 Тест"

        await save_vote(user.id, username, voter_name, candidate_id)

        suffix = "\n\n_Можешь голосовать ещё раз._" if tester else ""
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
            except Exception:
                await callback.message.answer(caption)
        else:
            await callback.message.answer(caption)

        if tester:
            await callback.message.answer(
                "🧪 Ещё раз?",
                reply_markup=build_ballot_keyboard()
            )
        await callback.answer()
    except Exception as e:
        print(f"Ошибка process_vote: {e}")
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
    await message.answer("🔄 Сброшено.")


@dp.message(lambda m: m.video is not None)
async def get_video_id(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer(
        f"📹 file_id:\n\n`{message.video.file_id}`",
        parse_mode="Markdown"
    )


# ===== ФОНОВАЯ ЗАДАЧА =====
async def background_watcher(bot: Bot):
    global flags
    while True:
        try:
            n = now_msk()
            if not flags["test_end_notified"] and n >= TEST_MODE_END:
                try:
                    await bot.send_message(ADMIN_ID, "🧪 Тестовый режим снят.")
                except Exception as e:
                    print(f"Ошибка: {e}")
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
                    try:
                        await bot.send_message(uid, text)
                    except Exception as e:
                        print(f"Не смог отправить {uid}: {e}")
                if ADMIN_ID not in sent_to:
                    try:
                        await bot.send_message(ADMIN_ID, text)
                    except Exception:
                        pass
                flags["election_end_notified"] = True
        except Exception as e:
            print(f"Ошибка watcher: {e}")
        await asyncio.sleep(30)


# ===== ЗАПУСК =====
async def main():
    global db_pool
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN не задан!")
        return
    if not DATABASE_URL:
        print("❌ DATABASE_URL не задан!")
        return

    db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    await init_db()
    await preload_roles()
    await preload_subjects()
    await preload_initial_roles()
    await preload_votes()
    print("База данных подключена.")

    bot = Bot(token=BOT_TOKEN)
    asyncio.create_task(background_watcher(bot))
    print("Бот запущен...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
