from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from leadpilot.application.proposal_generation import (
    GeneratedProposalSection,
    ProposalGenerationDraft,
    ProposalGenerationStatus,
    ProposalGenerationType,
    ProposalSectionContentSource,
    ProposalTone,
)
from leadpilot.infrastructure.database.models import (
    ProposalGenerationDraftModel,
    ProposalSectionModel,
)


class ProposalGenerationRepository:
    """Tenant-bound persistence for immutable proposal generation drafts."""

    def __init__(self, factory: Callable[[], Session], organization_id: int) -> None:
        self._factory, self.organization_id = factory, organization_id

    def create(
        self,
        proposal_id: int,
        ai_run_id: int,
        generation_type: ProposalGenerationType,
        tone: ProposalTone,
        instructions: str | None,
        keys: tuple[str, ...],
        sections: tuple[GeneratedProposalSection, ...],
        warnings: tuple[str, ...],
        input_hash: str,
        user_id: int | None,
    ) -> ProposalGenerationDraft:
        with self._factory() as session, session.begin():
            model = ProposalGenerationDraftModel(
                organization_id=self.organization_id,
                proposal_id=proposal_id,
                ai_run_id=ai_run_id,
                generation_type=generation_type.value,
                status=ProposalGenerationStatus.READY_FOR_REVIEW.value,
                tone=tone.value,
                instructions=instructions,
                requested_section_keys_json=json.dumps(keys),
                generated_sections_json=json.dumps(
                    [self._section_dict(s) for s in sections]
                ),
                source_references_json=json.dumps(
                    [r for s in sections for r in s.source_references]
                ),
                warnings_json=json.dumps(warnings),
                applied_section_keys_json="[]",
                input_hash=input_hash,
                created_by_user_id=user_id,
            )
            session.add(model)
            session.flush()
            session.refresh(model)
            return self._draft(model)

    def get(self, draft_id: int) -> ProposalGenerationDraft | None:
        with self._factory() as session:
            model = session.scalar(
                select(ProposalGenerationDraftModel).where(
                    ProposalGenerationDraftModel.id == draft_id,
                    ProposalGenerationDraftModel.organization_id
                    == self.organization_id,
                )
            )
            return self._draft(model) if model else None

    def find_ready(
        self, proposal_id: int, input_hash: str
    ) -> ProposalGenerationDraft | None:
        with self._factory() as session:
            model = session.scalar(
                select(ProposalGenerationDraftModel)
                .where(
                    ProposalGenerationDraftModel.proposal_id == proposal_id,
                    ProposalGenerationDraftModel.organization_id
                    == self.organization_id,
                    ProposalGenerationDraftModel.input_hash == input_hash,
                    ProposalGenerationDraftModel.status
                    == ProposalGenerationStatus.READY_FOR_REVIEW.value,
                )
                .order_by(ProposalGenerationDraftModel.id.desc())
            )
            return self._draft(model) if model else None

    def list(self, proposal_id: int) -> tuple[ProposalGenerationDraft, ...]:
        with self._factory() as session:
            return tuple(
                self._draft(m)
                for m in session.scalars(
                    select(ProposalGenerationDraftModel)
                    .where(
                        ProposalGenerationDraftModel.proposal_id == proposal_id,
                        ProposalGenerationDraftModel.organization_id
                        == self.organization_id,
                    )
                    .order_by(
                        ProposalGenerationDraftModel.created_at.desc(),
                        ProposalGenerationDraftModel.id.desc(),
                    )
                )
            )

    def apply(
        self, draft_id: int, keys: tuple[str, ...], user_id: int | None
    ) -> ProposalGenerationDraft | None:
        with self._factory() as session, session.begin():
            model = self._ready(session, draft_id)
            if model is None:
                return None
            requested = tuple(json.loads(model.requested_section_keys_json))
            (
                model.applied_section_keys_json,
                model.applied_by_user_id,
                model.applied_at,
            ) = json.dumps(keys), user_id, datetime.now(UTC)
            model.status = (
                ProposalGenerationStatus.APPLIED
                if set(keys) == set(requested)
                else ProposalGenerationStatus.PARTIALLY_APPLIED
            ).value
            session.flush()
            session.refresh(model)
            return self._draft(model)

    def reject(self, draft_id: int) -> ProposalGenerationDraft | None:
        with self._factory() as session, session.begin():
            model = self._ready(session, draft_id)
            if model is None:
                return None
            model.status, model.rejected_at = (
                ProposalGenerationStatus.REJECTED.value,
                datetime.now(UTC),
            )
            session.flush()
            session.refresh(model)
            return self._draft(model)

    def supersede(self, proposal_id: int, keys: tuple[str, ...]) -> int:
        with self._factory() as session, session.begin():
            models = list(
                session.scalars(
                    select(ProposalGenerationDraftModel).where(
                        ProposalGenerationDraftModel.proposal_id == proposal_id,
                        ProposalGenerationDraftModel.organization_id
                        == self.organization_id,
                        ProposalGenerationDraftModel.status
                        == ProposalGenerationStatus.READY_FOR_REVIEW.value,
                    )
                )
            )
            count = 0
            for model in models:
                if set(json.loads(model.requested_section_keys_json)) == set(keys):
                    model.status = ProposalGenerationStatus.SUPERSEDED.value
                    count += 1
            return count

    def apply_sections(
        self,
        proposal_id: int,
        ai_run_id: int,
        sections: tuple[GeneratedProposalSection, ...],
    ) -> None:
        with self._factory() as session, session.begin():
            by_key = {s.section_key: s for s in sections}
            models = list(
                session.scalars(
                    select(ProposalSectionModel).where(
                        ProposalSectionModel.proposal_id == proposal_id,
                        ProposalSectionModel.organization_id == self.organization_id,
                        ProposalSectionModel.section_key.in_(by_key),
                    )
                )
            )
            if len(models) != len(sections):
                raise ValueError("One or more proposal sections are unavailable.")
            for model in models:
                generated = by_key[model.section_key]
                model.title, model.content = generated.title, generated.content
                model.content_source, model.manually_edited = (
                    ProposalSectionContentSource.AI_GENERATED.value,
                    False,
                )
                model.last_ai_run_id, model.generated_at = ai_run_id, datetime.now(UTC)

    def _ready(
        self, session: Session, draft_id: int
    ) -> ProposalGenerationDraftModel | None:
        return session.scalar(
            select(ProposalGenerationDraftModel).where(
                ProposalGenerationDraftModel.id == draft_id,
                ProposalGenerationDraftModel.organization_id == self.organization_id,
                ProposalGenerationDraftModel.status
                == ProposalGenerationStatus.READY_FOR_REVIEW.value,
            )
        )

    @staticmethod
    def _section_dict(section: GeneratedProposalSection) -> dict[str, object]:
        return {
            "section_key": section.section_key,
            "title": section.title,
            "content": section.content,
            "source_references": section.source_references,
            "warnings": section.warnings,
        }

    @classmethod
    def _draft(cls, model: ProposalGenerationDraftModel) -> ProposalGenerationDraft:
        sections = tuple(
            GeneratedProposalSection(
                s["section_key"],
                s["title"],
                s["content"],
                tuple(s.get("source_references", ())),
                tuple(s.get("warnings", ())),
            )
            for s in json.loads(model.generated_sections_json)
        )
        return ProposalGenerationDraft(
            model.id,
            model.proposal_id,
            model.ai_run_id,
            ProposalGenerationType(model.generation_type),
            ProposalGenerationStatus(model.status),
            ProposalTone(model.tone),
            model.instructions,
            tuple(json.loads(model.requested_section_keys_json)),
            sections,
            tuple(json.loads(model.warnings_json or "[]")),
            tuple(json.loads(model.applied_section_keys_json or "[]")),
            model.input_hash,
            model.created_at,
        )
