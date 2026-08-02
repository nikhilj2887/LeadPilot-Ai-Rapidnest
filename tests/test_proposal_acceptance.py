from __future__ import annotations

import hashlib
import io
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw
from pypdf import PdfReader
from reportlab.pdfgen.canvas import Canvas

from leadpilot.application.proposal_acceptance import (
    AcceptanceAlreadyCompletedError,
    AcceptanceSubmission,
    AcceptanceUnavailableError,
    AcceptanceValidationError,
    ProposalAcceptance,
    ProposalAcceptanceService,
    ProposalAcceptanceStatus,
    SignatureType,
    validate_signature_png,
)
from leadpilot.infrastructure.pdf.reportlab_acceptance_renderer import (
    ReportLabSignedAcceptanceRenderer,
)
from leadpilot.infrastructure.storage.local_document_storage import LocalDocumentStorage
from tests.test_support import build_acceptance_context


def _pdf() -> bytes:
    output = io.BytesIO()
    canvas = Canvas(output)
    canvas.drawString(72, 750, "Original proposal")
    canvas.save()
    return output.getvalue()


def _png(*, drawn: bool = True, size: tuple[int, int] = (180, 80)) -> bytes:
    image = Image.new("RGB", size, "white")
    if drawn:
        ImageDraw.Draw(image).line((10, 50, 160, 20), fill="black", width=4)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


class _Repository:
    def __init__(self) -> None:
        self.result: ProposalAcceptance | None = None
        self.values: dict[str, object] = {}

    def accepted_for_proposal(self, organization_id: int, proposal_id: int):
        return (
            self.result
            if self.result and self.result.status == ProposalAcceptanceStatus.ACCEPTED
            else None
        )

    def acceptance_for_link(self, link_id: int):
        return self.result

    def accept(self, context, values, signed_document):
        self.values = {**values, **signed_document}
        self.result = _acceptance(
            ProposalAcceptanceStatus.ACCEPTED, context.link.organization_id
        )
        return self.result

    def reject(self, context, comments, metadata, rejected_at):
        self.values = {"comments": comments, **metadata}
        self.result = _acceptance(
            ProposalAcceptanceStatus.REJECTED, context.link.organization_id
        )
        return self.result

    def list_by_proposal(self, proposal_id: int):
        return (self.result,) if self.result else ()


def _acceptance(status: ProposalAcceptanceStatus, org: int = 1) -> ProposalAcceptance:
    now = datetime.now(UTC)
    return ProposalAcceptance(
        21,
        org,
        11,
        7,
        13,
        22 if status == ProposalAcceptanceStatus.ACCEPTED else None,
        status,
        "Alex Client" if status == ProposalAcceptanceStatus.ACCEPTED else None,
        "alex@example.test" if status == ProposalAcceptanceStatus.ACCEPTED else None,
        "Client Co" if status == ProposalAcceptanceStatus.ACCEPTED else None,
        None,
        SignatureType.TYPED if status == ProposalAcceptanceStatus.ACCEPTED else None,
        "Alex Client" if status == ProposalAcceptanceStatus.ACCEPTED else None,
        None,
        None,
        "a" * 64 if status == ProposalAcceptanceStatus.ACCEPTED else None,
        now if status == ProposalAcceptanceStatus.ACCEPTED else None,
        now if status == ProposalAcceptanceStatus.REJECTED else None,
        now,
    )


class _PortalRepository:
    def __init__(self, checksum: str) -> None:
        self.checksum = checksum

    def document_snapshot(self, link):
        snapshot = {
            "branding": {"brand_name": "Tenant Brand", "primary_color": "#123456"},
            "proposal": {"number": "LP-1", "title": "Growth Plan"},
            "company": {"name": "Client Co"},
        }
        return (
            json.dumps(snapshot),
            "original.pdf",
            100,
            self.checksum,
            "application/pdf",
        )


class _PdfService:
    def __init__(self, content: bytes, checksum: str) -> None:
        self.content, self.checksum = content, checksum

    def download_proposal_document(self, document_id: int):
        return SimpleNamespace(
            file_name="Proposal.pdf", sha256_checksum=self.checksum
        ), self.content


def _service(tmp_path, repository: _Repository | None = None):
    original = _pdf()
    checksum = hashlib.sha256(original).hexdigest()
    repo = repository or _Repository()
    events: list[str] = []
    service = ProposalAcceptanceService(
        repo,
        _PortalRepository(checksum),
        lambda organization_id: _PdfService(original, checksum),
        LocalDocumentStorage(tmp_path),
        ReportLabSignedAcceptanceRenderer(),
        "test-pepper",
        lambda action, entity, entity_id: events.append(action),
    )
    return service, repo, events


def _typed(**changes) -> AcceptanceSubmission:
    values = {
        "legal_name": "Alex Client",
        "email": "Alex@Example.Test",
        "company": "Client Co",
        "title": "Director",
        "comments": "Approved",
        "signature_type": SignatureType.TYPED,
        "typed_signature": "Alex Client",
        "authorized": True,
    }
    values.update(changes)
    return AcceptanceSubmission(**values)


def test_typed_acceptance_generates_signed_copy_and_audit_events(tmp_path) -> None:
    service, repository, events = _service(tmp_path)
    accepted = service.accept_proposal(
        build_acceptance_context(),
        _typed(),
        ip_address="192.0.2.1",
        user_agent="browser",
        session_identifier="session",
    )
    assert accepted.status == ProposalAcceptanceStatus.ACCEPTED
    assert events == [
        "SIGNATURE_CAPTURED",
        "SIGNED_COPY_GENERATED",
        "PROPOSAL_ACCEPTED",
    ]
    assert repository.values["client_ip_hash"] != "192.0.2.1"
    assert repository.values["client_user_agent_hash"] != "browser"
    assert repository.values["client_session_hash"] != "session"
    signed = next(tmp_path.rglob("signed-copy.pdf")).read_bytes()
    assert len(PdfReader(io.BytesIO(signed)).pages) == 2
    assert "SIGNED COPY" in PdfReader(io.BytesIO(signed)).pages[-1].extract_text()


def test_handwritten_acceptance_stores_only_png(tmp_path) -> None:
    service, repository, _ = _service(tmp_path)
    service.accept_proposal(
        build_acceptance_context(),
        _typed(
            signature_type=SignatureType.HANDWRITTEN,
            typed_signature=None,
            signature_png=_png(),
        ),
    )
    path = repository.values["signature_image_path"]
    assert isinstance(path, str) and path.endswith("signature.png")
    assert next(tmp_path.rglob("signature.png")).read_bytes().startswith(b"\x89PNG")


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"authorized": False}, "Authorization"),
        ({"legal_name": ""}, "signer name"),
        ({"email": "invalid"}, "signer name"),
        ({"company": ""}, "signer name"),
        ({"typed_signature": "Someone Else"}, "match"),
    ],
)
def test_acceptance_validation_rejects_invalid_typed_submissions(
    tmp_path, changes, message
) -> None:
    service, _, _ = _service(tmp_path)
    with pytest.raises(AcceptanceValidationError, match=message):
        service.accept_proposal(build_acceptance_context(), _typed(**changes))


@pytest.mark.parametrize(
    "value",
    [
        None,
        b"not-png",
        "data:image/svg+xml;base64,PHN2Zz4=",
        _png(size=(20, 10)),
        _png(drawn=False),
    ],
)
def test_signature_validation_rejects_invalid_images(value) -> None:
    with pytest.raises(AcceptanceValidationError):
        validate_signature_png(value)


def test_signature_validation_accepts_png_data_url() -> None:
    import base64

    value = "data:image/png;base64," + base64.b64encode(_png()).decode()
    assert validate_signature_png(value).startswith(b"\x89PNG")


def test_duplicate_acceptance_is_rejected_before_file_creation(tmp_path) -> None:
    repository = _Repository()
    repository.result = _acceptance(ProposalAcceptanceStatus.ACCEPTED)
    service, _, _ = _service(tmp_path, repository)
    with pytest.raises(AcceptanceAlreadyCompletedError):
        service.accept_proposal(build_acceptance_context(), _typed())
    assert not tuple(tmp_path.rglob("*"))


def test_rejection_records_reason_hashes_and_prevents_replay(tmp_path) -> None:
    service, repository, events = _service(tmp_path)
    rejected = service.reject_proposal(
        build_acceptance_context(),
        "  Not in budget  ",
        ip_address="192.0.2.8",
        session_identifier="client",
    )
    assert rejected.status == ProposalAcceptanceStatus.REJECTED
    assert repository.values["comments"] == "Not in budget"
    assert repository.values["client_ip_hash"] != "192.0.2.8"
    assert events == ["PROPOSAL_REJECTED"]


def test_signed_download_requires_accepted_record(tmp_path) -> None:
    service, _, _ = _service(tmp_path)
    with pytest.raises(AcceptanceUnavailableError):
        service.download_signed_copy(_acceptance(ProposalAcceptanceStatus.REJECTED))


def test_internal_and_portal_views_do_not_render_storage_paths() -> None:
    portal = Path(
        "src/leadpilot/presentation/streamlit/public/proposal_portal.py"
    ).read_text()
    workspace = Path(
        "src/leadpilot/presentation/streamlit/views/proposals.py"
    ).read_text()
    assert "Download Signed Copy" in portal
    assert "Acceptance history" in workspace
    assert "signature_image_path" not in portal
    assert "signature_image_path" not in workspace
