# =========================================
# Aura | Онлайн-психолог — ОДИН ФАЙЛ (расширенная версия)
# =========================================
# Что добавлено по сравнению с исходником:
# - 🧘 Медитации: команда /meditation и кнопка в меню.
#   Отправляет бесплатные аудио-файлы из локальной папки или по URL,
#   кэширует file_id Telegram для мгновенной повторной отправки.
# - 👥 Реферальная система «как у взрослых»:
#   * Персональный код по соль-шифру tg_id → /start ref<code>
#   * Учет клика и «регистрации» (join) в БД
#   * Бонусы: приглашённому — сразу N дней; пригласившему — после оплаты (демо: при клике «оплатить»)
#   * /referrals — сводка, ссылка приглашения, статусы
# - Небольшие улучшения логов/команд.
#
# Новые переменные окружения (опционально):
# - AUDIO_DIR                — путь к папке с медитациями (mp3/m4a/ogg). По умолчанию ./meditations рядом со скриптом
# - AUDIO_BASE_URL           — если хотите раздавать аудио с CDN/сайта (пример: https://cdn.example.com/meditations)
# - REF_SALT                 — целое число-соль для кодирования реф.кодов (по умолчанию 8349271)
# - REF_BONUS_DAYS_JOINED    — сколько дней дарить приглашённому (по умолчанию 7)
# - REF_BONUS_DAYS_PAID      — сколько дней дарить пригласившему после оплаты друга (по умолчанию 7)
#
# Куда класть аудио:
# - Создайте папку "meditations" рядом с этим файлом и положите туда .mp3/.m4a/.ogg.
#   Например: ./meditations/breath_3min.mp3, ./meditations/body_scan_7min.mp3
#   Имена кнопок формируются из имён файлов (подчёркивания/дефисы → пробелы).
# - Либо укажите AUDIO_BASE_URL и храните файлы на своём хостинге/CDN.
#   Пример: AUDIO_BASE_URL="https://cdn.example.com/meditations" → бот будет слать URL вида .../body_scan_7min.mp3

import os
import re
import json
import time
import asyncio
from typing import Optional, Dict, Any, List, Tuple

# Попробуем прочитать .env, если установлен python-dotenv (не обязательно)
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass

# -------------------------
# 1) НАСТРОЙКИ
# -------------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
DEEPSEEK_API_KEY   = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL  = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
DEEPSEEK_MODEL     = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
DATABASE_URL       = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///aura.db")  # просто, без Postgres
REDIS_URL          = os.getenv("REDIS_URL")  # если есть — используем для антиспама/временных состояний

# Новые настройки аудио/рефералок
AUDIO_DIR          = os.getenv("AUDIO_DIR", os.path.join(os.path.dirname(__file__), "meditations"))
AUDIO_BASE_URL     = (os.getenv("AUDIO_BASE_URL") or "").rstrip("/") or None

REF_SALT                 = int(os.getenv("REF_SALT", "8349271"))
REF_BONUS_DAYS_JOINED    = int(os.getenv("REF_BONUS_DAYS_JOINED", "7"))
REF_BONUS_DAYS_PAID      = int(os.getenv("REF_BONUS_DAYS_PAID", "7"))

if not TELEGRAM_BOT_TOKEN:
    raise SystemExit("❌ Не задан TELEGRAM_BOT_TOKEN (создайте бота в BotFather и вставьте токен).")

# -------------------------
# 2) ТЕКСТЫ И РОЛИ (редактируйте тут)
# -------------------------
STYLE_SYSTEM = (
    "Тон: тёплая, простая поддержка. Техники: активное слушание, отражение, нормализация, "
    "микро-шаг на 10–15 минут. Без диагнозов и лекарств. Если тяжело — мягко предложи ресурсы.\n"
    "Формат: 2–5 коротких абзацев, без сложных слов. Заверши вопросом или мини-шагом."
)

PERSONAS: Dict[str, Dict[str, str]] = {
    "pro_psychologist": {
        "title": "🎓 Психолог (проф.)",
        "system": (
            "Ты — профессиональный психолог-консультант. "
            "Говори просто, объясняй «зачем» задаёшь вопрос. "
            "Используй мягкие вопросы, давай 2–3 варианта выбора."
        ),
    },
    "mentor_growth": {
        "title": "🌱 Наставница развития",
        "system": (
            "Ты — наставница. Фокус на целях и ценностях. "
            "Помогай дробить большие задачи на микро-шаги (10–15 минут)."
        ),
    },
    "friend_fun": {
        "title": "💬 Подружка-хахатушка",
        "system": (
            "Ты — тёплая подружка. Чуть-чуть юмора уместно. "
            "Поддерживай, не обесценивай. В тяжёлых темах — мягче."
        ),
    },
}

CRISIS_TEXT = (
    "Похоже, сейчас очень тяжело. Я рядом, но я не служба экстренной помощи.\n\n"
    "Если есть риск навредить себе или кому-то — пожалуйста, позвоните **112** (экстренные службы, бесплатно, круглосуточно по РФ).\n"
    "Экстренная психологическая помощь МЧС: **+7 (495) 989-50-50**. Москва — 051 / +7 (495) 051.\n"
    "Детям/подросткам: **8-800-2000-122** (короткий **124** у мобильных).\n"
    "Для женщин, пострадавших от насилия: **8-800-7000-600**.\n\n"
    "Если хотите, составим план безопасности на ближайший час: 1) где вы, 2) кто рядом, 3) что снизит остроту на 10%?"
)

# -------------------------
# 3) БАЗА ДАННЫХ (SQLite по умолчанию)
#    Храним: пользователей, дневник, результаты тестов, события, кэш медиа, рефералы, бонусы.
# -------------------------
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Integer, DateTime, ForeignKey, Text, JSON, Boolean, select, text as sqltext, func

engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)

class Base(AsyncAttrs, DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[int]       = mapped_column(Integer, primary_key=True)
    tg_id: Mapped[str]    = mapped_column(String, unique=True, index=True)
    username: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    persona: Mapped[str]  = mapped_column(String, default="pro_psychologist")
    plan: Mapped[str]     = mapped_column(String, default="LIGHT")
    created_at: Mapped[Any] = mapped_column(DateTime(timezone=True), server_default=func.now())

class JournalEntry(Base):
    __tablename__ = "journal_entries"
    id: Mapped[int]       = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int]  = mapped_column(Integer, ForeignKey("users.id"), index=True)
    created_at: Mapped[Any] = mapped_column(DateTime(timezone=True), server_default=func.now())
    mood: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

class ScaleResult(Base):
    __tablename__ = "scale_results"
    id: Mapped[int]       = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int]  = mapped_column(Integer, ForeignKey("users.id"), index=True)
    scale: Mapped[str]    = mapped_column(String)  # PHQ9 | GAD7
    score: Mapped[int]    = mapped_column(Integer)
    answers: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[Any] = mapped_column(DateTime(timezone=True), server_default=func.now())

class EventLog(Base):
    __tablename__ = "event_logs"
    id: Mapped[int]       = mapped_column(Integer, primary_key=True)
    user_tg_id: Mapped[str] = mapped_column(String, index=True)
    event: Mapped[str]    = mapped_column(String)  # message_sent, ai_reply, crisis_detected ...
    payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[Any] = mapped_column(DateTime(timezone=True), server_default=func.now())

# Новые таблицы
class MediaCache(Base):
    __tablename__ = "media_cache"
    id: Mapped[int]       = mapped_column(Integer, primary_key=True)
    key: Mapped[str]      = mapped_column(String, unique=True, index=True)  # например, med:<slug>
    file_id: Mapped[str]  = mapped_column(String)  # Telegram file_id
    created_at: Mapped[Any] = mapped_column(DateTime(timezone=True), server_default=func.now())

class Referral(Base):
    __tablename__ = "referrals"
    id: Mapped[int]            = mapped_column(Integer, primary_key=True)
    code: Mapped[str]          = mapped_column(String, index=True)              # реф.код, с которым пришёл пользователь
    referrer_tg_id: Mapped[str]= mapped_column(String, index=True)              # кто пригласил
    referred_tg_id: Mapped[Optional[str]] = mapped_column(String, index=True, nullable=True)  # кто пришёл
    status: Mapped[str]        = mapped_column(String)  # clicked | joined | paid | self | invalid
    created_at: Mapped[Any]    = mapped_column(DateTime(timezone=True), server_default=func.now())

class UserBonus(Base):
    __tablename__ = "user_bonuses"
    id: Mapped[int]            = mapped_column(Integer, primary_key=True)
    user_tg_id: Mapped[str]    = mapped_column(String, index=True)
    type: Mapped[str]          = mapped_column(String)  # ref_join, ref_paid, promo и т.п.
    days: Mapped[int]          = mapped_column(Integer, default=0)
    activated: Mapped[bool]    = mapped_column(Boolean, default=True)
    payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # контекст (кто кого привёл и т.д.)
    created_at: Mapped[Any]    = mapped_column(DateTime(timezone=True), server_default=func.now())
    activated_at: Mapped[Optional[Any]] = mapped_column(DateTime(timezone=True), nullable=True)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# -------------------------
# 4) ПРОСТОЙ ЛОГ СОБЫТИЙ (с очисткой телефонов/e-mail)
# -------------------------
def _redact_pii(obj: Optional[dict]) -> Optional[dict]:
    if not obj:
        return obj
    text = json.dumps(obj, ensure_ascii=False)
    text = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[email]", text)
    text = re.sub(r"(\+?\d[\d\s\-()]{8,}\d)", "[phone]", text)
    return {"text": text}

async def log_event(user_tg_id: str, event: str, payload: Optional[dict] = None):
    async with SessionLocal() as s:
        s.add(EventLog(user_tg_id=user_tg_id, event=event, payload=_redact_pii(payload)))
        await s.commit()

# -------------------------
# 5) АНТИСПАМ И ДЕДУП (Redis ИЛИ in-memory)
# -------------------------
_redis = None
if REDIS_URL:
    try:
        import redis.asyncio as redis  # type: ignore
        _redis = redis.from_url(REDIS_URL, decode_responses=True)
    except Exception:
        _redis = None

_recent_hashes: Dict[str, float] = {}  # in-memory TTL по ключу user:text

async def is_duplicate(user_id: int, text: str, ttl_sec: int = 30) -> bool:
    if not text:
        return False
    key = f"{user_id}:{hash(text.strip())}"
    now = time.time()
    if _redis:
        exists = await _redis.exists(f"anti:{key}")
        if exists:
            return True
        await _redis.setex(f"anti:{key}", ttl_sec, "1")
        return False
    # in-memory
    if key in _recent_hashes and now - _recent_hashes[key] < ttl_sec:
        return True
    _recent_hashes[key] = now
    return False

_user_minute_counts: Dict[str, int] = {}
_user_minute_ts: Dict[str, int] = {}

async def rate_limited(user_id: int, max_per_minute: int = 20) -> bool:
    now_min = int(time.time() // 60)
    uid = str(user_id)
    if _redis:
        # простой вариант в Redis
        key = f"rate:{uid}:{now_min}"
        cnt = await _redis.incr(key)
        await _redis.expire(key, 60)
        return cnt > max_per_minute
    # in-memory
    last = _user_minute_ts.get(uid)
    if last != now_min:
        _user_minute_ts[uid] = now_min
        _user_minute_counts[uid] = 0
    _user_minute_counts[uid] = _user_minute_counts.get(uid, 0) + 1
    return _user_minute_counts[uid] > max_per_minute

# -------------------------
# 6) ОБНАРУЖЕНИЕ ОПАСНЫХ ФРАЗ (кризис)
# -------------------------
def detect_risk(text: str) -> Optional[str]:
    if not text:
        return None
    patterns_suicide = [
        r"\b(хочу|думаю|планирую)\s+(умереть|сдохнуть|покончить\s+с\s+собой)\b",
        r"\b(не\s+хочу\s+жить|жить\s+не\s+хочу)\b",
        r"\b(суицид|самоубийств[оа])\b",
        r"\b(порезать\s*ся|повесить\s*ся|перерезать\s*вены)\b",
        r"\b(навредить|вредить)\s+себе\b",
    ]
    patterns_violence = [r"\b(убить|навредить)\s+(его|ее|их|человеку|людям)\b"]
    for p in patterns_suicide:
        if re.search(p, text, re.IGNORECASE | re.UNICODE):
            return "suicide"
    for p in patterns_violence:
        if re.search(p, text, re.IGNORECASE | re.UNICODE):
            return "violence"
    return None

# -------------------------
# 7) «МОЗГ» ДЛЯ ОТВЕТОВ (DeepSeek через HTTP)
# -------------------------
import httpx

async def deepseek_reply(messages: List[Dict[str, str]], temperature: float = 0.6, max_tokens: int = 600) -> str:
    # Если нет ключа — вернём мягкий заглушечный ответ (бот не сломается)
    if not DEEPSEEK_API_KEY:
        return "Я здесь, чтобы поддержать. Расскажите, что сейчас больше всего хочется прояснить? (подключите DEEPSEEK_API_KEY для умного ответа)"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{DEEPSEEK_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
                json={"model": DEEPSEEK_MODEL, "messages": messages, "temperature": temperature, "max_tokens": max_tokens},
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
    except Exception:
        return "Сейчас мне трудно ответить из-за перегрузки. Давайте попробуем ещё раз через минутку. Я рядом."

# -------------------------
# 8) TELEGRAM-БОТ (aiogram 3)
# -------------------------
from aiogram import Bot, Dispatcher, Router, F
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import (
    Message, BotCommand,
    KeyboardButton, ReplyKeyboardMarkup,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, FSInputFile
)

bot = Bot(token=TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
dp = Dispatcher()

# Главное меню (кнопки)
MAIN_KB = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🧠 Сессия"), KeyboardButton(text="🎭 Персонаж")],
        [KeyboardButton(text="✅ Чек-ин"), KeyboardButton(text="🧪 Шкалы")],
        [KeyboardButton(text="📝 Дневник"), KeyboardButton(text="🆘 Ресурсы")],
        [KeyboardButton(text="🧘 Медитации"), KeyboardButton(text="💳 Подписка")],
        [KeyboardButton(text="💌 Пригласить друга"), KeyboardButton(text="👥 Рефералы")],
    ],
    resize_keyboard=True, input_field_placeholder="Выберите действие…"
)

# -------------------------
# 8.1 Старт и меню + обработка deep-link /start ref<code>
# -------------------------
start_router = Router()

async def _ensure_user(tg_id: int, username: Optional[str]) -> "User":
    # Оставлено для обратной совместимости других обработчиков
    async with SessionLocal() as s:
        user = (await s.execute(select(User).where(User.tg_id == str(tg_id)))).scalar_one_or_none()
        if not user:
            user = User(tg_id=str(tg_id), username=username or "", persona="pro_psychologist")
            s.add(user)
            await s.commit()
        return user

async def ensure_user_with_flag(tg_id: int, username: Optional[str]) -> Tuple["User", bool]:
    async with SessionLocal() as s:
        user = (await s.execute(select(User).where(User.tg_id == str(tg_id)))).scalar_one_or_none()
        created = False
        if not user:
            user = User(tg_id=str(tg_id), username=username or "", persona="pro_psychologist")
            s.add(user)
            await s.commit()
            created = True
        return user, created

# --- Реферальные хелперы ---
_DIGITS36 = "0123456789abcdefghijklmnopqrstuvwxyz"
def _to_base36(n: int) -> str:
    if n < 0:
        raise ValueError("negative")
    if n == 0:
        return "0"
    s = []
    while n:
        n, r = divmod(n, 36)
        s.append(_DIGITS36[r])
    return "".join(reversed(s))

def _from_base36(s: str) -> int:
    return int(s.lower(), 36)

def make_ref_code(tg_id: int) -> str:
    # Простой обратимый код: XOR с солью + base36
    return _to_base36((int(tg_id) ^ REF_SALT))

def parse_ref_code(code: str) -> Optional[int]:
    try:
        v = _from_base36(code.strip().lower())
        candidate = v ^ REF_SALT
        return int(candidate)
    except Exception:
        return None

async def record_referral(referrer_tg_id: int, referred_tg_id: int, code: str, status: str):
    async with SessionLocal() as s:
        # проверим, есть ли запись пары
        existing = (await s.execute(
            select(Referral).where(
                Referral.referrer_tg_id == str(referrer_tg_id),
                Referral.referred_tg_id == str(referred_tg_id)
            )
        )).scalar_one_or_none()
        if existing:
            # Обновим статус, если стало «лучше» (clicked -> joined -> paid)
            order = {"invalid":0, "self":0, "clicked":1, "joined":2, "paid":3}
            if order.get(status, 0) > order.get(existing.status, 0):
                existing.status = status
            await s.commit()
        else:
            s.add(Referral(code=code, referrer_tg_id=str(referrer_tg_id),
                           referred_tg_id=str(referred_tg_id), status=status))
            await s.commit()
    await log_event(str(referred_tg_id), "referral_"+status, {"referrer": str(referrer_tg_id), "code": code})

async def grant_bonus(user_tg_id: int, bonus_type: str, days: int, activated: bool = True, payload: Optional[dict] = None):
    async with SessionLocal() as s:
        s.add(UserBonus(user_tg_id=str(user_tg_id), type=bonus_type, days=days, activated=activated,
                        payload=payload or {}, activated_at=func.now() if activated else None))
        await s.commit()
    await log_event(str(user_tg_id), "bonus_granted", {"type": bonus_type, "days": days, "activated": activated})

async def activate_referral_reward_for_payer(payer_tg_id: int):
    # Найти последнюю referral (joined/clicked) и начислить пригласившему бонус REF_BONUS_DAYS_PAID
    async with SessionLocal() as s:
        ref = (await s.execute(
            select(Referral).where(
                Referral.referred_tg_id == str(payer_tg_id),
                Referral.status.in_(("joined","clicked"))
            ).order_by(Referral.created_at.desc())
        )).scalars().first()
        if not ref:
            return False
        # обновим статус → paid
        ref.status = "paid"
        await s.commit()
    # начислим пригласившему
    await grant_bonus(int(ref.referrer_tg_id), "ref_paid", REF_BONUS_DAYS_PAID, activated=True, payload={"from": str(payer_tg_id)})
    try:
        await bot.send_message(int(ref.referrer_tg_id),
                               f"🎉 Друг совершил оплату — +{REF_BONUS_DAYS_PAID} дней к вашему доступу (бонус реферала).")
    except Exception:
        pass
    return True

@start_router.message(F.text.startswith("/start"))
async def cmd_start(message: Message):
    # Разберём payload у /start (deep-link)
    payload = ""
    parts = message.text.split(maxsplit=1)
    if len(parts) > 1:
        payload = parts[1].strip()

    user, created = await ensure_user_with_flag(message.from_user.id, message.from_user.username)

    # Реферальная обработка: /start ref<code>
    if payload.startswith("ref"):
        code = payload[3:]
        referrer_tg_id = parse_ref_code(code)
        if not referrer_tg_id:
            await record_referral(0, message.from_user.id, code, "invalid")
            await message.answer("Кажется, реферальная ссылка некорректна. Но ничего — можно пользоваться ботом и так 💛")
        elif int(referrer_tg_id) == int(message.from_user.id):
            await record_referral(referrer_tg_id, message.from_user.id, code, "self")
            await message.answer("Нельзя пригласить самого себя 😊 Отправьте ссылку друзьям.")
        else:
            await record_referral(referrer_tg_id, message.from_user.id, code, "joined" if created else "clicked")
            if created:
                # бонус приглашённому сразу
                await grant_bonus(message.from_user.id, "ref_join", REF_BONUS_DAYS_JOINED, activated=True, payload={"referrer": str(referrer_tg_id)})
                try:
                    await bot.send_message(int(referrer_tg_id),
                                           "📣 По вашей ссылке зарегистрировался новый пользователь. "
                                           f"После его первой оплаты вам придёт +{REF_BONUS_DAYS_PAID} дней.")
                except Exception:
                    pass
                await message.answer(f"✨ Добро пожаловать! Вам начислено {REF_BONUS_DAYS_JOINED} дней в подарок за регистрацию по приглашению.")
    # Меню
    await message.answer(
        "Привет! Я Aura — онлайн-психолог в Telegram.\n"
        "Я не ставлю диагнозы и не заменяю терапию. В кризисе звоните 112.\n\n"
        "Выберите действие ниже 👇",
        reply_markup=MAIN_KB,
    )
    await log_event(str(message.from_user.id), "menu_open", {"source": "start"})

@start_router.message(F.text == "/menu")
async def cmd_menu(message: Message):
    await message.answer("Выберите действие ниже 👇", reply_markup=MAIN_KB)

# -------------------------
# 8.2 Персонажи (роли)
# -------------------------
persona_router = Router()

PERSONA_KB = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text=PERSONAS["pro_psychologist"]["title"], callback_data="persona:pro_psychologist")],
        [InlineKeyboardButton(text=PERSONAS["mentor_growth"]["title"],    callback_data="persona:mentor_growth")],
        [InlineKeyboardButton(text=PERSONAS["friend_fun"]["title"],       callback_data="persona:friend_fun")],
    ]
)

@persona_router.message(F.text.in_({"🎭 Персонаж", "/persona"}))
async def select_persona(message: Message):
    await message.answer("Кем мне быть для вас в диалоге?", reply_markup=PERSONA_KB)

@persona_router.callback_query(F.data.startswith("persona:"))
async def set_persona(cb: CallbackQuery):
    persona = cb.data.split(":")[1]
    async with SessionLocal() as s:
        user = (await s.execute(select(User).where(User.tg_id == str(cb.from_user.id)))).scalar_one()
        user.persona = persona
        await s.commit()
    await cb.message.edit_text(f"Готово! Выбрана роль: {PERSONAS[persona]['title']}")
    await log_event(str(cb.from_user.id), "persona_set", {"persona": persona})
    await cb.answer("Супер!")

# -------------------------
# 8.3 Сессия (диалог)
# -------------------------
session_router = Router()

@session_router.message(F.text == "🧠 Сессия")
@session_router.message(F.text == "/session")
async def session_greet(message: Message):
    await message.answer("Начнём. Что сейчас важнее всего — мысль, чувство или ситуация?")

@session_router.message(
    F.text & ~F.text.in_({"🧠 Сессия","🎭 Персонаж","✅ Чек-ин","🧪 Шкалы","📝 Дневник","🆘 Ресурсы","🧘 Медитации","💳 Подписка","💌 Пригласить друга","👥 Рефералы"})
)
async def talk(message: Message):
    # антиспам
    if await rate_limited(message.from_user.id):
        return await message.answer("Хм, очень много сообщений подряд 🙈 Давайте по шагу…")
    if await is_duplicate(message.from_user.id, message.text):
        return
    # кризис
    if detect_risk(message.text):
        await message.answer(CRISIS_TEXT)
        await log_event(str(message.from_user.id), "crisis_detected", {"text": message.text})
        return
    # роль пользователя
    async with SessionLocal() as s:
        user = (await s.execute(select(User).where(User.tg_id == str(message.from_user.id)))).scalar_one_or_none()
    persona_key = user.persona if user else "pro_psychologist"
    system_prompt = PERSONAS[persona_key]["system"] + "\n\n" + STYLE_SYSTEM
    # запрос к «мозгу»
    reply = await deepseek_reply([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": message.text},
    ])
    await message.answer(reply)
    await log_event(str(message.from_user.id), "ai_reply", {"len": len(reply)})

# -------------------------
# 8.4 Чек-ин (настроение)
# -------------------------
checkin_router = Router()
MOODS = ["спокоен/спокойна", "тревожно", "грусть", "злость", "усталость", "радость", "растерянность"]
MOOD_KB = InlineKeyboardMarkup(
    inline_keyboard=[[InlineKeyboardButton(text=m, callback_data=f"mood:{i}")] for i, m in enumerate(MOODS)]
)

@checkin_router.message(F.text.in_({"✅ Чек-ин", "/checkin"}))
async def checkin(message: Message):
    await message.answer("Как вы сейчас? Выберите состояние:", reply_markup=MOOD_KB)

@checkin_router.callback_query(F.data.startswith("mood:"))
async def mood_selected(cb: CallbackQuery):
    idx = int(cb.data.split(":")[1])
    mood = MOODS[idx]
    async with SessionLocal() as s:
        user_id = (await s.execute(sqltext("SELECT id FROM users WHERE tg_id=:t"), {"t": str(cb.from_user.id)})).scalar_one()
        s.add(JournalEntry(user_id=user_id, mood=mood, text=None))
        await s.commit()
    await cb.message.edit_text(f"Сохранила: {mood}. Если хотите, добавьте пару слов — это помогает замечать паттерны.")
    await log_event(str(cb.from_user.id), "checkin_saved", {"mood": mood})
    await cb.answer("Готово")

# -------------------------
# 8.5 Дневник (5 минут после команды)
# -------------------------
journal_router = Router()
_journal_until: Dict[int, float] = {}  # user_id -> timestamp_deadline

@journal_router.message(F.text.in_({"📝 Дневник", "/journal"}))
async def journal_start(message: Message):
    _journal_until[message.from_user.id] = time.time() + 300  # 5 минут
    await message.answer("Напишите заметку в дневник (1–3 предложения) — у вас 5 минут, потом окно закроется.")

@journal_router.message(F.text)
async def journal_capture(message: Message):
    deadline = _journal_until.get(message.from_user.id)
    if not deadline or time.time() > deadline:
        return  # не в «окне дневника»
    async with SessionLocal() as s:
        user_id = (await s.execute(sqltext("SELECT id FROM users WHERE tg_id=:t"), {"t": str(message.from_user.id)})).scalar_one()
        s.add(JournalEntry(user_id=user_id, mood=None, text=message.text))
        await s.commit()
    _journal_until.pop(message.from_user.id, None)
    await message.answer("Сохранила запись. Спасибо, что доверяете.")
    await log_event(str(message.from_user.id), "journal_saved", {"len": len(message.text)})

# -------------------------
# 8.6 Шкалы PHQ-9 и GAD-7 (простая сумма баллов)
# -------------------------
scales_router = Router()
PHQ9 = [
    "Мало интереса или удовольствия от любимых занятий",
    "Подавленное или безнадёжное настроение",
    "Трудности со сном или повышенная сонливость",
    "Усталость или упадок сил",
    "Плохой аппетит или переедание",
    "Низкая самооценка, чувство, что вы неудачник/неудачница",
    "Трудности с концентрацией",
    "Замедленность или ажитация (заметно окружающим)",
    "Мысли, что лучше бы умереть, или мысли о причинении себе вреда",
]
GAD7 = [
    "Чувство нервозности, тревоги или на грани срыва",
    "Невозможность остановить или контролировать беспокойство",
    "Чрезмерные волнения о разных вещах",
    "Трудности с расслаблением",
    "Неспособность усидеть на месте из-за беспокойства",
    "Раздражительность",
    "Страх, что что-то ужасное может случиться",
]
ANSWER_LABELS = ["Никогда (0)", "Несколько дней (1)", "Более половины дней (2)", "Почти каждый день (3)"]

def _answers_kb(prefix: str, idx: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=txt, callback_data=f"{prefix}:{idx}:{score}")]
                         for score, txt in enumerate(ANSWER_LABELS)]
    )

# временное хранилище прогресса шкал: user_id -> {"phq":[...], "gad":[...]}
_scale_progress: Dict[int, Dict[str, List[int]]] = {}

@scales_router.message(F.text.in_({"🧪 Шкалы", "/tests"}))
async def tests_menu(message: Message):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="PHQ-9 (настроение)", callback_data="phq:0"),
             InlineKeyboardButton(text="GAD-7 (тревога)",   callback_data="gad:0")]
        ]
    )
    await message.answer("Выберите шкалу. Это скрининг (предварительная оценка), не диагноз и не замена врачу.", reply_markup=kb)

@scales_router.callback_query(F.data.startswith("phq:"))
async def phq(cb: CallbackQuery):
    idx = int(cb.data.split(":")[1])
    if idx < len(PHQ9):
        await cb.message.edit_text(f"PHQ-9 — вопрос {idx+1}/9\n\n{PHQ9[idx]}\nКак часто за последние 2 недели?", reply_markup=_answers_kb("phqa", idx))
        await cb.answer()

@scales_router.callback_query(F.data.startswith("gad:"))
async def gad(cb: CallbackQuery):
    idx = int(cb.data.split(":")[1])
    if idx < len(GAD7):
        await cb.message.edit_text(f"GAD-7 — вопрос {idx+1}/7\n\n{GAD7[idx]}\nКак часто за последние 2 недели?", reply_markup=_answers_kb("gada", idx))
        await cb.answer()

async def _store_and_next(cb: CallbackQuery, scale_key: str, idx: int, score: int):
    prog = _scale_progress.setdefault(cb.from_user.id, {"phq": [], "gad": []})
    prog[scale_key].append(score)
    next_idx = idx + 1
    total_q = 9 if scale_key == "phq" else 7
    if next_idx < total_q:
        if scale_key == "phq":
            await cb.message.edit_text(f"PHQ-9 — вопрос {next_idx+1}/9\n\n{PHQ9[next_idx]}\nКак часто за последние 2 недели?", reply_markup=_answers_kb("phqa", next_idx))
        else:
            await cb.message.edit_text(f"GAD-7 — вопрос {next_idx+1}/7\n\n{GAD7[next_idx]}\nКак часто за последние 2 недели?", reply_markup=_answers_kb("gada", next_idx))
        await cb.answer()
        return
    # закончили: сохраним сумму в БД
    scores = prog[scale_key]
    total = sum(scores)
    scale_name = "PHQ9" if scale_key == "phq" else "GAD7"
    async with SessionLocal() as s:
        user_id = (await s.execute(sqltext("SELECT id FROM users WHERE tg_id=:t"), {"t": str(cb.from_user.id)})).scalar_one()
        s.add(ScaleResult(user_id=user_id, scale=scale_name, score=total, answers={"scores": scores}))
        await s.commit()
    # очистим прогресс
    prog[scale_key] = []
    await cb.message.edit_text(f"{scale_name} завершена. Ваш суммарный балл: {total}.\nЭто скрининг, не диагноз. "
                               f"Если баллы высоки или есть мысли о самоповреждении — обратитесь за помощью. "
                               f"Я помогу обсудить результат, если хотите.")
    await log_event(str(cb.from_user.id), "scale_finished", {"scale": scale_name, "score": total})
    await cb.answer("Готово")

@scales_router.callback_query(F.data.startswith("phqa:"))
async def phq_answer(cb: CallbackQuery):
    _, idx, score = cb.data.split(":")
    await _store_and_next(cb, "phq", int(idx), int(score))

@scales_router.callback_query(F.data.startswith("gada:"))
async def gad_answer(cb: CallbackQuery):
    _, idx, score = cb.data.split(":")
    await _store_and_next(cb, "gad", int(idx), int(score))

# -------------------------
# 8.7 Ресурсы помощи
# -------------------------
resources_router = Router()

@resources_router.message(F.text.in_({"🆘 Ресурсы", "/resources"}))
async def resources(message: Message):
    await message.answer(CRISIS_TEXT, disable_web_page_preview=True)
    await log_event(str(message.from_user.id), "resources_open", {})

# -------------------------
# 8.8 Подписка (демо-счета) и рефералка (улучшено)
# -------------------------
account_router = Router()

ACCOUNT_KB = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="Опора (RUB)",    callback_data="pay:opora:rub"),
         InlineKeyboardButton(text="Balance+ (RUB)", callback_data="pay:balance:rub")],
        [InlineKeyboardButton(text="SOS-пакет (RUB)", callback_data="pay:sos:rub")],
        [InlineKeyboardButton(text="Опора (USDT)",    callback_data="pay:opora:usdt"),
         InlineKeyboardButton(text="Balance+ (USDT)", callback_data="pay:balance:usdt")],
    ]
)

@account_router.message(F.text.in_({"💳 Подписка", "/account"}))
async def account(message: Message):
    # Покажем базовую информацию + активные бонусы
    async with SessionLocal() as s:
        bonuses = (await s.execute(
            select(UserBonus).where(UserBonus.user_tg_id == str(message.from_user.id))
        )).scalars().all()
    active_days = sum(b.days for b in bonuses if b.activated)
    pending_paid = 0  # приглашённые, которые ещё не оплатили
    # Подсчитаем pending из рефералок (joined, но не paid)
    async with SessionLocal() as s:
        joined = (await s.execute(select(Referral).where(
            Referral.referrer_tg_id == str(message.from_user.id),
            Referral.status.in_(("joined","clicked"))
        ))).scalars().all()
        paid = (await s.execute(select(Referral).where(
            Referral.referrer_tg_id == str(message.from_user.id),
            Referral.status == "paid"
        ))).scalars().all()
        pending_paid = max(0, len(joined) - len(paid))

    text = (
        "Ваши планы и бонусы.\n"
        f"Активных бонусных дней: *{active_days}*\n"
        f"Ожидают бонуса (после оплаты друзей): *{pending_paid}*\n\n"
        "Выберите план ⤵️"
    )
    await message.answer(text, reply_markup=ACCOUNT_KB)

@account_router.callback_query(F.data.startswith("pay:"))
async def pay(cb: CallbackQuery):
    _, plan, currency = cb.data.split(":")
    # демо-ссылки — замените на реальные платёжные ссылки при интеграции
    url = "https://pay.yookassa.ru/demo" if currency == "rub" else "https://t.me/CryptoBot?start=invoice-demo"
    await cb.message.edit_text(f"Счёт создан. Перейдите по ссылке для оплаты: {url}")
    await log_event(str(cb.from_user.id), "payment_created", {"plan": plan, "currency": currency})
    # ДЕМО: считаем, что друг «оплатил» → активируем бонус пригласившему (если был)
    await activate_referral_reward_for_payer(cb.from_user.id)
    await cb.answer()

invite_router = Router()

@invite_router.message(F.text.in_({"💌 Пригласить друга", "/invite"}))
async def invite(message: Message):
    code = make_ref_code(message.from_user.id)
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=ref{code}"
    await message.answer(
        "Реферальная программа:\n"
        f"• Друг регистрируется по вашей ссылке и сразу получает *{REF_BONUS_DAYS_JOINED} дней* бесплатно.\n"
        f"• Когда друг впервые оплачивает — вам начисляется *{REF_BONUS_DAYS_PAID} дней*.\n\n"
        f"Ваша ссылка:\n{link}\n\n"
        "Поделитесь ею с другом 💛"
    )
    await log_event(str(message.from_user.id), "referral_link_shown", {"code": code})

# Новый раздел со статистикой
referrals_router = Router()

@referrals_router.message(F.text.in_({"👥 Рефералы", "/referrals"}))
async def referrals(message: Message):
    code = make_ref_code(message.from_user.id)
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=ref{code}"
    async with SessionLocal() as s:
        total_clicked = (await s.execute(select(func.count()).select_from(
            select(Referral).where(Referral.referrer_tg_id == str(message.from_user.id),
                                   Referral.status == "clicked").subquery()
        ))).scalar_one()
        total_joined = (await s.execute(select(func.count()).select_from(
            select(Referral).where(Referral.referrer_tg_id == str(message.from_user.id),
                                   Referral.status.in_(("joined","paid"))).subquery()
        ))).scalar_one()
        total_paid    = (await s.execute(select(func.count()).select_from(
            select(Referral).where(Referral.referrer_tg_id == str(message.from_user.id),
                                   Referral.status == "paid").subquery()
        ))).scalar_one()
        bonuses = (await s.execute(
            select(UserBonus).where(UserBonus.user_tg_id == str(message.from_user.id))
        )).scalars().all()
    active_days = sum(b.days for b in bonuses if b.activated)
    text = (
        f"👥 *Мои рефералы*\n"
        f"Ссылка приглашения:\n{link}\n\n"
        f"Кликнули: *{total_clicked}*\n"
        f"Присоединились: *{total_joined}*\n"
        f"Совершили оплату: *{total_paid}*\n"
        f"Активных бонусных дней: *{active_days}*"
    )
    await message.answer(text)

# -------------------------
# 8.9 Медитации — локальные/URL аудио с кэшированием file_id
# -------------------------
meditation_router = Router()

def _prettify_title(fname_no_ext: str) -> str:
    base = re.sub(r"[_\-]+", " ", fname_no_ext).strip()
    # первые буквы слов в верхний регистр
    return " ".join(w.capitalize() for w in base.split())

def list_meditations() -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    if os.path.isdir(AUDIO_DIR):
        for fname in sorted(os.listdir(AUDIO_DIR)):
            if fname.lower().endswith((".mp3", ".m4a", ".ogg", ".oga", ".wav")):
                slug = os.path.splitext(fname)[0]
                items.append({
                    "slug": slug,
                    "title": _prettify_title(slug),
                    "filename": fname,
                    "path": os.path.join(AUDIO_DIR, fname)
                })
    return items

async def get_cached_file_id(key: str) -> Optional[str]:
    async with SessionLocal() as s:
        rec = (await s.execute(select(MediaCache).where(MediaCache.key == key))).scalar_one_or_none()
        return rec.file_id if rec else None

async def set_cached_file_id(key: str, file_id: str):
    async with SessionLocal() as s:
        rec = (await s.execute(select(MediaCache).where(MediaCache.key == key))).scalar_one_or_none()
        if rec:
            rec.file_id = file_id
        else:
            s.add(MediaCache(key=key, file_id=file_id))
        await s.commit()

def _meditation_keyboard(items: List[Dict[str, str]]) -> InlineKeyboardMarkup:
    # Кнопки по одному в строке
    kb = [[InlineKeyboardButton(text=i["title"], callback_data=f"med:{i['slug']}")] for i in items]
    return InlineKeyboardMarkup(inline_keyboard=kb or [[InlineKeyboardButton(text="Папка пуста — что делать?", callback_data="med:help")]])

@meditation_router.message(F.text.in_({"🧘 Медитации", "/meditation"}))
async def meditations_menu(message: Message):
    items = list_meditations()
    if not items and not AUDIO_BASE_URL:
        text = (
            "🧘 Медитации: чтобы бот присылал бесплатные аудио,\n"
            f"1) создайте папку: `{AUDIO_DIR}`\n"
            "2) положите туда .mp3/.m4a/.ogg (например, breath_3min.mp3)\n"
            "3) нажмите кнопку ещё раз.\n\n"
            "Либо задайте переменную окружения AUDIO_BASE_URL и храните файлы на CDN."
        )
        await message.answer(text)
        return
    await message.answer("Выберите практику:", reply_markup=_meditation_keyboard(items))

@meditation_router.callback_query(F.data == "med:help")
async def med_help(cb: CallbackQuery):
    await cb.message.edit_text(
        "Как добавить аудио:\n"
        f"• Локальная папка: `{AUDIO_DIR}` — поместите .mp3/.m4a/.ogg\n"
        "• Или укажите AUDIO_BASE_URL — тогда бот пришлёт файл по URL.\n\n"
        "Названия кнопок берутся из имён файлов (подчёркивания/дефисы → пробелы)."
    )
    await cb.answer()

@meditation_router.callback_query(F.data.startswith("med:"))
async def med_play(cb: CallbackQuery):
    slug = cb.data.split(":")[1]
    items = list_meditations()
    item = next((i for i in items if i["slug"] == slug), None)

    key = f"med:{slug}"
    cached = await get_cached_file_id(key)
    if cached:
        await cb.message.answer_audio(audio=cached, caption="Приятной практики 🧘", title=item["title"] if item else None, performer="Aura")
        await cb.answer()
        await log_event(str(cb.from_user.id), "meditation_sent", {"slug": slug, "source": "cache"})
        return

    try:
        if item and os.path.isfile(item["path"]):
            sent = await cb.message.answer_audio(audio=FSInputFile(item["path"]), caption="Приятной практики 🧘", title=item["title"], performer="Aura")
            if sent.audio and sent.audio.file_id:
                await set_cached_file_id(key, sent.audio.file_id)
            await log_event(str(cb.from_user.id), "meditation_sent", {"slug": slug, "source": "local"})
        elif AUDIO_BASE_URL and item:
            url = f"{AUDIO_BASE_URL}/{item['filename']}"
            sent = await cb.message.answer_audio(audio=url, caption="Приятной практики 🧘", title=item["title"], performer="Aura")
            if sent.audio and sent.audio.file_id:
                await set_cached_file_id(key, sent.audio.file_id)
            await log_event(str(cb.from_user.id), "meditation_sent", {"slug": slug, "source": "url"})
        else:
            await cb.message.answer("Не удалось найти аудио. Проверьте папку/URL.")
        await cb.answer()
    except Exception as e:
        await cb.message.answer(f"Не получилось отправить аудио. {e}")
        await cb.answer()

# -------------------------
# 8.10 Регистрация роутеров и команд
# -------------------------
async def setup_commands():
    await bot.set_my_commands([
        BotCommand(command="start", description="Перезапустить бота"),
        BotCommand(command="menu", description="Показать меню"),
        BotCommand(command="persona", description="Выбрать персонажа"),
        BotCommand(command="session", description="Начать разговор"),
        BotCommand(command="checkin", description="Быстрый чек-ин"),
        BotCommand(command="tests", description="Шкалы PHQ-9/GAD-7"),
        BotCommand(command="journal", description="Записи дневника"),
        BotCommand(command="resources", description="Полезные ресурсы"),
        BotCommand(command="meditation", description="Медитации и практики"),
        BotCommand(command="account", description="Подписка и промокоды"),
        BotCommand(command="invite", description="Реферальная ссылка"),
        BotCommand(command="referrals", description="Статистика по рефералам"),
    ])

def register_routers():
    dp.include_router(start_router)
    dp.include_router(persona_router)
    dp.include_router(session_router)
    dp.include_router(checkin_router)
    dp.include_router(journal_router)
    dp.include_router(scales_router)
    dp.include_router(resources_router)
    dp.include_router(account_router)
    dp.include_router(invite_router)
    dp.include_router(referrals_router)
    dp.include_router(meditation_router)

# -------------------------
# 9) MAIN
# -------------------------
async def main():
    print("▶ Aura запускается…")
    await init_db()
    register_routers()
    await setup_commands()
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("⏹ Остановлено")
