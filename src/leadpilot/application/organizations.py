from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator

ORGANIZATION_STATUSES = ("active", "suspended", "archived")
SUPPORTED_CURRENCIES = ("AUD", "CAD", "EUR", "GBP", "INR", "USD")
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
HEX_COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class OrganizationValidationError(ValueError):
    pass


class OrganizationNotFoundError(LookupError):
    pass


class OrganizationInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    slug: str = Field(min_length=2, max_length=80)
    legal_name: str | None = Field(default=None, max_length=200)
    display_name: str = Field(min_length=1, max_length=200)
    status: str = "active"
    default_currency: str = "INR"
    timezone: str = "Asia/Kolkata"
    website: str | None = Field(default=None, max_length=500)
    contact_email: str | None = Field(default=None, max_length=320)
    contact_phone: str | None = Field(default=None, max_length=50)

    @field_validator("slug")
    @classmethod
    def valid_slug(cls, value: str) -> str:
        if not SLUG_PATTERN.fullmatch(value):
            raise ValueError(
                "Slug must contain lowercase letters, numbers, and hyphens"
            )
        return value

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str) -> str:
        if value not in ORGANIZATION_STATUSES:
            raise ValueError("Invalid organization status")
        return value

    @field_validator("default_currency")
    @classmethod
    def valid_currency(cls, value: str) -> str:
        value = value.upper()
        if value not in SUPPORTED_CURRENCIES:
            raise ValueError("Unsupported currency")
        return value

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Invalid timezone") from exc
        return value

    @field_validator("contact_email")
    @classmethod
    def valid_email(cls, value: str | None) -> str | None:
        if value and not EMAIL_PATTERN.fullmatch(value):
            raise ValueError("Invalid contact email")
        return value

    @field_validator("website")
    @classmethod
    def valid_website(cls, value: str | None) -> str | None:
        if not value:
            return None
        candidate = value if "://" in value else f"https://{value}"
        parsed = urlparse(candidate)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Invalid organization website")
        return value


class OrganizationCreate(OrganizationInput):
    pass


class OrganizationUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    legal_name: str | None = Field(default=None, max_length=200)
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    status: str | None = None
    default_currency: str | None = None
    timezone: str | None = None
    website: str | None = Field(default=None, max_length=500)
    contact_email: str | None = Field(default=None, max_length=320)
    contact_phone: str | None = Field(default=None, max_length=50)

    _status = field_validator("status")(OrganizationInput.valid_status.__func__)
    _currency = field_validator("default_currency")(
        OrganizationInput.valid_currency.__func__
    )
    _timezone = field_validator("timezone")(OrganizationInput.valid_timezone.__func__)
    _email = field_validator("contact_email")(OrganizationInput.valid_email.__func__)
    _website = field_validator("website")(OrganizationInput.valid_website.__func__)


class OrganizationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    display_name: str
    status: str


class OrganizationDetails(OrganizationInput):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class OrganizationBranding:
    organization_id: int
    brand_name: str
    logo_reference: str | None
    primary_color: str
    secondary_color: str
    accent_color: str
    proposal_footer: str | None
    email_signature: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class OrganizationService:
    id: int
    organization_id: int
    name: str
    short_description: str | None
    full_description: str | None
    category: str | None
    is_active: bool
    display_order: int
    created_at: datetime
    updated_at: datetime


class OrganizationRepository(Protocol):
    def list_active(self) -> list[OrganizationSummary]: ...
    def get(self, organization_id: int) -> OrganizationDetails | None: ...
    def get_by_slug(self, slug: str) -> OrganizationDetails | None: ...


@dataclass(frozen=True, slots=True)
class OrganizationContext:
    organization_id: int
    organization: OrganizationDetails

    @classmethod
    def resolve(
        cls, repository: OrganizationRepository, organization_id: int | None = None
    ) -> OrganizationContext:
        organization = (
            repository.get(organization_id)
            if organization_id is not None
            else repository.get_by_slug("rapidnest")
        )
        if organization is None:
            raise OrganizationNotFoundError("Organization was not found")
        if organization.status != "active":
            raise OrganizationValidationError("Organization is not active")
        return cls(organization.id, organization)


def validate_color(value: str) -> str:
    if not HEX_COLOR_PATTERN.fullmatch(value):
        raise OrganizationValidationError("Color must use #RRGGBB format")
    return value.upper()


def validate_logo_reference(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.replace("\\", "/")
    if (
        normalized.startswith("/")
        or ".." in normalized.split("/")
        or not normalized.startswith("assets/")
    ):
        raise OrganizationValidationError(
            "Logo reference must be a safe path under assets/"
        )
    return normalized
