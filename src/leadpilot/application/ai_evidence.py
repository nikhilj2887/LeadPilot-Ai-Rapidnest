from __future__ import annotations

import hashlib
import json
from typing import Any

from leadpilot.application.discovery import DiscoveryScan

BOOLEAN_IDS = {
    "is_https": "website.https",
    "ssl_valid": "website.ssl_valid",
    "mobile_viewport_present": "website.mobile_viewport",
    "robots_txt_present": "website.robots_txt",
    "sitemap_present": "website.sitemap",
    "contact_page_present": "page.contact",
    "about_page_present": "page.about",
    "careers_page_present": "page.careers",
    "blog_present": "page.blog",
    "privacy_policy_present": "page.privacy",
    "terms_page_present": "page.terms",
    "contact_form_present": "contact.form",
    "newsletter_present": "engagement.newsletter",
    "booking_system_present": "page.booking",
    "ecommerce_present": "commerce.ecommerce",
    "live_chat_present": "engagement.live_chat",
    "chatbot_present": "engagement.chatbot",
    "whatsapp_present": "engagement.whatsapp",
    "phone_present": "contact.phone",
    "email_present": "contact.email",
    "social_links_present": "social.any",
    "linkedin_present": "social.linkedin",
    "facebook_present": "social.facebook",
    "instagram_present": "social.instagram",
    "x_present": "social.x",
}


def build_snapshot(company: Any, scan: DiscoveryScan) -> dict[str, Any]:
    evidence: dict[str, Any] = {
        evidence_id: {"observed": bool(getattr(scan, field, False)), "source": field}
        for field, evidence_id in BOOLEAN_IDS.items()
    }
    evidence["website.response_time"] = {"value_ms": scan.response_time_ms}
    for technology in scan.detected_technologies:
        key = "".join(c if c.isalnum() else "_" for c in str(technology).lower()).strip(
            "_"
        )
        evidence[f"technology.{key}"] = {
            "detected": True,
            "name": str(technology)[:120],
        }
    return {
        "company": {
            key: getattr(company, key, None)
            for key in (
                "name",
                "website",
                "industry",
                "country",
                "city",
                "company_size",
            )
        },
        "scan": {
            "id": scan.id,
            "website_url": scan.website_url,
            "scores": {
                key: getattr(scan, key)
                for key in (
                    "website_health_score",
                    "digital_maturity_score",
                    "ai_readiness_score",
                    "automation_potential_score",
                    "lead_priority_score",
                )
            },
            "score_details": scan.score_details,
            "findings": scan.findings,
            "rule_based_opportunities": scan.recommendations,
        },
        "evidence_catalogue": evidence,
    }


def snapshot_hash(snapshot: dict[str, Any]) -> str:
    normalized = json.dumps(
        snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256(normalized.encode()).hexdigest()


def evidence_references(output: Any) -> set[str]:
    refs: set[str] = set()
    data = output.model_dump()

    def visit(value: Any, key: str = "") -> None:
        if isinstance(value, dict):
            for child_key, child in value.items():
                visit(child, child_key)
        elif isinstance(value, list):
            if key in {"evidence", "evidence_references"}:
                refs.update(item for item in value if isinstance(item, str))
            else:
                for child in value:
                    visit(child, key)

    visit(data)
    return refs
