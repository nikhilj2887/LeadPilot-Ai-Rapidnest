from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from leadpilot.application.discovery import DiscoveryScan
from leadpilot.infrastructure.discovery_scoring import rating_label


@dataclass(frozen=True, slots=True)
class ScoreCard:
    label: str
    value: int
    rating: str
    explanation: str


def score_cards(scan: DiscoveryScan) -> list[ScoreCard]:
    details = scan.score_details or {}
    fields = (
        ("Website Health", "website_health_score"),
        ("Digital Maturity", "digital_maturity_score"),
        ("AI Readiness", "ai_readiness_score"),
        ("Automation Potential", "automation_potential_score"),
        ("Lead Priority", "lead_priority_score"),
    )
    return [
        ScoreCard(
            label=label,
            value=int(getattr(scan, field, 0)),
            rating=str(
                details.get(field, {}).get(
                    "rating", rating_label(int(getattr(scan, field, 0)))
                )
            ),
            explanation=str(
                details.get(field, {}).get(
                    "explanation", "Based on observable public website signals."
                )
            ),
        )
        for label, field in fields
    ]


def website_health_rows(scan: DiscoveryScan) -> list[dict[str, str]]:
    def present(value: bool, yes: str = "Yes", no: str = "No") -> str:
        return f"{'Pass' if value else 'Review'} — {yes if value else no}"

    return [
        {
            "Check": "HTTPS",
            "Result": present(scan.is_https),
            "Details": scan.final_url or scan.website_url,
        },
        {
            "Check": "SSL Valid",
            "Result": present(scan.ssl_valid),
            "Details": "Certificate validation remained enabled",
        },
        {
            "Check": "HTTP Status",
            "Result": "Pass"
            if scan.http_status_code and scan.http_status_code < 400
            else "Review",
            "Details": str(scan.http_status_code or "Unavailable"),
        },
        {
            "Check": "Response Time",
            "Result": "Measured",
            "Details": f"{scan.response_time_ms or 0} ms",
        },
        {
            "Check": "Page Title",
            "Result": present(bool(scan.page_title), "Present", "Missing"),
            "Details": scan.page_title or "No page title detected",
        },
        {
            "Check": "Meta Description",
            "Result": present(bool(scan.meta_description), "Present", "Missing"),
            "Details": scan.meta_description or "No meta description detected",
        },
        {
            "Check": "Mobile Viewport",
            "Result": present(scan.mobile_viewport_present, "Present", "Missing"),
            "Details": "Responsive viewport metadata",
        },
        {
            "Check": "robots.txt",
            "Result": present(scan.robots_txt_present, "Present", "Not detected"),
            "Details": "Public crawler guidance",
        },
        {
            "Check": "Sitemap",
            "Result": present(scan.sitemap_present, "Present", "Not detected"),
            "Details": "Public sitemap.xml",
        },
    ]


SIGNALS = (
    ("Contact Page", "contact_page_present"),
    ("About Page", "about_page_present"),
    ("Careers", "careers_page_present"),
    ("Blog", "blog_present"),
    ("Booking System", "booking_system_present"),
    ("Ecommerce", "ecommerce_present"),
    ("Contact Form", "contact_form_present"),
    ("Newsletter", "newsletter_present"),
    ("WhatsApp", "whatsapp_present"),
    ("Phone", "phone_present"),
    ("Email", "email_present"),
)


def signal_rows(scan: DiscoveryScan) -> list[dict[str, str]]:
    return [
        {
            "Signal": label,
            "Status": "Detected" if bool(getattr(scan, field)) else "Not Detected",
            "Evidence or Notes": (
                "Observable on the public website"
                if bool(getattr(scan, field))
                else "No public indicator found during this scan"
            ),
        }
        for label, field in SIGNALS
    ]


SEVERITY_MAP = {
    "Info": "Info",
    "Attention": "Improvement",
    "Improvement": "Improvement",
    "Opportunity": "Opportunity",
    "Important": "Important",
}


def finding_rows(findings: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "Severity": SEVERITY_MAP.get(str(item.get("severity")), "Info"),
            "Title": str(item.get("title", "Website observation")),
            "Evidence": str(item.get("evidence", "Public website signal")),
            "Explanation": str(
                item.get("explanation", "Based on observable website evidence.")
            ),
        }
        for item in findings
    ]


def opportunity_rows(items: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows = []
    for item in items:
        service = str(item.get("service_category", "Business Process Automation"))
        priority = (
            "High"
            if service in {"AI Chatbots", "WhatsApp Automation", "CRM"}
            else "Medium"
        )
        rows.append(
            {
                "RapidNest Service": {
                    "AI Chatbots": "AI Chatbot",
                    "CRM": "CRM Integration",
                }.get(service, service),
                "Opportunity": str(item.get("opportunity", "")),
                "Evidence": str(item.get("evidence", "")),
                "Suggested Outcome": str(
                    item.get("suggested_outcome", item.get("opportunity", ""))
                ),
                "Priority": priority,
            }
        )
    return rows


def social_link_rows(scan: DiscoveryScan) -> list[dict[str, str]]:
    platforms = (
        ("LinkedIn", "linkedin.com"),
        ("Facebook", "facebook.com"),
        ("Instagram", "instagram.com"),
        ("X", "x.com"),
        ("X", "twitter.com"),
    )
    seen: set[str] = set()
    rows: list[dict[str, str]] = []
    for raw in scan.detected_social_links:
        url = str(raw).strip()
        normalized = url.rstrip("/").casefold()
        if not url or normalized in seen:
            continue
        seen.add(normalized)
        host = (urlsplit(url).hostname or "").casefold()
        label = next((name for name, domain in platforms if domain in host), "Social")
        path = urlsplit(url).path.strip("/")
        rows.append(
            {
                "Platform": label,
                "Status": "Profile link" if path else "Platform indicator",
                "URL": url,
            }
        )
    return rows


def executive_summary(company_name: str, scan: DiscoveryScan) -> str:
    health = (
        "a technically healthy website"
        if scan.website_health_score >= 61
        else "a website with visible modernization opportunities"
    )
    channels = [
        label
        for label, value in (
            ("contact forms", scan.contact_form_present),
            ("email", scan.email_present),
            ("phone", scan.phone_present),
            ("WhatsApp", scan.whatsapp_present),
        )
        if value
    ]
    contact = (
        f" Public contact channels include {', '.join(channels)}."
        if channels
        else " Few public contact channels were detected."
    )
    gaps = []
    if not scan.chatbot_present:
        gaps.append("no chatbot")
    if not scan.booking_system_present:
        gaps.append("no automated booking workflow")
    gap_text = (
        f" However, {' and '.join(gaps)} was detected."
        if gaps
        else " Visible customer-engagement automation is already present."
    )
    return (
        f"{company_name} has {health}.{contact}{gap_text} "
        "These signals highlight evidence-based opportunities for lead capture and enquiry follow-up."
    )
