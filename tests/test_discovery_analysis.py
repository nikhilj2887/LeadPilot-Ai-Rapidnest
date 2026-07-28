from __future__ import annotations

from leadpilot.infrastructure.discovery_analysis import (
    analyze_html,
    detect_technologies,
)

HTML = """
<html><head><title>Acme</title><meta name="description" content="Widgets">
<meta name="viewport" content="width=device-width"><script src="/wp-content/react-dom.js"></script>
<script src="https://www.google-analytics.com/analytics.js"></script>
<script src="https://widget.intercom.io/widget/a"></script></head><body>
<a href="/contact">Contact</a><a href="/about">About</a>
<a href="https://linkedin.com/company/acme">LinkedIn</a>
<a href="https://wa.me/15551234567">WhatsApp</a>
<form><input type="email"></form> hello@acme.example +1 555 123 4567
</body></html>
"""


def test_html_metadata_and_business_signals() -> None:
    result = analyze_html(HTML, "https://acme.example/")
    assert result["page_title"] == "Acme"
    assert result["meta_description"] == "Widgets"
    assert result["mobile_viewport_present"] is True
    assert result["contact_page_present"] is True
    assert result["about_page_present"] is True
    assert result["contact_form_present"] is True
    assert result["whatsapp_present"] is True
    assert result["linkedin_present"] is True
    assert "hello@acme.example" in result["detected_emails"]
    assert result["phone_present"] is True
    assert result["live_chat_present"] is True
    assert result["chatbot_present"] is False


def test_technology_detection_has_evidence() -> None:
    found = detect_technologies(
        HTML + " js.hs-scripts.com cdn.shopify.com __next_data__",
        {"x-powered-by": "PHP"},
    )
    names = {item["name"] for item in found}
    assert {
        "WordPress",
        "React",
        "Next.js",
        "Shopify",
        "Google Analytics",
        "HubSpot",
        "Intercom",
        "PHP",
    } <= names
    assert all(item["evidence"] for item in found)
