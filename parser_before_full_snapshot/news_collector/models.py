from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def image_status(images):
    statuses = {x.get("status","pending") for x in images}
    if not statuses:
        return "not_found"
    if "pending" in statuses:
        return "pending"
    if "saved" in statuses:
        return "partial" if "failed" in statuses else "saved"
    return "failed" if "failed" in statuses else "filtered"


def normalize_url(url: str) -> str:
    p = urlsplit(url.strip())
    if p.scheme not in ("https", "http") or not p.hostname or p.username or p.password:
        raise ValueError(f"Invalid public article URL: {url[:120]}")
    # Source configurations are trusted, but links extracted from HTML are not.
    if p.hostname == "localhost" or p.hostname.endswith((".localhost", ".local")):
        raise ValueError("Local hostname in article URL")
    try:
        address = ipaddress.ip_address(p.hostname)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ValueError("Non-public IP literal in article URL")
    query = [(k,v) for k,v in parse_qsl(p.query, keep_blank_values=True)
             if not k.lower().startswith("utm_") and k.lower() not in ("gclid", "fbclid", "yclid")]
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path or "/", urlencode(sorted(query)), ""))


@dataclass(frozen=True)
class Source:
    id: str
    name: str
    seeds: list[str]
    domains: list[str]
    article_pattern: str
    language: str
    publisher_country: str
    body_selectors: list[str] = field(default_factory=list)
    poll_seconds: int = 300
    min_interval_seconds: float = 6
    min_text_chars: int = 180
    enabled: bool = True
    topics: list[str] = field(default_factory=list)
    max_age_days: int = 14
    listing_scrolls: int = 0
    listing_pages: int = 1
    notes: str = ""
    article_query_pattern: str | None = None
    source_kind: str = "news_media"
    collection_priority: int = 50
    max_articles_per_cycle: int = 20
    listing_link_selectors: list[str] = field(default_factory=list)
    title_selectors: list[str] = field(default_factory=list)

    def accepts(self, url: str) -> bool:
        p = urlsplit(url)
        return (p.hostname in self.domains and bool(re.search(self.article_pattern, p.path))
                and (not self.article_query_pattern or bool(re.search(self.article_query_pattern,p.query))))

    def allows_host(self, url: str) -> bool:
        return urlsplit(url).hostname in self.domains


def load_sources(path, selected=()) -> list[Source]:
    data = json.loads(path.read_text(encoding="utf-8"))
    sources = [Source(**s) for s in data["sources"]]
    ids = [s.id for s in sources]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate source ids")
    unknown = set(selected) - set(ids)
    if unknown:
        raise ValueError(f"Unknown source ids: {sorted(unknown)}")
    result = [s for s in sources if s.id in selected] if selected else [s for s in sources if s.enabled]
    hosts = set()
    for s in result:
        if not re.fullmatch(r"[a-z0-9_-]+", s.id):
            raise ValueError("Source id must be a safe slug")
        re.compile(s.article_pattern)
        if s.article_query_pattern:
            re.compile(s.article_query_pattern)
        if s.max_age_days < 1 or not 0 <= s.listing_scrolls <= 3 or not 1 <= s.listing_pages <= 5:
            raise ValueError("Invalid source age/scroll/pagination limits")
        if not 0 <= s.collection_priority <= 100 or not 1 <= s.max_articles_per_cycle <= 1000:
            raise ValueError("Invalid source priority/article budget")
        if s.poll_seconds < 60 or s.min_interval_seconds < 1:
            raise ValueError("Poll >=60 seconds, domain navigation interval >=1 second")
        if hosts.intersection(s.domains):
            raise ValueError("Combine feeds for the same domain into a single source to share pacing")
        hosts.update(s.domains)
        for url in s.seeds:
            normalize_url(url)
            if not s.allows_host(url):
                raise ValueError("Seed outside source domain allowlist")
    return sorted(result,key=lambda s:s.collection_priority,reverse=True)


@dataclass
class Article:
    source_id: str
    source_name: str
    url: str
    canonical_url: str
    title: str
    text: str
    description: str | None
    authors: list[str]
    language: str
    publisher_country: str
    published_at: str | None
    published_at_raw: str | None
    publication_date_status: str
    modified_at: str | None
    fetched_at: str
    text_scope: str
    extraction_method: str
    raw_html_path: str
    quality_flags: list[str] = field(default_factory=list)
    source_tags: list[str] = field(default_factory=list)
    schema_version: int = 1
    topics: list[str] = field(default_factory=list)
    source_topics: list[str] = field(default_factory=list)
    relevance_score: int = 0
    source_kind: str = "news_media"
    images: list[dict] = field(default_factory=list)
    main_image_path: str | None = None

    def record(self):
        data = asdict(self)
        data["id"] = digest(self.canonical_url)
        data["content_hash"] = digest(re.sub(r"\s+", " ", self.title + "\n" + self.text).strip())
        data["text_hash"] = digest(re.sub(r"\s+", " ", self.text).strip().casefold())
        data["kind"] = "external_news"
        data["images_status"] = image_status(self.images)
        return data
