"""Pydantic schemas for API validation and responses."""

from datetime import datetime
from typing import List, Optional
import uuid

from pydantic import BaseModel, EmailStr, Field


class GenerateReferralLinkRequest(BaseModel):
    user_id: uuid.UUID = Field(..., description="Идентификатор пользователя, создающего ссылку")


class ReferralLinkResponse(BaseModel):
    referral_code: str
    referral_link: str


class RegisterRequest(BaseModel):
    email: EmailStr
    name: str
    password: str
    referral_code: Optional[str] = Field(default=None, description="Необязательный реферальный код")
    request_ip: str = Field(..., description="IP адрес, с которого выполняется регистрация")


class RegisterResponse(BaseModel):
    user_id: uuid.UUID
    awarded_days: int
    referrer_id: Optional[uuid.UUID]


class SubscribeRequest(BaseModel):
    user_id: uuid.UUID
    plan_days: int = Field(..., gt=0, description="Количество дней, которое даёт оплаченная подписка")


class SubscribeResponse(BaseModel):
    user_id: uuid.UUID
    subscription_end: datetime
    referrer_bonus_awarded: bool
    referrer_id: Optional[uuid.UUID]


class ReferralInfo(BaseModel):
    referee_id: uuid.UUID
    email: EmailStr
    registered_at: datetime
    registration_bonus_days: int
    subscription_bonus_days: int
    subscription_bonus_awarded: bool


class MyReferralsResponse(BaseModel):
    referrer_id: uuid.UUID
    total_registration_days: int
    total_subscription_days: int
    referrals: List[ReferralInfo]
