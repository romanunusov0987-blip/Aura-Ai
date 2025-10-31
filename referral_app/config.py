"""Application configuration primitives."""

from dataclasses import dataclass
from datetime import timedelta
import os
from urllib.parse import urljoin


@dataclass(frozen=True)
class Settings:
    """Container for configurable settings used by the referral service."""

    database_url: str = os.getenv(
        "DATABASE_URL",
        "sqlite:///referral_app.db",
    )
    referral_base_url: str = os.getenv(
        "REFERRAL_BASE_URL", "https://saas.example.com/register?code="
    )
    registration_bonus: timedelta = timedelta(days=3)
    subscription_bonus: timedelta = timedelta(days=7)
    max_registrations_per_ip: int = int(os.getenv("MAX_REGISTRATIONS_PER_IP", "1"))

    def referral_link(self, code: str) -> str:
        """Build a fully qualified referral link for the given code."""

        return urljoin(self.referral_base_url, code)


settings = Settings()
"""Singleton settings instance consumed by the rest of the app."""
