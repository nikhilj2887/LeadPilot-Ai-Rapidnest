from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

from leadpilot.application.discovery import DiscoveryError
from leadpilot.infrastructure.discovery_analysis import (
    analyze_html,
    detect_technologies,
    prioritized_internal_links,
)
from leadpilot.infrastructure.discovery_client import WebsiteClient
from leadpilot.infrastructure.discovery_scoring import calculate_scores
from leadpilot.infrastructure.discovery_security import validate_public_url


class WebsiteScanner:
    def __init__(self, client: WebsiteClient, *, max_pages: int, slow_ms: int) -> None:
        self._client = client
        self._max_pages = max(1, min(max_pages, 20))
        self._slow_ms = slow_ms

    def scan(self, website_url: str) -> dict[str, Any]:
        normalized = validate_public_url(website_url)
        home = self._client.fetch(normalized)
        signals = analyze_html(home.text, home.url)
        technologies = detect_technologies(home.text, home.headers)
        links = prioritized_internal_links(
            list(signals.pop("internal_links", [])), home.url, self._max_pages - 1
        )
        for link in links:
            try:
                page = self._client.fetch(link)
            except DiscoveryError:
                continue
            page_signals = analyze_html(page.text, page.url)
            technologies.extend(detect_technologies(page.text, page.headers))
            for key, value in page_signals.items():
                if key.startswith("detected_"):
                    signals[key] = sorted(set(signals.get(key, [])) | set(value))  # type: ignore[arg-type]
                elif isinstance(value, bool):
                    signals[key] = bool(signals.get(key)) or value
        robots_present = self._probe(urljoin(home.url, "/robots.txt"), "text")
        sitemap_present = self._probe(urljoin(home.url, "/sitemap.xml"), "xml")
        unique_tech = {item["name"]: item for item in technologies}
        data: dict[str, Any] = {
            **signals,
            "http_status_code": home.status_code,
            "final_url": home.url,
            "response_time_ms": home.response_time_ms,
            "is_https": home.url.startswith("https://"),
            "ssl_valid": home.url.startswith("https://"),
            "http_success": 200 <= home.status_code < 400,
            "acceptable_response_time": home.response_time_ms <= self._slow_ms,
            "robots_txt_present": robots_present,
            "sitemap_present": sitemap_present,
            "detected_technologies": list(unique_tech.values()),
        }
        scores = calculate_scores(data)
        data.update({name: score["value"] for name, score in scores.items()})
        findings, recommendations = build_findings(data)
        data.update(
            score_details=scores,
            findings=findings,
            recommendations=recommendations,
        )
        return data

    def _probe(self, url: str, expected: str) -> bool:
        try:
            result = self._client.fetch(url, require_html=False)
            content_type = result.headers.get("content-type", "").casefold()
            return result.status_code < 400 and (
                expected in content_type or bool(result.text.strip())
            )
        except DiscoveryError:
            return False


def build_findings(
    data: dict[str, Any],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    rules = (
        (
            not data.get("chatbot_present"),
            "Opportunity",
            "No chatbot detected on the public website.",
            "AI Chatbots",
            "Evaluate an AI-assisted support chatbot for common enquiries and lead qualification.",
        ),
        (
            data.get("whatsapp_present") and not data.get("chatbot_present"),
            "Opportunity",
            "WhatsApp is available, but no automated interaction was detected.",
            "WhatsApp Automation",
            "Consider WhatsApp automation for FAQs, routing, and appointment follow-up.",
        ),
        (
            data.get("contact_form_present")
            and not any(
                t["name"] == "HubSpot" for t in data.get("detected_technologies", [])
            ),
            "Opportunity",
            "Contact forms are present without visible CRM integration indicators.",
            "CRM",
            "Assess CRM integration to centralize enquiries and automate sales follow-up.",
        ),
        (
            not data.get("booking_system_present"),
            "Info",
            "No public booking system was detected.",
            "Business Process Automation",
            "Consider online scheduling if the business handles appointments or consultations.",
        ),
        (
            data.get("website_health_score", 0) < 60,
            "Attention",
            "The website has observable health or metadata gaps.",
            "Website Modernization",
            "Review the reported website health gaps to improve usability and discoverability.",
        ),
    )
    findings = []
    recommendations = []
    for condition, severity, title, category, opportunity in rules:
        if condition:
            findings.append(
                {
                    "severity": severity,
                    "title": title,
                    "evidence": title,
                    "explanation": "Based on publicly observable website signals only.",
                }
            )
            recommendations.append(
                {
                    "service_category": category,
                    "opportunity": opportunity,
                    "evidence": title,
                    "suggested_outcome": opportunity,
                }
            )
    return findings, recommendations
