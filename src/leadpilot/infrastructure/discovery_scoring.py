from __future__ import annotations

from typing import Any


def rating_label(value: int) -> str:
    bounded = max(0, min(value, 100))
    if bounded <= 20:
        return "Very Low"
    if bounded <= 40:
        return "Low"
    if bounded <= 60:
        return "Moderate"
    if bounded <= 80:
        return "High"
    return "Very High"


def _score(
    name: str, value: int, positives: list[str], negatives: list[str]
) -> dict[str, Any]:
    bounded = max(0, min(100, value))
    return {
        "name": name,
        "value": bounded,
        "rating": rating_label(bounded),
        "explanation": f"{name} is {rating_label(bounded).lower()} based only on observable public website signals.",
        "positive_factors": positives,
        "negative_factors": negatives,
    }


def calculate_scores(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    def weighted(
        base: int, weights: dict[str, int]
    ) -> tuple[int, list[str], list[str]]:
        positives = [
            key.replace("_", " ")
            for key, weight in weights.items()
            if data.get(key) and weight > 0
        ]
        negatives = [
            key.replace("_", " ")
            for key, weight in weights.items()
            if not data.get(key) and weight > 0
        ]
        return (
            base + sum(weight for key, weight in weights.items() if data.get(key)),
            positives,
            negatives,
        )

    health_value, hp, hn = weighted(
        0,
        {
            "is_https": 15,
            "ssl_valid": 10,
            "http_success": 15,
            "page_title": 10,
            "meta_description": 10,
            "mobile_viewport_present": 10,
            "robots_txt_present": 8,
            "sitemap_present": 8,
            "privacy_policy_present": 5,
            "terms_page_present": 4,
            "acceptable_response_time": 5,
        },
    )
    modern = any(
        t["category"] in {"CMS", "Frontend", "Commerce"}
        for t in data.get("detected_technologies", [])
    )
    analytics = any(
        t["category"] in {"Analytics", "Marketing"}
        for t in data.get("detected_technologies", [])
    )
    marketing = any(
        t["name"] == "HubSpot" for t in data.get("detected_technologies", [])
    )
    maturity_signals = dict(data, modern_platform=modern, analytics_present=analytics)
    original = data
    data = maturity_signals
    maturity_value, mp, mn = weighted(
        5,
        {
            "modern_platform": 15,
            "analytics_present": 15,
            "social_links_present": 10,
            "linkedin_present": 5,
            "contact_form_present": 10,
            "newsletter_present": 8,
            "ecommerce_present": 8,
            "booking_system_present": 8,
            "about_page_present": 5,
            "careers_page_present": 5,
            "blog_present": 6,
        },
    )
    readiness_value, rp, rn = weighted(
        5,
        {
            "modern_platform": 18,
            "analytics_present": 15,
            "contact_form_present": 10,
            "live_chat_present": 10,
            "chatbot_present": 12,
            "booking_system_present": 10,
            "ecommerce_present": 10,
            "social_links_present": 8,
            "newsletter_present": 7,
        },
    )
    channels = sum(
        bool(original.get(k))
        for k in (
            "phone_present",
            "email_present",
            "whatsapp_present",
            "contact_form_present",
        )
    )
    opportunity = 25
    op: list[str] = []
    on: list[str] = []

    def add(condition: bool, points: int, message: str) -> None:
        nonlocal opportunity
        if condition:
            opportunity += points
            op.append(message)
        else:
            on.append(message)

    add(
        bool(original.get("contact_form_present") and not marketing),
        15,
        "Contact form without visible CRM indicators",
    )
    add(
        bool(original.get("whatsapp_present") and not original.get("chatbot_present")),
        12,
        "WhatsApp without visible chatbot",
    )
    add(
        not bool(original.get("booking_system_present")),
        8,
        "No public booking system detected",
    )
    add(channels >= 2, 12, "Multiple public contact channels")
    add(not bool(original.get("live_chat_present")), 8, "No live chat detected")
    add(
        not bool(original.get("newsletter_present")),
        7,
        "No newsletter automation detected",
    )
    if (
        original.get("chatbot_present")
        and marketing
        and original.get("booking_system_present")
    ):
        opportunity -= 20
        on.append("Extensive visible automation ecosystem")
    data = original
    reachable = bool(data.get("email_present") or data.get("phone_present"))
    engagement = bool(channels or data.get("social_links_present"))
    health_gap = 100 - min(100, health_value)
    maturity_gap = 100 - min(100, maturity_value)
    priority = (
        opportunity * 0.35
        + readiness_value * 0.20
        + maturity_gap * 0.15
        + health_gap * 0.10
        + (100 if engagement else 0) * 0.10
        + (100 if reachable else 0) * 0.10
    )
    return {
        "website_health_score": _score("Website Health", health_value, hp, hn),
        "digital_maturity_score": _score("Digital Maturity", maturity_value, mp, mn),
        "ai_readiness_score": _score("AI Readiness", readiness_value, rp, rn),
        "automation_potential_score": _score(
            "Automation Potential", opportunity, op, on
        ),
        "lead_priority_score": _score(
            "Lead Priority",
            round(priority),
            ["Visible business engagement"] if engagement else [],
            [] if reachable else ["No reachable contact details detected"],
        ),
    }
