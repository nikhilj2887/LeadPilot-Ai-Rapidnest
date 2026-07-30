from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from leadpilot.application.ai_foundation import AIInvalidRequestError
from leadpilot.application.prompt_templates import PromptTemplateService
from leadpilot.infrastructure.database.base import Base
from leadpilot.infrastructure.database.models import (
    OrganizationModel,
    PromptTemplateModel,
)
from leadpilot.infrastructure.database.prompt_template_repository import (
    SqlAlchemyPromptTemplateRepository,
)


def test_prompt_versions_resolution_rendering_and_tenant_isolation() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)
    with factory.begin() as session:
        first = OrganizationModel(slug="prompt-a", display_name="A")
        second = OrganizationModel(slug="prompt-b", display_name="B")
        platform = PromptTemplateModel(
            template_key="foundation.test",
            version=1,
            name="Platform",
            system_template="System {name}",
            user_template="User {name}",
            response_schema_version="1",
            is_active=True,
        )
        session.add_all((first, second, platform))
        session.flush()
        ids = first.id, second.id
    first_service = PromptTemplateService(
        SqlAlchemyPromptTemplateRepository(factory, ids[0])
    )
    second_service = PromptTemplateService(
        SqlAlchemyPromptTemplateRepository(factory, ids[1])
    )
    assert first_service.get_active_template("foundation.test").organization_id is None
    override = first_service.create_template_version(
        "foundation.test", "Tenant", "Tenant {name}", "Request {name}", "1"
    )
    assert override.version == 1
    first_service.activate_version(override.id)
    system, user, resolved = first_service.render_template(
        "foundation.test", {"name": "Acme"}
    )
    assert (system, user, resolved.organization_id) == (
        "Tenant Acme",
        "Request Acme",
        ids[0],
    )
    assert second_service.get_active_template("foundation.test").organization_id is None
    with pytest.raises(AIInvalidRequestError, match="Missing"):
        first_service.render_template("foundation.test", {})
