from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", re.IGNORECASE)
PHONE_RE = re.compile(
    r"(?<!\w)(?:\+\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?){2,4}\d{3,4}"
)
PAGE_KEYWORDS = {
    "contact_page_present": ("contact",),
    "about_page_present": ("about", "company"),
    "careers_page_present": ("career", "jobs"),
    "blog_present": ("blog", "news"),
    "privacy_policy_present": ("privacy",),
    "terms_page_present": ("terms",),
}
PRIORITY_WORDS = tuple(word for words in PAGE_KEYWORDS.values() for word in words) + (
    "services",
    "products",
    "booking",
    "appointment",
)


class SignalParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.description = ""
        self.canonical_url = ""
        self.viewport = False
        self.links: list[str] = []
        self.scripts: list[str] = []
        self.metas: list[dict[str, str]] = []
        self.forms: list[dict[str, str]] = []
        self.text: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.casefold(): value or "" for key, value in attrs}
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            self.metas.append(values)
            name = values.get("name", "").casefold()
            if name == "description":
                self.description = values.get("content", "").strip()
            if name == "viewport":
                self.viewport = True
        elif tag == "link":
            if "canonical" in values.get("rel", "").casefold():
                self.canonical_url = values.get("href", "")
            if values.get("href"):
                self.links.append(values["href"])
        elif tag == "a" and values.get("href"):
            self.links.append(values["href"])
        elif tag == "script":
            self.scripts.append(values.get("src", ""))
        elif tag == "form":
            self.forms.append(values)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        clean = data.strip()
        if clean:
            self.text.append(clean)
            if self._in_title:
                self.title += clean


def analyze_html(html: str, page_url: str) -> dict[str, object]:
    parser = SignalParser()
    parser.feed(html)
    lower = html.casefold()
    text = " ".join(parser.text)
    resolved_links = [urljoin(page_url, link) for link in parser.links]
    social = [
        link
        for link in resolved_links
        if any(
            domain in (urlsplit(link).hostname or "").casefold()
            for domain in (
                "linkedin.com",
                "facebook.com",
                "instagram.com",
                "twitter.com",
                "x.com",
            )
        )
    ]
    emails = sorted(set(EMAIL_RE.findall(text + " " + html)))
    phones = sorted({match.group().strip() for match in PHONE_RE.finditer(text)})
    result: dict[str, object] = {
        "page_title": parser.title.strip() or None,
        "meta_description": parser.description or None,
        "canonical_url": urljoin(page_url, parser.canonical_url)
        if parser.canonical_url
        else None,
        "mobile_viewport_present": parser.viewport,
        "contact_form_present": bool(parser.forms),
        "newsletter_present": any(
            word in lower for word in ("newsletter", "subscribe", "mailchimp")
        ),
        "booking_system_present": any(
            word in lower
            for word in (
                "calendly",
                "acuityscheduling",
                "microsoft bookings",
                "appointment",
            )
        ),
        "ecommerce_present": any(
            word in lower
            for word in ("add to cart", "checkout", "shopify", "woocommerce")
        ),
        "whatsapp_present": "wa.me/" in lower or "whatsapp.com/" in lower,
        "phone_present": bool(phones),
        "email_present": bool(emails),
        "social_links_present": bool(social),
        "linkedin_present": any("linkedin.com" in item for item in social),
        "facebook_present": any("facebook.com" in item for item in social),
        "instagram_present": any("instagram.com" in item for item in social),
        "x_present": any(
            domain in item for item in social for domain in ("x.com", "twitter.com")
        ),
        "detected_emails": emails,
        "detected_phone_numbers": phones,
        "detected_social_links": sorted(set(social)),
        "internal_links": resolved_links,
    }
    for field, words in PAGE_KEYWORDS.items():
        result[field] = any(
            any(word in link.casefold() for word in words) for link in resolved_links
        )
    technologies = detect_technologies(html, {})
    engagement = {
        item["name"] for item in technologies if item["category"] == "Engagement"
    }
    result["live_chat_present"] = bool(
        engagement & {"Intercom", "Tawk.to", "Zendesk", "Crisp", "Freshchat"}
    )
    result["chatbot_present"] = "Drift" in engagement or "chatbot" in lower
    result["unknown_chat_widget_present"] = (
        "chat-widget" in lower
        and not result["live_chat_present"]
        and not result["chatbot_present"]
    )
    return result


INDICATORS = (
    ("WordPress", "CMS", ("wp-content", "wp-includes")),
    ("Shopify", "Commerce", ("cdn.shopify.com", "shopify.theme")),
    ("Wix", "CMS", ("wixstatic.com", "wix.com")),
    ("Squarespace", "CMS", ("static.squarespace.com", "squarespace")),
    ("Webflow", "CMS", ("webflow.js", "webflow.com")),
    ("Drupal", "CMS", ("drupal-settings-json", "/sites/default/files")),
    ("Joomla", "CMS", ("/media/system/js/", 'content="joomla')),
    ("Next.js", "Frontend", ("__next_data__", "/_next/")),
    ("React", "Frontend", ("data-reactroot", "react-dom")),
    ("Angular", "Frontend", ("ng-version", "angular.js")),
    ("Vue", "Frontend", ("data-v-", "vue.js")),
    ("Nuxt", "Frontend", ("__nuxt__", "/_nuxt/")),
    ("Svelte", "Frontend", ("svelte-", "/_app/immutable/")),
    ("Laravel", "Backend", ("laravel_session", "csrf-token")),
    ("Django", "Backend", ("csrfmiddlewaretoken", "__admin_media_prefix__")),
    ("Ruby on Rails", "Backend", ("csrf-param", "rails-ujs")),
    ("Google Analytics", "Analytics", ("google-analytics.com", "gtag(")),
    ("Google Tag Manager", "Analytics", ("googletagmanager.com", "gtm-")),
    ("Meta Pixel", "Marketing", ("connect.facebook.net/en_us/fbevents", "fbq(")),
    ("HubSpot", "Marketing", ("js.hs-scripts.com", "hubspot")),
    ("Hotjar", "Analytics", ("static.hotjar.com", "hj(")),
    ("Intercom", "Engagement", ("widget.intercom.io", "intercomsettings")),
    ("Drift", "Engagement", ("js.driftt.com", "drift.load")),
    ("Tawk.to", "Engagement", ("embed.tawk.to", "tawk_api")),
    ("Zendesk", "Engagement", ("static.zdassets.com", "zopim")),
    ("Crisp", "Engagement", ("client.crisp.chat", "$crisp")),
    ("Freshchat", "Engagement", ("wchat.freshchat.com", "freshchat")),
    ("WooCommerce", "Commerce", ("woocommerce", "wc-add-to-cart")),
    ("Calendly", "Booking", ("assets.calendly.com", "calendly-inline-widget")),
    (
        "Microsoft Bookings",
        "Booking",
        ("outlook.office365.com/owa/calendar", "microsoft bookings"),
    ),
    (
        "Acuity Scheduling",
        "Booking",
        ("acuityscheduling.com", "squarespacescheduling.com"),
    ),
)


def detect_technologies(html: str, headers: dict[str, str]) -> list[dict[str, object]]:
    haystack = f"{html} {' '.join(f'{k}:{v}' for k, v in headers.items())}".casefold()
    found: list[dict[str, object]] = []
    for name, category, needles in INDICATORS:
        evidence = [
            f"{needle} indicator detected" for needle in needles if needle in haystack
        ]
        if evidence:
            found.append(
                {
                    "name": name,
                    "category": category,
                    "confidence": "High" if len(evidence) > 1 else "Medium",
                    "evidence": evidence,
                }
            )
    server = headers.get("server", "").casefold()
    powered = headers.get("x-powered-by", "").casefold()
    for name, needle in (
        ("ASP.NET", "asp.net"),
        ("PHP", "php"),
        ("Node.js", "express"),
    ):
        if needle in server or needle in powered:
            found.append(
                {
                    "name": name,
                    "category": "Backend",
                    "confidence": "High",
                    "evidence": [f"response header contains {needle}"],
                }
            )
    return found


def prioritized_internal_links(links: list[str], origin: str, limit: int) -> list[str]:
    origin_host = (urlsplit(origin).hostname or "").removeprefix("www.")
    unique: dict[str, None] = {}
    for link in links:
        parsed = urlsplit(link)
        host = (parsed.hostname or "").removeprefix("www.")
        if parsed.scheme in {"http", "https"} and host == origin_host:
            clean = parsed._replace(fragment="").geturl()
            if any(word in clean.casefold() for word in PRIORITY_WORDS):
                unique[clean] = None
    return list(unique)[:limit]
