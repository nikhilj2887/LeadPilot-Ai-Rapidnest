from __future__ import annotations

import os
from collections.abc import Callable

from sqlalchemy import case, or_, select
from sqlalchemy.orm import Session

from leadpilot.application.proposal_email import (
    EmailProviderConfiguration,
    EmailProviderName,
)
from leadpilot.config import Settings
from leadpilot.infrastructure.database.models import EmailProviderConfigModel


class EmailProviderConfigRepository:
    def __init__(
        self, factory: Callable[[], Session], organization_id: int, settings: Settings
    ) -> None:
        self._factory, self._organization_id, self._settings = (
            factory,
            organization_id,
            settings,
        )

    def resolve(self) -> EmailProviderConfiguration | None:
        with self._factory() as session:
            model = session.scalar(
                select(EmailProviderConfigModel)
                .where(
                    EmailProviderConfigModel.is_active.is_(True),
                    EmailProviderConfigModel.is_default.is_(True),
                    or_(
                        EmailProviderConfigModel.organization_id
                        == self._organization_id,
                        EmailProviderConfigModel.organization_id.is_(None),
                    ),
                )
                .order_by(
                    case(
                        (
                            EmailProviderConfigModel.organization_id
                            == self._organization_id,
                            0,
                        ),
                        else_=1,
                    ),
                    EmailProviderConfigModel.id.desc(),
                )
            )
            if model:
                password = (
                    os.getenv(model.credentials_reference, "")
                    if model.credentials_reference
                    else None
                )
                return EmailProviderConfiguration(
                    provider=EmailProviderName(model.provider),
                    from_address=model.from_address,
                    from_name=model.from_name,
                    reply_to=model.reply_to_address,
                    id=model.id,
                    smtp_host=model.smtp_host,
                    smtp_port=model.smtp_port or 587,
                    smtp_username=self._settings.email_smtp_username,
                    smtp_password=password,
                    use_tls=model.smtp_use_tls,
                    use_ssl=model.smtp_use_ssl,
                    timeout_seconds=model.request_timeout_seconds,
                    max_retries=model.max_retries,
                )
        return self._environment_fallback()

    def _environment_fallback(self) -> EmailProviderConfiguration | None:
        settings = self._settings
        if not (
            settings.email_provider
            and settings.email_from_address
            and settings.email_from_name
        ):
            return None
        if settings.email_provider == "smtp" and not settings.email_smtp_host:
            return None
        return EmailProviderConfiguration(
            provider=EmailProviderName(settings.email_provider.upper()),
            from_address=settings.email_from_address,
            from_name=settings.email_from_name,
            reply_to=settings.email_reply_to,
            smtp_host=settings.email_smtp_host,
            smtp_port=settings.email_smtp_port,
            smtp_username=settings.email_smtp_username,
            smtp_password=settings.email_smtp_password,
            use_tls=settings.email_smtp_use_tls,
            use_ssl=settings.email_smtp_use_ssl,
            timeout_seconds=settings.email_timeout_seconds,
            max_retries=settings.email_max_retries,
        )
