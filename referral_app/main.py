"""FastAPI application exposing the referral program endpoints."""

from __future__ import annotations

from typing import Generator
import uuid

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .crud import (
    ensure_user_referral_code,
    get_user_by_id,
    init_models,
    process_successful_subscription,
    register_user,
)
from .database import SessionLocal, engine
from .models import Referral
from .schemas import (
    GenerateReferralLinkRequest,
    MyReferralsResponse,
    ReferralInfo,
    ReferralLinkResponse,
    RegisterRequest,
    RegisterResponse,
    SubscribeRequest,
    SubscribeResponse,
)

app = FastAPI(title="SaaS Referral Program")

# Create tables when the module is imported.  In production this would be
# handled by migrations, but the helper keeps the example self-contained.
init_models(engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session per request."""

    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@app.post("/generate-referral-link", response_model=ReferralLinkResponse)
def generate_referral_link(
    payload: GenerateReferralLinkRequest,
    session: Session = Depends(get_db),
) -> ReferralLinkResponse:
    """Ensure that the user has a referral link and return it."""

    user = get_user_by_id(session, payload.user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")

    code = ensure_user_referral_code(session, user)
    link = settings.referral_link(code)
    return ReferralLinkResponse(referral_code=code, referral_link=link)


@app.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, session: Session = Depends(get_db)) -> RegisterResponse:
    """Register a new user and optionally grant referral bonuses."""

    try:
        user, awarded_days, referrer_id = register_user(
            session,
            email=payload.email,
            name=payload.name,
            password=payload.password,
            referral_code=payload.referral_code,
            request_ip=payload.request_ip,
        )
    except ValueError as exc:  # Transform domain errors into API friendly responses
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return RegisterResponse(user_id=user.id, awarded_days=awarded_days, referrer_id=referrer_id)


@app.post("/subscribe", response_model=SubscribeResponse)
def subscribe(payload: SubscribeRequest, session: Session = Depends(get_db)) -> SubscribeResponse:
    """Handle a successful subscription purchase for a user."""

    subscriber = get_user_by_id(session, payload.user_id)
    if not subscriber:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")

    subscription_end, referrer_bonus_awarded, referrer_id = process_successful_subscription(
        session,
        subscriber=subscriber,
        plan_days=payload.plan_days,
    )

    return SubscribeResponse(
        user_id=subscriber.id,
        subscription_end=subscription_end,
        referrer_bonus_awarded=referrer_bonus_awarded,
        referrer_id=referrer_id,
    )


@app.get("/my-referrals", response_model=MyReferralsResponse)
def my_referrals(user_id: uuid.UUID, session: Session = Depends(get_db)) -> MyReferralsResponse:
    """Return all referrals for the given user with aggregated bonuses."""

    user = get_user_by_id(session, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")

    referrals = (
        session.execute(select(Referral).where(Referral.referrer_id == user.id)).scalars().all()
    )

    referral_infos: list[ReferralInfo] = []
    total_registration_days = 0
    total_subscription_days = 0

    for referral in referrals:
        referral_infos.append(
            ReferralInfo(
                referee_id=referral.referee_id,
                email=referral.referee.email,
                registered_at=referral.registered_at,
                registration_bonus_days=referral.registration_bonus_days,
                subscription_bonus_days=referral.subscription_bonus_days,
                subscription_bonus_awarded=referral.subscription_bonus_awarded,
            )
        )
        total_registration_days += referral.registration_bonus_days
        total_subscription_days += referral.subscription_bonus_days

    return MyReferralsResponse(
        referrer_id=user.id,
        total_registration_days=total_registration_days,
        total_subscription_days=total_subscription_days,
        referrals=referral_infos,
    )
