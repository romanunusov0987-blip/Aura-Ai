"""Reusable business logic for the referral program."""

from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import settings
from .models import Base, BonusEvent, Referral, User


def init_models(engine) -> None:
    """Create database tables if they are missing."""

    Base.metadata.create_all(bind=engine)


def hash_password(password: str) -> str:
    """Produce a deterministic password hash (for demo purposes only)."""

    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def generate_referral_code(session: Session) -> str:
    """Generate a unique referral code."""

    while True:
        code = uuid.uuid4().hex[:10]
        exists = session.execute(select(User).where(User.referral_code == code)).scalar_one_or_none()
        if not exists:
            return code


def get_user_by_id(session: Session, user_id: uuid.UUID) -> User | None:
    """Fetch a user by identifier."""

    return session.get(User, user_id)


def get_user_by_email(session: Session, email: str) -> User | None:
    """Fetch a user by email."""

    return session.execute(select(User).where(User.email == email)).scalar_one_or_none()


def award_bonus_days(
    session: Session,
    user: User,
    days: int,
    event_type: str,
    referral: Referral | None = None,
) -> None:
    """Grant bonus days to a user and update their subscription end date."""

    if days <= 0:
        return

    now = datetime.utcnow()
    user.bonus_balance_days += days

    # Extend the subscription: if it is already active, extend from current
    # expiry; otherwise start counting from "now".
    if user.subscription_end and user.subscription_end > now:
        user.subscription_end = user.subscription_end + timedelta(days=days)
    else:
        user.subscription_end = now + timedelta(days=days)

    session.add(
        BonusEvent(
            user=user,
            referral=referral,
            event_type=event_type,
            days_awarded=days,
        )
    )


def register_user(
    session: Session,
    *,
    email: str,
    name: str,
    password: str,
    referral_code: str | None,
    request_ip: str,
) -> tuple[User, int, uuid.UUID | None]:
    """Register a new user and award referral bonuses if applicable."""

    if get_user_by_email(session, email):
        raise ValueError("Пользователь с таким email уже существует")

    user = User(email=email, name=name, password_hash=hash_password(password))
    session.add(user)
    session.flush()  # Get database generated identifiers

    awarded_days = 0
    referrer_id: uuid.UUID | None = None

    if referral_code:
        referrer = session.execute(
            select(User).where(User.referral_code == referral_code)
        ).scalar_one_or_none()
        if not referrer:
            raise ValueError("Реферальный код не найден")

        # Protect against abuse: limit number of registrations per IP for the
        # same referrer.
        ip_count = session.execute(
            select(func.count()).select_from(Referral).where(
                Referral.referrer_id == referrer.id,
                Referral.registration_ip == request_ip,
            )
        ).scalar_one()
        if ip_count >= settings.max_registrations_per_ip:
            raise ValueError("С данного IP уже была регистрация по этой ссылке")

        user.referred_by_id = referrer.id

        referral = Referral(
            referrer=referrer,
            referee=user,
            registration_ip=request_ip,
            registration_bonus_days=int(settings.registration_bonus.total_seconds() // 86400),
        )
        session.add(referral)
        session.flush()

        awarded_days = referral.registration_bonus_days
        referrer_id = referrer.id
        award_bonus_days(
            session,
            referrer,
            referral.registration_bonus_days,
            event_type="registration",
            referral=referral,
        )

    return user, awarded_days, referrer_id


def ensure_user_referral_code(session: Session, user: User) -> str:
    """Ensure the user has a referral code, generating a new one if necessary."""

    if not user.referral_code:
        user.referral_code = generate_referral_code(session)
    return user.referral_code


def process_successful_subscription(
    session: Session,
    *,
    subscriber: User,
    plan_days: int,
) -> tuple[datetime, bool, uuid.UUID | None]:
    """Update subscriber subscription and award inviter if applicable."""

    now = datetime.utcnow()
    if subscriber.subscription_end and subscriber.subscription_end > now:
        subscriber.subscription_end = subscriber.subscription_end + timedelta(days=plan_days)
    else:
        subscriber.subscription_end = now + timedelta(days=plan_days)

    referrer_awarded = False
    referrer_id: uuid.UUID | None = None

    if subscriber.referred_by_id:
        referral = session.execute(
            select(Referral).where(Referral.referee_id == subscriber.id)
        ).scalar_one_or_none()
        if referral and not referral.subscription_bonus_awarded:
            referrer = session.get(User, referral.referrer_id)
            if referrer is None:
                raise ValueError("Пригласивший пользователь не найден")

            referral.subscription_bonus_awarded = True
            referral.subscription_bonus_days = int(
                settings.subscription_bonus.total_seconds() // 86400
            )
            referral.subscription_awarded_at = now

            award_bonus_days(
                session,
                referrer,
                referral.subscription_bonus_days,
                event_type="subscription",
                referral=referral,
            )
            referrer_awarded = True
            referrer_id = referrer.id

    return subscriber.subscription_end, referrer_awarded, referrer_id
