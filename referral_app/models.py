"""SQLAlchemy ORM models for the referral program domain."""

from __future__ import annotations

from datetime import datetime
import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class User(Base):
    """Application user that can invite friends and receive bonuses."""

    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=False)
    referral_code = Column(String(32), unique=True, index=True)
    referred_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    subscription_end = Column(DateTime(timezone=True), nullable=True)
    bonus_balance_days = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    referred_users = relationship(
        "Referral",
        back_populates="referrer",
        foreign_keys="Referral.referrer_id",
        cascade="all, delete-orphan",
    )
    referral_record = relationship(
        "Referral",
        back_populates="referee",
        foreign_keys="Referral.referee_id",
        uselist=False,
    )
    bonus_events = relationship("BonusEvent", back_populates="user", cascade="all, delete-orphan")


class Referral(Base):
    """Links the inviter and invitee alongside bookkeeping metadata."""

    __tablename__ = "referrals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    referrer_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    referee_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, unique=True)
    registration_ip = Column(String(64), nullable=True)
    registered_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    registration_bonus_days = Column(Integer, default=0, nullable=False)
    subscription_bonus_awarded = Column(Boolean, default=False, nullable=False)
    subscription_bonus_days = Column(Integer, default=0, nullable=False)
    subscription_awarded_at = Column(DateTime(timezone=True), nullable=True)

    referrer = relationship("User", foreign_keys=[referrer_id], back_populates="referred_users")
    referee = relationship("User", foreign_keys=[referee_id], back_populates="referral_record")
    bonus_events = relationship("BonusEvent", back_populates="referral", cascade="all, delete-orphan")


class BonusEvent(Base):
    """Ledger of every bonus day credit issued by the program."""

    __tablename__ = "bonus_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    referral_id = Column(UUID(as_uuid=True), ForeignKey("referrals.id"), nullable=True)
    event_type = Column(String(32), nullable=False)
    days_awarded = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    user = relationship("User", back_populates="bonus_events")
    referral = relationship("Referral", back_populates="bonus_events")
