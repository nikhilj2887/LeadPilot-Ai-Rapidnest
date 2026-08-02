from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from leadpilot.application.proposal_email import (
    EmailProviderName,
    EmailRecipientSet,
    ProposalEmailDelivery,
    ProposalEmailDeliveryStatus,
)
from leadpilot.infrastructure.database.models import ProposalEmailDeliveryModel


class ProposalEmailRepository:
    def __init__(self, factory: Callable[[], Session], organization_id: int) -> None:
        self._factory, self.organization_id = factory, organization_id

    def create_draft(self, values: dict[str, object]) -> ProposalEmailDelivery:
        recipients = values.pop("recipients")
        assert isinstance(recipients, EmailRecipientSet)
        provider = values.pop("provider")
        assert isinstance(provider, EmailProviderName)
        reply_to = values.pop("reply_to")
        attachment_checksum = values.pop("attachment_checksum")
        with self._factory() as session, session.begin():
            model = ProposalEmailDeliveryModel(
                organization_id=self.organization_id,
                provider=provider.value,
                reply_to_address=reply_to,
                attachment_sha256_checksum=attachment_checksum,
                to_addresses_json=json.dumps(recipients.to),
                cc_addresses_json=json.dumps(recipients.cc),
                bcc_addresses_json=json.dumps(recipients.bcc),
                **values,
            )
            session.add(model)
            session.flush()
            session.refresh(model)
            return self._delivery(model)

    def get_by_id(self, delivery_id: int) -> ProposalEmailDelivery | None:
        with self._factory() as session:
            model = self._get(session, delivery_id)
            return self._delivery(model) if model else None

    def list_by_proposal(self, proposal_id: int) -> tuple[ProposalEmailDelivery, ...]:
        with self._factory() as session:
            return tuple(
                self._delivery(model)
                for model in session.scalars(
                    select(ProposalEmailDeliveryModel)
                    .where(
                        ProposalEmailDeliveryModel.organization_id
                        == self.organization_id,
                        ProposalEmailDeliveryModel.proposal_id == proposal_id,
                    )
                    .order_by(
                        ProposalEmailDeliveryModel.created_at.desc(),
                        ProposalEmailDeliveryModel.id.desc(),
                    )
                )
            )

    def find_by_idempotency_key(self, key: str) -> ProposalEmailDelivery | None:
        with self._factory() as session:
            model = session.scalar(
                select(ProposalEmailDeliveryModel).where(
                    ProposalEmailDeliveryModel.organization_id == self.organization_id,
                    ProposalEmailDeliveryModel.idempotency_key == key,
                )
            )
            return self._delivery(model) if model else None

    def list_by_document(self, document_id: int) -> tuple[ProposalEmailDelivery, ...]:
        return self._list_where(
            ProposalEmailDeliveryModel.proposal_document_id == document_id
        )

    def list_by_status(
        self, status: ProposalEmailDeliveryStatus
    ) -> tuple[ProposalEmailDelivery, ...]:
        return self._list_where(ProposalEmailDeliveryModel.status == status.value)

    def paginate(
        self,
        *,
        page: int = 1,
        page_size: int = 25,
        status: ProposalEmailDeliveryStatus | None = None,
        provider: EmailProviderName | None = None,
    ) -> tuple[ProposalEmailDelivery, ...]:
        page, page_size = max(1, page), min(100, max(1, page_size))
        predicates = [
            ProposalEmailDeliveryModel.organization_id == self.organization_id
        ]
        if status:
            predicates.append(ProposalEmailDeliveryModel.status == status.value)
        if provider:
            predicates.append(ProposalEmailDeliveryModel.provider == provider.value)
        with self._factory() as session:
            return tuple(
                self._delivery(model)
                for model in session.scalars(
                    select(ProposalEmailDeliveryModel)
                    .where(*predicates)
                    .order_by(
                        ProposalEmailDeliveryModel.created_at.desc(),
                        ProposalEmailDeliveryModel.id.desc(),
                    )
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            )

    def count_by_status(self) -> dict[ProposalEmailDeliveryStatus, int]:
        with self._factory() as session:
            rows = session.execute(
                select(
                    ProposalEmailDeliveryModel.status,
                    func.count(ProposalEmailDeliveryModel.id),
                )
                .where(
                    ProposalEmailDeliveryModel.organization_id == self.organization_id
                )
                .group_by(ProposalEmailDeliveryModel.status)
            )
            return {
                ProposalEmailDeliveryStatus(status): count for status, count in rows
            }

    def dashboard_metrics(self) -> dict[str, int]:
        counts = self.count_by_status()
        return {
            "total": sum(counts.values()),
            **{
                status.value: counts.get(status, 0)
                for status in ProposalEmailDeliveryStatus
            },
        }

    def transition(
        self,
        delivery_id: int,
        expected: ProposalEmailDeliveryStatus,
        status: ProposalEmailDeliveryStatus,
        **values: object,
    ) -> ProposalEmailDelivery:
        with self._factory() as session, session.begin():
            model = self._get(session, delivery_id)
            if model is None or model.status != expected.value:
                raise ValueError("Invalid email delivery transition.")
            model.status = status.value
            now = datetime.now(UTC)
            timestamp = {
                ProposalEmailDeliveryStatus.QUEUED: "queued_at",
                ProposalEmailDeliveryStatus.SENDING: "sending_at",
                ProposalEmailDeliveryStatus.SENT: "sent_at",
                ProposalEmailDeliveryStatus.FAILED: "failed_at",
                ProposalEmailDeliveryStatus.CANCELLED: "cancelled_at",
                ProposalEmailDeliveryStatus.SUPERSEDED: "superseded_at",
            }.get(status)
            if timestamp:
                setattr(model, timestamp, now)
            for name, value in values.items():
                if name in {
                    "provider_message_id",
                    "provider_response_json",
                    "safe_error_code",
                    "safe_error_message",
                }:
                    setattr(model, name, value)
            session.flush()
            session.refresh(model)
            return self._delivery(model)

    def increment_attempt(self, delivery_id: int) -> ProposalEmailDelivery:
        with self._factory() as session, session.begin():
            model = self._get(session, delivery_id)
            if model is None:
                raise ValueError("Email delivery was not found.")
            model.attempt_count += 1
            session.flush()
            session.refresh(model)
            return self._delivery(model)

    def _list_where(self, predicate: object) -> tuple[ProposalEmailDelivery, ...]:
        with self._factory() as session:
            return tuple(
                self._delivery(model)
                for model in session.scalars(
                    select(ProposalEmailDeliveryModel)
                    .where(
                        ProposalEmailDeliveryModel.organization_id
                        == self.organization_id,
                        predicate,
                    )
                    .order_by(
                        ProposalEmailDeliveryModel.created_at.desc(),
                        ProposalEmailDeliveryModel.id.desc(),
                    )
                )
            )

    def _get(
        self, session: Session, delivery_id: int
    ) -> ProposalEmailDeliveryModel | None:
        return session.scalar(
            select(ProposalEmailDeliveryModel).where(
                ProposalEmailDeliveryModel.id == delivery_id,
                ProposalEmailDeliveryModel.organization_id == self.organization_id,
            )
        )

    @staticmethod
    def _delivery(model: ProposalEmailDeliveryModel) -> ProposalEmailDelivery:
        return ProposalEmailDelivery(
            id=model.id,
            proposal_id=model.proposal_id,
            proposal_document_id=model.proposal_document_id,
            status=ProposalEmailDeliveryStatus(model.status),
            provider=EmailProviderName(model.provider),
            from_address=model.from_address,
            from_name=model.from_name,
            reply_to=model.reply_to_address,
            recipients=EmailRecipientSet(
                tuple(json.loads(model.to_addresses_json)),
                tuple(json.loads(model.cc_addresses_json or "[]")),
                tuple(json.loads(model.bcc_addresses_json or "[]")),
            ),
            subject=model.subject,
            html_body=model.html_body,
            text_body=model.text_body,
            attachment_file_name=model.attachment_file_name,
            attachment_checksum=model.attachment_sha256_checksum,
            idempotency_key=model.idempotency_key,
            attempt_count=model.attempt_count,
            provider_message_id=model.provider_message_id,
            safe_error_code=model.safe_error_code,
            safe_error_message=model.safe_error_message,
            created_at=model.created_at,
            sent_at=model.sent_at,
            original_delivery_id=model.original_delivery_id,
        )
