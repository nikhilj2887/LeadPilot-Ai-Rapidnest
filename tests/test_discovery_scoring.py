from __future__ import annotations

from leadpilot.infrastructure.discovery_scoring import calculate_scores, rating_label


def test_rating_boundaries() -> None:
    assert [
        rating_label(value) for value in (0, 20, 21, 40, 41, 60, 61, 80, 81, 100)
    ] == [
        "Very Low",
        "Very Low",
        "Low",
        "Low",
        "Moderate",
        "Moderate",
        "High",
        "High",
        "Very High",
        "Very High",
    ]


def test_scores_are_bounded_explainable_and_deterministic() -> None:
    data = {
        "is_https": True,
        "ssl_valid": True,
        "http_success": True,
        "page_title": "A",
    }
    first = calculate_scores(data)
    assert first == calculate_scores(data)
    for score in first.values():
        assert 0 <= score["value"] <= 100
        assert score["rating"]
        assert score["explanation"]
        assert isinstance(score["positive_factors"], list)
        assert isinstance(score["negative_factors"], list)


def test_automation_opportunity_rewards_visible_gaps() -> None:
    gaps = calculate_scores(
        {
            "contact_form_present": True,
            "whatsapp_present": True,
            "phone_present": True,
            "email_present": True,
        }
    )
    automated = calculate_scores(
        {
            "contact_form_present": True,
            "whatsapp_present": True,
            "phone_present": True,
            "email_present": True,
            "chatbot_present": True,
            "live_chat_present": True,
            "booking_system_present": True,
            "newsletter_present": True,
            "detected_technologies": [{"name": "HubSpot", "category": "Marketing"}],
        }
    )
    assert (
        gaps["automation_potential_score"]["value"]
        > automated["automation_potential_score"]["value"]
    )
    assert gaps["lead_priority_score"]["value"] != sum(
        score["value"] for score in gaps.values()
    ) / len(gaps)
