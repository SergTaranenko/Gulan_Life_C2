# -*- coding: utf-8 -*-
"""
Бот «Путь через эпохи» v3.0
Ядро — engine.
Контент рангов в rank_01.py … rank_12.py
"""

import os
import json
import random
import logging
import importlib
import ssl
import uuid
from datetime import datetime, date, timedelta
from pathlib import Path
from io import BytesIO

import pytz
import aiohttp
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes
)

# ── Конфигурация ────────────────────────────────────────────────────────────
BOT_TOKEN     = os.environ.get("BOT_TOKEN")
GIGACHAT_AUTH = os.environ.get("GIGACHAT_AUTH")
DATA_DIR      = Path("/app/data")
RANKS_DIR     = Path(__file__).parent          # rank_XX.py лежат рядом с bot.py
TIMEZONE      = pytz.timezone("Europe/Moscow")

WAKEUP_HOUR    = 5
WAKEUP_MINUTE  = 30
DOPAMINE_START = 6
DOPAMINE_END   = 22

HUNGER_WARNING_HOURS = 18
HUNGER_RIOT_HOURS    = 30

GIGACHAT_OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
GIGACHAT_API_URL   = "https://gigachat.devices.sberbank.ru/api/v1"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ── Расписание рангов ────────────────────────────────────────────────────────
# start      — дата разблокировки (праздник, церемония)
# active_from — дата начала реального отсчёта дел
# bot_end    — дата остановки бота
RANK_SCHEDULE = [
    {"rank_idx": 0,  "start": "2026-04-21", "active_from": "2026-04-21"},  # Старт
    {"rank_idx": 1,  "start": "2026-05-01", "active_from": "2026-05-04"},  # Праздник 1–3 мая
    {"rank_idx": 2,  "start": "2026-05-09", "active_from": "2026-05-11"},  # Праздник 9–10 мая
    {"rank_idx": 3,  "start": "2026-06-01", "active_from": "2026-06-08"},  # Праздник 1–7 июня
    {"rank_idx": 4,  "start": "2026-07-07", "active_from": "2026-07-08"},  # Праздник 7 июля
    {"rank_idx": 5,  "start": "2026-08-01", "active_from": "2026-08-03"},  # Праздник 1–2 августа
    {"rank_idx": 6,  "start": "2026-08-29", "active_from": "2026-08-31"},  # Праздник 29–30 августа
    {"rank_idx": 7,  "start": "2026-09-12", "active_from": "2026-09-14"},  # Праздник 12–13 сентября
    {"rank_idx": 8,  "start": "2026-10-03", "active_from": "2026-10-05"},  # Праздник 3–4 октября
    {"rank_idx": 9,  "start": "2026-11-04", "active_from": "2026-11-06"},  # Праздник 4–5 ноября
    {"rank_idx": 10, "start": "2026-11-09", "active_from": "2026-11-24"},  # Праздник 9–23 ноября
    {"rank_idx": 11, "start": "2026-12-12", "active_from": "2026-12-14"},  # Праздник 12–13 декабря
]
VICTORY_DATE = date(2026, 12, 31)   # 31 декабря — победа, конец пути
BOT_END_DATE = date(2027, 1, 2)     # Бот останавливается 2 января

# ── Загрузка контента рангов ─────────────────────────────────────────────────
_rank_modules = {}

def load_rank_module(idx: int):
    """Загружает rank_XX.py и кэширует"""
    if idx not in _rank_modules:
        module_name = f"rank_{idx+1:02d}"
        spec_path = RANKS_DIR / f"{module_name}.py"
        if not spec_path.exists():
            logger.warning(f"Rank file {spec_path} not found, using fallback")
            _rank_modules[idx] = None
            return None
        import importlib.util
        spec = importlib.util.spec_from_file_location(module_name, spec_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _rank_modules[idx] = mod
    return _rank_modules[idx]

def get_rank_data(idx: int) -> dict:
    """Возвращает данные ранга из модуля или заглушку"""
    mod = load_rank_module(idx)
    if mod and hasattr(mod, "RANK"):
        return mod.RANK
    # Заглушка если файл не найден
    return {
        "name":           f"Ранг {idx+1}",
        "era":            "natuf" if idx < 6 else "neo",
        "deeds_needed":   17 if idx < 6 else 12,
        "short":          "Делай дела.",
        "full":           "Делай дела. Каждый день.",
        "image_prompt":   None,
        "done_phrases":   ["Дело сделано.", "Зафиксировано.", "Продолжай."],
        "promotion_text": f"Повышение до ранга {idx+2}.",
    }

# Предзагрузка всех рангов при старте
def preload_ranks():
    for i in range(12):
        get_rank_data(i)
    logger.info("Все ранги загружены")

# ── Вехи пути ────────────────────────────────────────────────────────────────
MILESTONES = {
    17:  "🏔 Первый ранг Натуфа пройден. 17 дел. Ты поднялся со дна.",
    34:  "⚒️ Второй ранг позади. 34 дела. Ты перестал быть грузом.",
    51:  "🔥 Половина Натуфа. 51 дело. Ты уже не инструмент — ты человек.",
    68:  "🧠 Четвёртый ранг. 68 дел. Твоя память стоит дороже мышц.",
    85:  "📜 Пятый ранг. 85 дел. Ты держишь то, что другие забывают.",
    102: "👑 Натуф пройден. 102 дела. Теперь — путь в другой мир.",
    114: "🏛 Первый ранг Неолита. 114 дел. Ты выжил на чужой земле.",
    126: "🏗 Второй ранг. 126 дел. Чужой дом стал чуть своим.",
    138: "🌾 Третий ранг. 138 дел. Ты создаёшь еду — это власть.",
    150: "🗡 Четвёртый ранг. 150 дел. Технолог смерти.",
    162: "🔑 Пятый ранг Неолита. 162 дела. Ключи от житницы — твои.",
    174: "🗿 174 дела. ПУТЬ ПРОЙДЕН. Ты — Созидатель места. Первый тиран.",
}

# ── Дофаминовые награды (общий пул — остальное в файлах рангов) ─────────────
# Натуф: охота / кремень / собирательство
DOPAMINE_NATUF = {
    "common": [
        ("🍬 Вкусняшка сладкая",      "🍯 Мёд диких пчёл — найденный в дупле"),
        ("🍫 Шоколад",                "🌰 Кедровые орехи — редкая находка"),
        ("🍎 Фрукт",                  "🍎 Дикие яблоки с рощи"),
        ("🥪 Сытный бутер",           "🥩 Кусок вяленого мяса — запасы на зиму"),
        ("☕ Кофе",                   "☕ Отвар из желудей — тонизирует"),
        ("🍵 Чай",                    "🍵 Отвар из липового цвета — согревает"),
        ("🧃 Напиток",                "🧃 Берёзовый сок — свежий, сладкий"),
        ("🪥 Почистить зубы",         "🌿 Пожевать веточку осины"),
        ("💧 Умыться",                "💧 Умыться водой из реки"),
        ("🧼 Помыть руки",            "🖐️ Отмыть руки от крови и кремнёвой пыли"),
        ("🧦 Сменить носки",          "🧦 Сменить кожаные обмотки на ногах"),
        ("👕 Сменить футболку",       "🦌 Сменить рубаху из лосиной шкуры"),
        ("🪟 Проветрить",             "🌬️ Выгнать дым из шалаша"),
        ("🧹 Убрать со стола",        "🪵 Убрать стружку с рабочего камня"),
        ("🛏 Заправить кровать",      "🌿 Уложить свежие ветки ели в ложе"),
        ("✨ Порядок",                "✨ Разложить инструменты по костяным чехлам"),
        ("🚶 Пройтись",              "🚶 Прогуляться по берегу — проверить сети"),
        ("🙆 Потянуться",            "🙆 Потянуться после работы над кремнем"),
        ("🏋️ Поприседать",          "🏋️ Приседания с кремнёвым ядрищем"),
        ("🔄 Круги шеей",            "🔄 Размять шею после склонов над инструментами"),
        ("🤸 Разминка",              "🤸 Разминка перед охотой"),
        ("🤫 Три минуты тишины",     "🤫 Три минуты слушать шум леса"),
        ("😌 Самомассаж лица",       "😌 Растереть лицо с медвежьим жиром"),
        ("🔋 Зарядить телефон",      "🎒 Проверить охотничье снаряжение"),
        ("🎧 Зарядить наушники",     "🏹 Проверить тетиву лука и оперение стрел"),
    ],
    "rare": [
        ("💬 Написать жене",          "💬 Поговорить с женой у общего очага"),
        ("🗣 Поболтать с супругой",   "🗣 Обсудить планы на завтрашнюю охоту"),
        ("🐕 Поиграть с собакой",    "🐕 Погладить охотничью собаку — она заслужила"),
        ("📨 Написать другу",         "📨 Обменяться новостями с соседней стоянкой"),
        ("😂 Анекдот",                "😂 Рассказать байку у костра"),
        ("📅 Планы на завтра",        "📅 Посмотреть на фазу луны — она определяет охоту"),
        ("🚿 Душ",                    "🚿 Обмыться в реке — смыть запах перед охотой"),
        ("🌳 Прогулка",               "🌳 Выйти в лес — тихая охота"),
        ("🎵 Любимый трек",           "🎵 Сыграть на костяной флейте у костра"),
        ("🛏 Лечь пораньше",          "🔥 Устроиться ближе к костру — тепло и покой"),
        ("🍦 Мороженое из Ледника",   "❄️ Загляни в Ледник Шамана (/шаман)"),
    ],
    "legendary": [
        ("📱 Лента Дзена",            "🔥 Медитация: смотреть на узоры пламени"),
        ("🌍 Заморские каналы",       "🌍 Слушать рассказы про море от странника"),
        ("📚 Толковые каналы",        "📚 Старейшина рассказывает легенды племени"),
        ("💭 Мечтать над целями",     "💭 Загадать желание Духу Леса"),
        ("📈 Саморазвитие",           "⚒️ Придумать новый способ ретуши кремня"),
        ("🛒 Маркетплейсы",           "🏺 Осмотреть товары на обменной ярмарке"),
        ("🍦 Мороженое",              "❄️ Снежок с мёдом и кедровыми орехами"),
        ("🎧 Музыка в наушниках",     "👂 Прислушаться к шуму леса и реки"),
        ("🍦 Редкий вкус из Ледника", "❄️ Особая награда — /шаман раскроет тайну"),
    ]
}

# Неолит: зерно / строительство / ритуал / оседлость
DOPAMINE_NEO = {
    "common": [
        ("🍬 Вкусняшка сладкая",      "🌾 Горсть свежемолотой пшеницы — первый урожай"),
        ("🍫 Шоколад",                "🫘 Бобы из хранилища — редкость для чужака"),
        ("🍎 Фрукт",                  "🍇 Дикий инжир с анатолийских склонов"),
        ("🥪 Сытный бутер",           "🫓 Лепёшка из ячменной муки на раскалённом камне"),
        ("☕ Кофе",                   "🌿 Отвар из трав — привычка оседлого человека"),
        ("🍵 Чай",                    "🌾 Настой на злаковых отрубях — согревает"),
        ("🧃 Напиток",                "🍶 Первое брожёное зерно — зачатки пива"),
        ("🪥 Почистить зубы",         "🌾 Пожевать стебель ячменя — чистит зубы"),
        ("💧 Умыться",                "💧 Умыться из каменного корыта"),
        ("🧼 Помыть руки",            "🖐️ Отмыть руки от земли и глины"),
        ("🧦 Сменить носки",          "🧶 Сменить льняные обмотки — ткань уже есть"),
        ("👕 Сменить футболку",       "👘 Сменить грубую льняную рубаху"),
        ("🪟 Проветрить",             "🌬️ Открыть дымовое отверстие в кровле дома"),
        ("🧹 Убрать со стола",        "🌾 Смести зерновую шелуху с тока"),
        ("🛏 Заправить кровать",      "🌾 Заменить солому в матрасе на свежую"),
        ("✨ Порядок",                "✨ Разложить семена по кожаным мешочкам"),
        ("🚶 Пройтись",              "🚶 Обойти поле — проверить всходы"),
        ("🙆 Потянуться",            "🙆 Потянуться после работы с тяжёлым камнем"),
        ("🏋️ Поприседать",          "🏋️ Приседания с мешком зерна"),
        ("🔄 Круги шеей",            "🔄 Размять шею после кладки стен"),
        ("🤸 Разминка",              "🤸 Разминка перед работой в каменоломне"),
        ("🤫 Три минуты тишины",     "🤫 Три минуты смотреть на поле — слышать рост"),
        ("😌 Самомассаж лица",       "😌 Растереть лицо глиняной водой"),
        ("🔋 Зарядить телефон",      "🎒 Проверить запасы семян на завтра"),
        ("🎧 Зарядить наушники",     "🐐 Проверить загон для коз"),
    ],
    "rare": [
        ("💬 Написать жене",          "💬 Поговорить с женой — оседлая жизнь это позволяет"),
        ("🗣 Поболтать с супругой",   "🗣 Обсудить план следующего посева"),
        ("🐕 Поиграть с собакой",    "🐕 Погладить первую одомашненную собаку"),
        ("📨 Написать другу",         "📨 Отправить весть в Левант — откуда пришёл"),
        ("😂 Анекдот",                "😂 Рассказать байку у общинного очага"),
        ("📅 Планы на завтра",        "📅 Отметить фазу луны — по ней сеют"),
        ("🚿 Душ",                    "🚿 Обмыться в каменном бассейне — роскошь неолита"),
        ("🌳 Прогулка",               "🌾 Пройтись по своему полю — это твоё"),
        ("🎵 Любимый трек",           "🎵 Сыграть на глиняной флейте"),
        ("💑 Время с женой",          "🏠 Вечер в каменном доме вдвоём — у тебя теперь есть стены"),
        ("💆 Массаж от супруги",      "🫒 Она разотрёт плечи оливковым маслом — строитель устал"),
        ("🫂 Обнять жену",            "🫂 Обнять у очага — оседлая жизнь даёт это каждый вечер"),
        ("🍦 Мороженое из Ледника",   "❄️ Загляни в Ледник Шамана (/шаман)"),
    ],
    "legendary": [
        ("📱 Лента Дзена",            "🔥 Медитация у ритуального огня Гёбекли-Тепе"),
        ("🌍 Заморские каналы",       "🌍 Слушать рассказы торговца про долину Нила"),
        ("📚 Толковые каналы",        "📚 Жрец объясняет смысл узоров на Т-столбах"),
        ("💭 Мечтать над целями",     "💭 Представить своё имя на камне этого места"),
        ("📈 Саморазвитие",           "🏺 Придумать новую форму глиняного сосуда"),
        ("🛒 Маркетплейсы",           "🏺 Осмотреть товары торговцев с севера"),
        ("🍦 Мороженое",              "🫒 Оливки с анатолийских склонов — они здесь есть"),
        ("🎧 Музыка в наушниках",     "👂 Слушать звуки первого постоянного поселения"),
        ("🍦 Редкий вкус из Ледника", "❄️ Особая награда — /шаман раскроет тайну"),
    ]
}

def get_dopamine_reward(era: str = "natuf") -> str:
    pool = DOPAMINE_NATUF if era == "natuf" else DOPAMINE_NEO
    # Дополнительные награды из файла ранга (если есть)
    roll = random.randint(1, 100)
    if roll <= 70:
        cat = "common"
    elif roll <= 95:
        cat = "rare"
    else:
        cat = "legendary"
    modern, ancient = random.choice(pool[cat])
    icon = "🏹" if era == "natuf" else "🌾"
    return f"{modern}\n{icon} {ancient}"

# ── GigaChat ─────────────────────────────────────────────────────────────────
class GigaChatAPI:
    def __init__(self):
        self.token_cache = {"token": None, "expires": None}

    async def get_token(self):
        if self.token_cache["token"] and self.token_cache["expires"]:
            if datetime.now().timestamp() < self.token_cache["expires"] - 60:
                return self.token_cache["token"]
        if not GIGACHAT_AUTH:
            return None
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(
                    GIGACHAT_OAUTH_URL,
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Accept": "application/json",
                        "RqUID": str(uuid.uuid4()),
                        "Authorization": f"Basic {GIGACHAT_AUTH}"
                    },
                    data="scope=GIGACHAT_API_PERS",
                    ssl=ssl_ctx
                ) as resp:
                    if resp.status == 200:
                        d = await resp.json()
                        self.token_cache["token"] = d["access_token"]
                        self.token_cache["expires"] = d["expires_at"] / 1000
                        return d["access_token"]
        except Exception as e:
            logger.error(f"GigaChat auth: {e}")
        return None

    async def generate_image(self, prompt: str):
        token = await self.get_token()
        if not token:
            return None
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
        try:
            timeout = aiohttp.ClientTimeout(total=90)
            async with aiohttp.ClientSession(timeout=timeout) as s:
                async with s.post(
                    f"{GIGACHAT_API_URL}/chat/completions",
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                        "Authorization": f"Bearer {token}"
                    },
                    json={
                        "model": "GigaChat-Max",
                        "messages": [{"role": "user", "content": prompt}],
                        "function_call": "auto"
                    },
                    ssl=ssl_ctx
                ) as resp:
                    if resp.status != 200:
                        return None
                    d = await resp.json()
                    content = d["choices"][0]["message"]["content"]
                    if "<img src=\"" in content:
                        start = content.find("<img src=\"") + 10
                        end = content.find("\"", start)
                        file_id = content[start:end]
                        async with s.get(
                            f"{GIGACHAT_API_URL}/files/{file_id}/content",
                            headers={"Authorization": f"Bearer {token}"},
                            ssl=ssl_ctx
                        ) as img_resp:
                            if img_resp.status == 200:
                                return await img_resp.read()
        except Exception as e:
            logger.error(f"Image gen: {e}")
        return None

    async def generate_text(self, prompt: str, temperature: float = 0.8):
        token = await self.get_token()
        if not token:
            return None
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(
                    f"{GIGACHAT_API_URL}/chat/completions",
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                        "Authorization": f"Bearer {token}"
                    },
                    json={
                        "model": "GigaChat-Max",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": temperature
                    },
                    ssl=ssl_ctx
                ) as resp:
                    if resp.status == 200:
                        d = await resp.json()
                        return d["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"Text gen: {e}")
        return None

gigachat = GigaChatAPI()

async def generate_keeper_success_text(streak: int, rank_name: str) -> str:
    """GigaChat генерирует сцену после успешного вечернего чека"""
    scenarios = [
        "спор за место у костра между двумя охотниками",
        "неравный раздел добычи",
        "долг инструментом — нож затуплен и не возвращён",
        "конфликт поколений — старший не хочет учить молодого",
        "спор о маршруте — север или запад",
        "брачная сделка — обмен навыка на ресурс",
        "чужак просит ночлег у стоянки",
        "кто-то взял чужую долю зерна",
    ]
    scenario = random.choice(scenarios)
    prompt = (
        f"Ты — {rank_name} в первобытном обществе. "
        f"Серия выполненных соглашений: {streak} дней. "
        f"Сегодня ты разрешил ситуацию: {scenario}. "
        f"Опиши коротко (2-3 предложения) конкретные действия: жесты, детали, результат. "
        f"Стиль: сдержанный, деловой, без пафоса. Только факты."
    )
    result = await gigachat.generate_text(prompt)
    return result or "Соглашение сдержано. Порядок восстановлен."

# ── Ледник Шамана ─────────────────────────────────────────────────────────────
try:
    import importlib.util as _ilu, pathlib as _pl
    _at_path = _pl.Path(__file__).parent / "adult_treats.py"
    _at_spec = _ilu.spec_from_file_location("adult_treats", _at_path)
    _at_mod  = _ilu.module_from_spec(_at_spec)
    _at_spec.loader.exec_module(_at_mod)
    get_random_flavor   = _at_mod.get_random_flavor
    get_cipher_text     = _at_mod.get_cipher_text
    GLACIER_AVAILABLE   = True
except Exception as _e:
    logger.warning(f"adult_treats not loaded: {_e}")
    GLACIER_AVAILABLE   = False
    def get_random_flavor(rank_index): return None
    def get_cipher_text(rank_index): return "Ледник Шамана недоступен."


# ── GigaChat генераторы ───────────────────────────────────────────────────────
async def generate_rank_up_story(old_rank: dict, new_rank: dict, total_deeds: int) -> str:
    era = ("мезолитическом племени Натуфа (~11 000 до н.э.)"
           if old_rank["era"] == "natuf"
           else "раннем неолите Анатолии у Гёбекли-Тепе (~9 500 до н.э.)")
    prompt = (
        f"Напиши короткую (3-4 предложения) сцену из жизни первобытного человека. "
        f"Эпоха: {era}. "
        f"Он вырос с ранга «{old_rank['name']}» до «{new_rank['name']}». "
        f"За плечами {total_deeds} выполненных дел. "
        f"Один жест, один взгляд, одна деталь (запах, звук, ощущение). "
        f"Никакой патетики. Только земное, телесное, настоящее. "
        f"Стиль: жёсткий, короткий, без лишних слов."
    )
    return await gigachat.generate_text(prompt) or ""

async def generate_weekly_report_text(rank_name: str, week_deeds: int,
                                       total_deeds: int, era: str) -> str:
    era_label = "Натуфа" if era == "natuf" else "Анатолии"
    prompt = (
        f"Голос племени {era_label}. Итог недели для «{rank_name}»: "
        f"{week_deeds} дел за неделю, всего {total_deeds}. "
        f"2-3 предложения: достойно или нет, что это значит для выживания. "
        f"Стиль: суровый, без похвалы, без жалости. Факты и последствия."
    )
    return await gigachat.generate_text(prompt) or f"Итог недели: {week_deeds} дел."

# ── Утилиты времени ───────────────────────────────────────────────────────────
def now_msk() -> datetime:
    return datetime.now(TIMEZONE)

def today_msk() -> date:
    return now_msk().date()

def today_str() -> str:
    return today_msk().isoformat()

def parse_date(s: str) -> date:
    return date.fromisoformat(s)

# ── Логика рангов и переходов ─────────────────────────────────────────────────
def get_current_schedule_idx() -> int:
    """Возвращает индекс текущего ранга по расписанию (по дате старта)"""
    today = today_msk()
    current = 0
    for i, s in enumerate(RANK_SCHEDULE):
        if today >= parse_date(s["start"]):
            current = i
    return current

def is_holiday_mode() -> bool:
    """True если сейчас праздничный период (между start и active_from следующего ранга)"""
    today = today_msk()
    idx = get_current_schedule_idx()
    sched = RANK_SCHEDULE[idx]
    active_from = parse_date(sched["active_from"])
    start = parse_date(sched["start"])
    # Праздник = от start до active_from (не включая active_from)
    return start <= today < active_from

def is_bot_active() -> bool:
    return today_msk() < BOT_END_DATE

def is_victory_day() -> bool:
    return today_msk() == VICTORY_DATE

def effective_deeds_needed(data: dict) -> int:
    """Нужно дел для текущего ранга с учётом кэрриовера"""
    rank = get_rank_data(data["rank_index"])
    base = rank["deeds_needed"]
    carry = data.get("carry_deeds", 0)
    return max(1, base - carry)

def progress_bar(current: int, total: int, length: int = 10) -> str:
    if total <= 0:
        return "█" * length
    filled = int(length * min(current, total) / total)
    return "█" * filled + "░" * (length - filled)

# ── Данные ────────────────────────────────────────────────────────────────────
def load_data() -> dict:
    fp = DATA_DIR / "path_data.json"
    default = {
        "user_id": None,
        "rank_index": 0,
        "rank_deeds": 0,
        "carry_deeds": 0,        # кэрриовер на следующий ранг
        "total_deeds": 0,
        "current_date": None,
        "morning_done": False,
        "waiting_for_plans": False,
        "waiting_for_evening": False,
        "evening_streak": 0,
        "hunger_notified": False,
        "last_deed_time": None,
        "last_dopamine_hour": None,
        "goodnight_sent": False,
        "superhero_flag": False,
        "superhero_morning_flag": False,
        "keeper_streak": 0,
        "total_keeper_success": 0,
        "waiting_for_keeper": False,
        "victory_shown": False,
        "week_deeds": 0,
        "week_start": today_str(),
        "weekly_report_sent": False,
        "milestones_shown": [],
        "rank_transitions_shown": [],  # какие даты переходов уже объявили
        "excess_pool": 0,              # сверхдела доступные для трат
        "penalty_pool": 0,             # долг дел (дефицит прошлых рангов)
        "rewards_earned": 0,           # всего супернаград получено
    }
    try:
        if fp.exists():
            with open(fp, "r", encoding="utf-8") as f:
                saved = json.load(f)
            for k in default:
                if k not in saved:
                    saved[k] = default[k]
            return saved
        return default
    except Exception as e:
        logger.error(f"load_data: {e}")
        return default

def save_data(data: dict):
    fp = DATA_DIR / "path_data.json"
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"save_data: {e}")

def load_commandments() -> list:
    for fp in [DATA_DIR / "commandments.json", Path(__file__).parent / "commandments.json"]:
        try:
            if fp.exists():
                with open(fp, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
    return []

def get_hunger_hours(data: dict) -> float:
    if not data.get("last_deed_time"):
        return 0.0
    last = datetime.fromisoformat(data["last_deed_time"])
    if last.tzinfo is None:
        last = TIMEZONE.localize(last)
    return (now_msk() - last).total_seconds() / 3600

def get_hunger_mode(data: dict) -> str:
    h = get_hunger_hours(data)
    if h < HUNGER_WARNING_HOURS:
        return "good"
    elif h < HUNGER_RIOT_HOURS:
        return "bad"
    return "riot"

def rank_status_text(data: dict) -> str:
    idx = data["rank_index"]
    rank = get_rank_data(idx)
    deeds = data["rank_deeds"]
    needed = effective_deeds_needed(data)
    carry = data.get("carry_deeds", 0)

    era_label = "⚰️ НАТУФ" if idx < 6 else "🏛 НЕОЛИТ"
    era_num = f"Ранг {idx+1}/6" if idx < 6 else f"Ранг {idx-5}/6"
    holiday = " 🎉 ПРАЗДНИК" if is_holiday_mode() else ""

    lines = [
        f"📍 {era_label}  |  {era_num}{holiday}",
        f"🎖 {rank['name']}",
        f"💬 {rank['short']}",
        ""
    ]

    excess = data.get("excess_pool", 0)
    penalty = data.get("penalty_pool", 0)

    if idx == 11:
        lines.append("👑 ТЫ НА ВЕРШИНЕ. Созидатель места.")
        lines.append(f"⚒️ Всего дел: {data['total_deeds']}")
    else:
        bar = progress_bar(deeds, needed)
        lines.append(f"⚒️ [{bar}] {deeds}/{needed}")
        lines.append(f"📊 Всего за путь: {data['total_deeds']}/174")
        if deeds < needed:
            lines.append(f"🎯 До следующего ранга: {needed - deeds}")
        else:
            over = deeds - needed
            lines.append(f"🔥 Норма выполнена! Сверхдел сверх нормы: {over} — ждём даты перехода.")
        if excess > 0:
            lines.append(f"⚡ Пул сверхдел: {excess}  →  /reward = супернаграда")
        if penalty > 0:
            lines.append(f"🔴 Долг с прошлых рангов: {penalty} дел")

    hours = get_hunger_hours(data)
    mode = get_hunger_mode(data)
    if is_holiday_mode():
        lines.append(f"\n🎉 Праздничный режим. Отдыхай.")
    elif mode == "good":
        lines.append(f"\n✅ Активен. Без дела: {hours:.1f} ч.")
    elif mode == "bad":
        lines.append(f"\n⚠️ Пауза: {hours:.1f} ч. Действуй.")
    else:
        lines.append(f"\n🔥 КРИЗИС. {hours:.1f} ч. без дела.")

    lines.append("\n/done · /status · /rank · /path")
    return "\n".join(lines)

# ── Переход ранга (по дате) ───────────────────────────────────────────────────
ERA_TRANSITION_TEXT = """
🌍 ВЕЛИКИЙ ПЕРЕХОД

Ты прошёл Натуф. Шесть ступеней.
От падальщика до старшего у очага.

Но стоянка закрыта. Система не пускает выше.

На севере, за тремя горными хребтами,
строят из необтёсанного камня.
Сеют дикую пшеницу в борозды.
Режут горло пленникам под звёздами Гёбекли-Тепе.

Там другие боги. Другая власть. Другой страх.

Твой натуфийский опыт — багаж, не трон.
Ты приходишь как опытный чужак.
Не с нуля — но и не старшим.

Анатолия не знает тебя.
Ты должен заставить её запомнить.

🏔 ЭПОХА: РАННИЙ НЕОЛИТ ТУРЦИИ (PPN)
~9 500 до н. э. Ты — Пришедший из Леванта.
"""

async def check_date_transitions(bot, user_id: int, data: dict):
    """Проверяет нужно ли объявить переход ранга по дате"""
    today = today_msk()
    shown = data.get("rank_transitions_shown", [])

    for sched in RANK_SCHEDULE[1:]:   # пропускаем ранг 0 (старт)
        start_str = sched["start"]
        if today >= parse_date(start_str) and start_str not in shown:
            shown.append(start_str)
            data["rank_transitions_shown"] = shown

            new_idx = sched["rank_idx"]
            old_idx = data["rank_index"]

            # Считаем сверхдела и дефицит при переходе
            if new_idx > old_idx:
                needed = effective_deeds_needed(data)
                actual = data["rank_deeds"]
                diff = actual - needed  # > 0 сверхдела, < 0 дефицит

                if diff >= 0:
                    # Сверхдела: сначала закрываем долг, остаток в пул
                    penalty = data.get("penalty_pool", 0)
                    if penalty > 0:
                        cover = min(diff, penalty)
                        diff -= cover
                        data["penalty_pool"] = penalty - cover
                    data["excess_pool"] = data.get("excess_pool", 0) + diff
                else:
                    # Дефицит: добавляем в долг
                    data["penalty_pool"] = data.get("penalty_pool", 0) + abs(diff)

                # Кэрриовер = текущий excess_pool (после закрытия долга)
                data["carry_deeds"] = data.get("excess_pool", 0)
                data["rank_index"] = new_idx
                data["rank_deeds"] = 0
                save_data(data)

                new_rank = get_rank_data(new_idx)
                old_rank_data = get_rank_data(old_idx)

                # Переход Натуф → Неолит (ранг 6 → 7)
                if old_idx == 5:
                    msg = ERA_TRANSITION_TEXT
                else:
                    promo = old_rank_data.get("promotion_text", "")
                    msg = f"🔥 ПЕРЕХОД!\n\n{promo}\n\n⬆️ Теперь ты: {new_rank['name']}"

                active_from = parse_date(sched["active_from"])
                if today < active_from:
                    holiday_days = (active_from - today).days
                    msg += f"\n\n🎉 Праздничный режим: {holiday_days} дн. отдыха."

                excess_pool = data.get("excess_pool", 0)
                penalty_pool = data.get("penalty_pool", 0)
                new_needed = effective_deeds_needed(data)

                if excess_pool > 0 and penalty_pool > 0:
                    msg += (f"\n\n⚡ Сверхдел в пуле: {excess_pool}"
                            f"\n🔴 Долг закрыт частично. Остаток долга: {penalty_pool}"
                            f"\n🎯 Следующий ранг: {new_needed} дел"
                            f"\n💡 /reward — потратить сверхдело на супернаграду")
                elif excess_pool > 0:
                    msg += (f"\n\n⚡ Сверхдел в пуле: {excess_pool}"
                            f"\n🎯 Следующий ранг: {new_needed} дел"
                            f"\n💡 /reward — потратить сверхдело на супернаграду")
                elif penalty_pool > 0:
                    msg += (f"\n\n🔴 Долг перенесён: {penalty_pool} дел"
                            f"\n🎯 Следующий ранг: {new_needed} дел")

                await bot.send_message(chat_id=user_id, text=msg)

                # AI-сцена перехода
                story = await generate_rank_up_story(old_rank_data, new_rank, data["total_deeds"])
                if story:
                    await bot.send_message(chat_id=user_id, text=f"📖 {story}")

                # Картинка нового ранга
                img_prompt = new_rank.get("image_prompt")
                if img_prompt:
                    img = await gigachat.generate_image(img_prompt)
                    if img:
                        await bot.send_photo(
                            chat_id=user_id, photo=BytesIO(img),
                            caption=f"🎖 {new_rank['name']}"
                        )


# ── Команды ───────────────────────────────────────────────────────────────────
async def cmd_shaman(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Секретная команда — расшифровка Ледника Шамана"""
    data = load_data()
    rank_index = data.get("rank_index", 0)
    cipher = get_cipher_text(rank_index)
    # Отправляем как личное сообщение (одно сообщение, оно будет длинным)
    # Разбиваем если > 4000 символов
    if len(cipher) <= 4000:
        await update.message.reply_text(cipher)
    else:
        chunks = [cipher[i:i+4000] for i in range(0, len(cipher), 4000)]
        for chunk in chunks:
            await update.message.reply_text(chunk)

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    data["user_id"] = update.effective_user.id
    save_data(data)
    rank = get_rank_data(data["rank_index"])
    idx = data["rank_index"]
    era = "НАТУФИЙСКАЯ КУЛЬТУРА (~13 000 до н. э.)" if idx < 6 \
          else "РАННИЙ НЕОЛИТ ТУРЦИИ (~9 500 до н. э.)"
    needed = effective_deeds_needed(data)
    await update.message.reply_text(
        f"🏕 ПУТЬ ЧЕРЕЗ ЭПОХИ v3\n\n"
        f"📍 {era}\n"
        f"🎖 {rank['name']}\n\n"
        f"{rank['short']}\n\n"
        f"/done — дело сделано\n"
        f"/status — твой статус\n"
        f"/rank — описание ранга\n"
        f"/path — весь путь\n\n"
        f"Текущий ранг: {needed} дел до повышения.\n"
        f"Переходы по расписанию. Лишние дела — в запас."
    )

async def cmd_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_bot_active():
        await update.message.reply_text("Путь завершён.")
        return

    data = load_data()
    rank = get_rank_data(data["rank_index"])

    data["rank_deeds"] += 1
    data["total_deeds"] += 1
    data["week_deeds"] = data.get("week_deeds", 0) + 1
    data["last_deed_time"] = now_msk().isoformat()
    data["hunger_notified"] = False
    save_data(data)

    needed = effective_deeds_needed(data)
    deeds = data["rank_deeds"]
    phrase = random.choice(rank["done_phrases"])

    if is_holiday_mode():
        await update.message.reply_text(
            f"⚒️ {phrase}\n\n🎉 Праздничный режим — дело идёт в запас."
        )
        return

    # ── Выбор продукта: каждое 5-е — редкий ──────────────────────────
    is_rare = (deeds % 5 == 0)
    product_list = rank.get("rare_products" if is_rare else "products")
    if not product_list:
        product_list = rank.get("products", [])

    product_name, product_img_prompt = random.choice(product_list) if product_list else (None, None)

    # ── Текст ──────────────────────────────────────────────────────────
    if rank["deeds_needed"] > 0:
        remaining = max(0, needed - deeds)
        bar = progress_bar(deeds, needed)
        rare_mark = "🌟 " if is_rare else ""
        if product_name:
            msg = f"⚒️ {phrase}\n\n{rare_mark}Ты создал: {product_name}\n\n[{bar}] {deeds}/{needed}"
        else:
            msg = f"⚒️ {phrase}\n\n[{bar}] {deeds}/{needed}"
        if remaining > 0:
            msg += f"\nДо ранга: {remaining}"
        else:
            msg += f"\n🔥 Дел накоплено с запасом! Ждём даты перехода."
    else:
        rare_mark = "🌟 " if is_rare else ""
        if product_name:
            msg = f"👑 {phrase}\n\n{rare_mark}Ты создал: {product_name}"
        else:
            msg = f"👑 {phrase}"

    await update.message.reply_text(msg)

    # ── Картинка GigaChat ──────────────────────────────────────────────
    if product_img_prompt:
        img = await gigachat.generate_image(product_img_prompt)
        if img:
            caption = f"{'🌟 ' if is_rare else ''}{product_name}"
            await update.message.reply_photo(photo=BytesIO(img), caption=caption)

    # ── Вехи ──────────────────────────────────────────────────────────
    total = data["total_deeds"]
    shown = data.get("milestones_shown", [])
    if total in MILESTONES and total not in shown:
        shown.append(total)
        data["milestones_shown"] = shown
        save_data(data)
        await update.message.reply_text(MILESTONES[total])

async def cmd_tried(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    data["last_deed_time"] = now_msk().isoformat()
    data["hunger_notified"] = False
    save_data(data)
    phrases = [
        "Попытка — не провал. Огонь сохранён.",
        "Ты старался. Это засчитано в кости.",
        "Иногда попытка — это всё, что есть. Принято.",
        "Работа была. Результата нет. Продолжай."
    ]
    await update.message.reply_text(random.choice(phrases))

async def cmd_penalty(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    data["rank_deeds"] = max(0, data["rank_deeds"] - 1)
    data["total_deeds"] = max(0, data["total_deeds"] - 1)
    save_data(data)
    rank = get_rank_data(data["rank_index"])
    deeds = data["rank_deeds"]
    needed = effective_deeds_needed(data)
    phrases = [
        "💀 Ошибка стоила дела. -1 к прогрессу.",
        "❌ Провал засчитан. Шаг назад.",
        "🩸 Цена неудачи — откат. Будь точнее.",
        "⚠️ Один шаг назад. Племя недовольно."
    ]
    bar = progress_bar(deeds, needed) if rank["deeds_needed"] > 0 else ""
    msg = random.choice(phrases)
    if bar:
        msg += f"\n[{bar}] {deeds}/{needed}"
    await update.message.reply_text(msg)

async def cmd_penalty20(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Жёсткий штраф — откат на 3 дела (катастрофа)"""
    data = load_data()
    data["rank_deeds"] = max(0, data["rank_deeds"] - 3)
    data["total_deeds"] = max(0, data["total_deeds"] - 3)
    save_data(data)
    rank = get_rank_data(data["rank_index"])
    deeds = data["rank_deeds"]
    needed = effective_deeds_needed(data)
    hard_penalties = [
        "💥 Катастрофа! Всё рухнуло. -3 дела.",
        "🌊 Смыло всё. Откат на три шага назад.",
        "❄️ Три дня потеряно. Племя в ярости.",
        "🐻 Разорил всё. -3 к прогрессу.",
        "⚡ Удар судьбы. Три дела сгорели."
    ]
    bar = progress_bar(deeds, needed) if rank["deeds_needed"] > 0 else ""
    msg = random.choice(hard_penalties)
    if bar:
        msg += f"\n[{bar}] {deeds}/{needed}"
    await update.message.reply_text(msg)

async def cmd_reward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Потратить 1 сверхдело на супернаграду"""
    data = load_data()
    excess = data.get("excess_pool", 0)

    if excess <= 0:
        penalty = data.get("penalty_pool", 0)
        if penalty > 0:
            await update.message.reply_text(
                f"❌ Сверхдел нет. У тебя долг: {penalty} дел.\n"
                f"Сначала перекрой долг — потом награды."
            )
        else:
            await update.message.reply_text(
                "❌ Сверхдел нет. Сделай больше нормы ранга — тогда появятся."
            )
        return

    # Тратим 1 сверхдело
    data["excess_pool"] = excess - 1
    data["carry_deeds"] = max(0, data.get("carry_deeds", 0) - 1)
    data["rewards_earned"] = data.get("rewards_earned", 0) + 1
    rewards_total = data["rewards_earned"]
    save_data(data)

    rank = get_rank_data(data["rank_index"])
    remaining = data["excess_pool"]

    # Текст зависит от ранга — тематика награды разная
    if rank["era"] == "natuf":
        flavor = random.choice([
            "Старший стоянки кивнул. Ты знаешь, что взять.",
            "Племя в твоём долгу. Бери что заработал.",
            "Охотник получает трофей. Ты знаешь какой.",
            "Добыча твоя. Ты это заслужил — без объяснений.",
            "Костёр горит для тебя сегодня. Бери своё.",
        ])
    else:
        flavor = random.choice([
            "Хозяин житницы знает свою цену. Бери.",
            "Созидатель берёт то, что ему причитается.",
            "Зерно убрано. Награда заработана. Ты знаешь какая.",
            "Анатолия щедра к тем, кто строит. Возьми своё.",
            "Мастер получает то, что мастер хочет.",
        ])

    msg = (
        f"🎁 СУПЕРНАГРАДА #{rewards_total}\n\n"
        f"{flavor}\n\n"
        f"⚡ Сверхдел в пуле: {remaining}"
    )
    if remaining > 0:
        msg += f"\n💡 /reward — ещё одна супернаграда"

    await update.message.reply_text(msg)

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    await update.message.reply_text(rank_status_text(data))

async def cmd_rank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    idx = data["rank_index"]
    rank = get_rank_data(idx)
    era = "Натуфийская культура" if idx < 6 else "Ранний неолит Турции"
    era_pos = f"Ранг {idx+1}/6" if idx < 6 else f"Ранг {idx-5}/6"
    deeds = data["rank_deeds"]
    needed = effective_deeds_needed(data)
    carry = data.get("carry_deeds", 0)
    bar = f"[{progress_bar(deeds, needed)}] {deeds}/{needed}" if rank["deeds_needed"] > 0 else "👑 Вершина"
    carry_info = f"\n⚡ Кэрриовер из прошлого ранга: -{carry}" if carry > 0 else ""
    await update.message.reply_text(
        f"📜 {era}  |  {era_pos}\n"
        f"🎖 {rank['name']}\n\n"
        f"{rank['full']}\n\n"
        f"⚒️ {bar}{carry_info}"
    )

async def cmd_path(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    current_idx = data["rank_index"]
    lines = ["🗺 ПУТЬ ЧЕРЕЗ ЭПОХИ\n", "═══ НАТУФИЙСКАЯ КУЛЬТУРА ═══"]
    for i in range(6):
        r = get_rank_data(i)
        sched = RANK_SCHEDULE[i]
        date_info = f"  [{sched['start']}]"
        if i < current_idx:
            lines.append(f"✅ {i+1}. {r['name']}{date_info}")
        elif i == current_idx:
            d = data["rank_deeds"]
            n = effective_deeds_needed(data)
            lines.append(f"▶️ {i+1}. {r['name']} [{d}/{n}]{date_info} ← ТЫ ЗДЕСЬ")
        else:
            lines.append(f"⬜ {i+1}. {r['name']}{date_info}")
    lines.append("\n═══ РАННИЙ НЕОЛИТ ТУРЦИИ ═══")
    for i in range(6):
        idx = i + 6
        r = get_rank_data(idx)
        sched = RANK_SCHEDULE[idx]
        date_info = f"  [{sched['start']}]"
        if idx < current_idx:
            lines.append(f"✅ {i+1}. {r['name']}{date_info}")
        elif idx == current_idx:
            d = data["rank_deeds"]
            n = effective_deeds_needed(data)
            lines.append(f"▶️ {i+1}. {r['name']} [{d}/{n}]{date_info} ← ТЫ ЗДЕСЬ")
        else:
            lines.append(f"⬜ {i+1}. {r['name']}{date_info}")
    lines.append(f"\n📊 Всего дел: {data['total_deeds']}/174")
    await update.message.reply_text("\n".join(lines))

# ── Главный таймер ────────────────────────────────────────────────────────────
async def main_timer(context: ContextTypes.DEFAULT_TYPE):
    if not is_bot_active():
        return

    data = load_data()
    user_id = data.get("user_id")
    if not user_id:
        return

    now = now_msk()
    h, m = now.hour, now.minute
    wd = now.weekday()  # 0=пн

    rank = get_rank_data(data["rank_index"])
    era = rank["era"]
    holiday = is_holiday_mode()

    # ── Сброс дня ──
    if data.get("current_date") != today_str():
        data["current_date"] = today_str()
        data["morning_done"] = False
        data["waiting_for_plans"] = False
        data["waiting_for_evening"] = False
        data["hunger_notified"] = False
        data["last_dopamine_hour"] = None
        data["goodnight_sent"] = False
        data["superhero_flag"] = False
        data["superhero_morning_flag"] = False
        data["waiting_for_keeper"] = False
        data["weekly_report_sent"] = False
        save_data(data)

    # ── Проверка перехода по дате ──
    await check_date_transitions(context.bot, user_id, data)
    data = load_data()  # перечитываем после возможного перехода
    rank = get_rank_data(data["rank_index"])
    era = rank["era"]

    # ── 05:30 — Утро ──
    if h == WAKEUP_HOUR and m == WAKEUP_MINUTE and not data.get("morning_done"):
        commandments = load_commandments()
        if commandments:
            short_list = "\n".join([f"{c['id']}. {c['short']}" for c in commandments])
            if holiday:
                morning = f"🌅 Рассвет. Праздник, {rank['name']}. Отдыхай — но заповеди помни:\n\n{short_list}"
            else:
                morning = (
                    f"📜 ЗАПОВЕДИ:\n{short_list}\n\n"
                    f"🌅 Рассвет. {rank['name']}.\n"
                    f"У тебя есть 4 дела на сегодня? (есть/нет)"
                )
        else:
            morning = f"🌅 Рассвет. {rank['name']}. Четыре дела написал? (есть/нет)"

        await context.bot.send_message(chat_id=user_id, text=morning)
        data["morning_done"] = True
        if not holiday:
            data["waiting_for_plans"] = True
        save_data(data)

    # ── 04:00 Пн–Пт — Супергерой ──
    if h == 4 and m == 0 and wd < 5 and not holiday:
        data["superhero_morning_flag"] = False  # сбрасываем — начинаем с нуля
        save_data(data)
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                "🌑 Рассвет ещё не пришёл. Племя спит.\n"
                "У тебя 90 минут тишины — до побудки.\n"
                "Одно дело в темноте стоит трёх на свету.\n"
                "Это время Супергероя."
            )
        )

    # ── 09:00 Пн–Пт ──
    if h == 9 and m == 0 and wd < 5:
        if holiday:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"🎉 Праздничное утро. {rank['name']} отдыхает — но не теряет форму."
            )
        else:
            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    f"⚒️ Дневная смена. {rank['name']}.\n"
                    "Делай рабочие дела крепко и спокойно.\n"
                    "Если будет окно — один денежный шаг: цифры, идея, стратегия."
                )
            )

    # ── 18:00 Пн–Пт ──
    if h == 18 and m == 0 and wd < 5:
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                "🏕️ Очаг семьи уже горит.\n"
                "Возвращайся не только телом — и сердцем.\n"
                "Одно живое действие для близких."
            )
        )

    # ── 21:00 — Вечерний чек ──
    if h == 21 and m == 0 and not data.get("waiting_for_keeper"):
        deeds = data["rank_deeds"]
        needed = effective_deeds_needed(data)
        streak = data.get("keeper_streak", 0)
        streak_info = f"\n🔥 Серия: {streak} дней" if streak > 0 else ""
        if holiday:
            eve_text = f"🌙 Вечер праздника. {rank['name']}. Ты сдержал сегодня соглашение с собой? (сдержал/сорвал)"
        elif rank["deeds_needed"] > 0:
            bar = f"[{progress_bar(deeds, needed)}] {deeds}/{needed}"
            eve_text = (
                f"🌙 Вечер у костра. {rank['name']}.\n"
                f"{bar}{streak_info}\n\n"
                f"Ты сдержал сегодня соглашение с собой? (сдержал/сорвал)"
            )
        else:
            eve_text = f"🌙 Вечер. {rank['name']}{streak_info}. Ты сдержал соглашение? (сдержал/сорвал)"
        await context.bot.send_message(chat_id=user_id, text=eve_text)
        data["waiting_for_keeper"] = True
        save_data(data)

    # ── 21:30 Пн–Пт — Мультимиллионер / добивка Супергероя ──
    if h == 21 and m == 30 and wd < 5:
        if data.get("superhero_morning_flag"):
            msg = (
                "🔥 Ночная мастерская открыта. Есть искра — выходит Мультимиллионер.\n"
                "Один денежный шаг: идея, таблица, план, контроль.\n"
                "Не строй империю за ночь. Положи один слиток в будущее."
            )
        else:
            msg = (
                "🦶 Утренний выход Супергероя пропущен.\n"
                "Сначала — знание, потом — золото.\n"
                "15 минут на главное дело. Сначала копьё, потом сундук."
            )
        await context.bot.send_message(chat_id=user_id, text=msg)

    # ── 08:00 Суббота — Супергерой ──
    if h == 8 and m == 0 and wd == 5:
        data["superhero_flag"] = True
        save_data(data)
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                f"📜 День большой охоты. {rank['name']}.\n"
                "Суббота — день Супергероя. Не обязательно тащить всего мамонта.\n"
                "Но нужен настоящий заход: текст, таблица, правка, источники.\n"
                "Сегодня добываешь не мясо — а будущее имя."
            )
        )

    # ── 09:00 Воскресенье ──
    if h == 9 and m == 0 and wd == 6:
        await context.bot.send_message(
            chat_id=user_id,
            text="💰 Утро Мультимиллионера. Один денежный шаг сегодня важнее десяти фантазий."
        )

    # ── 15:00 Воскресенье ──
    if h == 15 and m == 0 and wd == 6:
        await context.bot.send_message(
            chat_id=user_id,
            text="🌿 Воскресный очаг зовёт. После обеда главное — семья, тепло и присутствие."
        )

    # ── 23:00 — Спокойной ночи ──
    if h == 23 and m == 0 and not data.get("goodnight_sent"):
        data["goodnight_sent"] = True
        save_data(data)
        deeds = data["rank_deeds"]
        needed = effective_deeds_needed(data)
        remaining = max(0, needed - deeds) if rank["deeds_needed"] > 0 else 0
        if remaining > 0:
            night_msg = f"🌙 Спокойной ночи. {rank['name']}. До повышения: {remaining} дел."
        elif rank["deeds_needed"] == 0:
            night_msg = "🌙 Спокойной ночи, Созидатель."
        else:
            night_msg = f"🌙 Спокойной ночи. {rank['name']}. Запас дел создан — ждём дату перехода."

        img_prompt = rank.get("image_prompt")
        if img_prompt:
            img = await gigachat.generate_image(img_prompt + ", ночное небо, звёзды, тихо")
            if img:
                await context.bot.send_photo(
                    chat_id=user_id, photo=BytesIO(img), caption=night_msg
                )
                return
        await context.bot.send_message(chat_id=user_id, text=night_msg)

    # ── Пн 08:00 — Недельный отчёт ──
    if wd == 0 and h == 8 and m == 0 and not data.get("weekly_report_sent"):
        data["weekly_report_sent"] = True
        week_deeds = data.get("week_deeds", 0)
        report_text = await generate_weekly_report_text(
            rank["name"], week_deeds, data["total_deeds"], era
        )
        if week_deeds == 0:
            header = "📉 НЕДЕЛЯ\n⚒️ Дел: 0. Племя недовольно."
        elif week_deeds < 5:
            header = f"📊 НЕДЕЛЯ\n⚒️ Дел: {week_deeds}. Слабая неделя."
        elif week_deeds < 10:
            header = f"📊 НЕДЕЛЯ\n⚒️ Дел: {week_deeds}. Рабочая неделя."
        else:
            header = f"📊 НЕДЕЛЯ\n⚒️ Дел: {week_deeds}. Сильная неделя."

        await context.bot.send_message(
            chat_id=user_id,
            text=f"{header}\n\n{report_text}\n\n📈 Путь: {data['total_deeds']}/174"
        )

        if week_deeds >= 7:
            img_prompt = rank.get("image_prompt")
            if img_prompt:
                img = await gigachat.generate_image(
                    img_prompt + ", итог недели, семь дел, стойкость"
                )
                if img:
                    await context.bot.send_photo(
                        chat_id=user_id, photo=BytesIO(img),
                        caption=f"🏆 {week_deeds} дел за неделю."
                    )

        data["week_deeds"] = 0
        data["week_start"] = today_str()
        save_data(data)

    # ── Дофамин в :55 нечётных часов ──
    if m == 55 and DOPAMINE_START <= h <= DOPAMINE_END and h % 2 != 0:
        if data.get("last_dopamine_hour") != h:
            data["last_dopamine_hour"] = h
            save_data(data)
            reward = get_dopamine_reward(era=era)
            await context.bot.send_message(chat_id=user_id, text=reward)
            commandments = load_commandments()
            if commandments:
                cmd = random.choice(commandments)
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"📜 {cmd['id']}. {cmd['short']} — {cmd['full']}"
                )

    # ── Голод / бунт (не в праздник) ──
    if not holiday:
        mode = get_hunger_mode(data)
        if mode == "riot" and m in [0, 30]:
            hours = get_hunger_hours(data)
            riots = [
                f"🔥 КРИЗИС. {rank['name']} — уже {hours:.0f} ч. без дела.",
                f"🔥 Племя теряет терпение. {rank['name']} — действуй.",
                f"🔥 Застрял. {rank['name']} требует работы. Прямо сейчас."
            ]
            await context.bot.send_message(chat_id=user_id, text=random.choice(riots))
        elif mode == "bad" and not data.get("hunger_notified"):
            data["hunger_notified"] = True
            save_data(data)
            await context.bot.send_message(
                chat_id=user_id,
                text=f"⚠️ {rank['name']} — пауза затянулась. Действуй, пока не поздно."
            )

    # ── 31 декабря — победа по дате ──
    if is_victory_day() and h == 10 and m == 0 and not data.get("victory_shown"):
        data["victory_shown"] = True
        save_data(data)
        rank12 = get_rank_data(11)
        vtexts = rank12.get("victory_texts", [])
        msg1 = vtexts[0] if vtexts else "🗿 31 ДЕКАБРЯ. ПУТЬ ЗАВЕРШЁН."
        msg2 = (vtexts[1] if len(vtexts) > 1 else "") + f"\n\n⚒️ Всего дел за год: {data['total_deeds']}\n🎉 С Новым Годом."
        await context.bot.send_message(chat_id=user_id, text=msg1)
        await context.bot.send_message(chat_id=user_id, text=msg2)
        final_prompt = rank12.get("image_prompt")
        if final_prompt:
            img = await gigachat.generate_image(final_prompt)
            if img:
                await context.bot.send_photo(
                    chat_id=user_id, photo=BytesIO(img),
                    caption="🗿 Созидатель места. Конец пути."
                )

    # ── Ранний финал (ранг 12 достигнут до 31 декабря) ──
    if data["rank_index"] == 11 and not data.get("victory_shown") and not is_victory_day():
        data["victory_shown"] = True
        save_data(data)
        rank12 = get_rank_data(11)
        vtexts = rank12.get("victory_texts", [])
        msg1 = vtexts[0] if vtexts else "👑 СОЗИДАТЕЛЬ МЕСТА\n\nПуть завершён досрочно."
        msg2 = vtexts[1] if len(vtexts) > 1 else "Ты — первый тиран. Гёбекли-Тепе помнит тебя."
        await context.bot.send_message(chat_id=user_id, text=msg1)
        await context.bot.send_message(chat_id=user_id, text=msg2)
        early_prompt = rank12.get("image_prompt")
        if early_prompt:
            img = await gigachat.generate_image(early_prompt)
            if img:
                await context.bot.send_photo(
                    chat_id=user_id, photo=BytesIO(img),
                    caption="🗿 Созидатель места."
                )

# ── Обработка текста ──────────────────────────────────────────────────────────
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower().strip()
    data = load_data()
    if not data.get("user_id"):
        data["user_id"] = update.effective_user.id
        save_data(data)

    if data.get("waiting_for_keeper"):
        if any(w in text for w in ["сдержал", "yes", "конечно", "выполнено", "да"]):
            data["keeper_streak"] = data.get("keeper_streak", 0) + 1
            data["total_keeper_success"] = data.get("total_keeper_success", 0) + 1
            data["waiting_for_keeper"] = False
            save_data(data)
            rank = get_rank_data(data["rank_index"])
            success_text = await generate_keeper_success_text(data["keeper_streak"], rank["name"])
            await update.message.reply_text(
                f"✅ Зафиксировано.\n\n{success_text}\n🔥 Серия: {data['keeper_streak']} дней"
            )
        elif any(w in text for w in ["сорвал", "no", "не выполнено", "нет", "нету"]):
            old_streak = data.get("keeper_streak", 0)
            data["keeper_streak"] = 0
            data["waiting_for_keeper"] = False
            save_data(data)
            await update.message.reply_text(
                f"❌ Соглашение не выдержано.\n"
                f"Серия сброшена (было: {old_streak}).\n"
                f"Социальное напряжение в племени растёт."
            )
        else:
            await update.message.reply_text("Ответь: 'сдержал' или 'сорвал'")
        return

    if data.get("waiting_for_plans"):
        if any(w in text for w in ["есть", "да", "yes", "готово"]):
            data["waiting_for_plans"] = False
            data["superhero_morning_flag"] = True  # план есть — флаг Супергероя активен
            save_data(data)
            rank = get_rank_data(data["rank_index"])
            await update.message.reply_text(f"✅ Отлично, {rank['name']}! План есть — племя будет сыто.")
            # Рассветная картинка через GigaChat
            rank_img = rank.get("image_prompt", "")
            if rank_img:
                sunrise_prompt = rank_img.replace("ночь", "рассвет").replace("ночное", "рассветное")
            else:
                sunrise_prompt = f"Рассвет у стоянки первобытного человека, {rank['name']}, начало нового дня, оптимизм, реализм"
            img = await gigachat.generate_image(sunrise_prompt + ", золотой свет, новый день")
            if img:
                await update.message.reply_photo(photo=BytesIO(img), caption="🌅 Рассвет. День начат.")
            else:
                await update.message.reply_text("🌅 Рассвет. Начинай.")
        elif any(w in text for w in ["нет", "no", "не", "нету"]):
            data["waiting_for_plans"] = False
            save_data(data)
            await update.message.reply_text(
                "📝 Запиши 4 дела прямо сейчас. Без списка — без движения."
            )
        else:
            await update.message.reply_text("Есть 4 дела? (есть/нет)")
        return

    if any(w in text for w in ["сделал", "готово", "сделала", "done"]):
        await cmd_done(update, context)
    elif any(w in text for w in ["попробовал", "старался", "tried", "пыт"]):
        await cmd_tried(update, context)
    elif "неудач" in text or "плохо" in text or "провал" in text:
        await cmd_penalty(update, context)
    elif any(w in text for w in ["статус", "status"]):
        await cmd_status(update, context)

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not BOT_TOKEN:
        logger.error("No BOT_TOKEN!")
        return

    preload_ranks()

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("done",    cmd_done))
    app.add_handler(CommandHandler("tried",   cmd_tried))
    app.add_handler(CommandHandler("penalty", cmd_penalty))
    app.add_handler(CommandHandler("penalty20", cmd_penalty20))
    app.add_handler(CommandHandler("reward",   cmd_reward))
    app.add_handler(CommandHandler("status",  cmd_status))
    app.add_handler(CommandHandler("rank",    cmd_rank))
    app.add_handler(CommandHandler("path",    cmd_path))
    app.add_handler(CommandHandler("шаман",   cmd_shaman))
    app.add_handler(CommandHandler("shaman",  cmd_shaman))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.job_queue.run_repeating(main_timer, interval=60, first=10)

    logger.info("Путь через эпохи v3.0 запущен")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
