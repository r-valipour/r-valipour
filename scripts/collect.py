#!/usr/bin/env python3
"""
RaazNet — Iran cybersecurity news calendar.

Reads sources.yml, gathers items from RSS feeds, Google News searches and
social media, filters them for Iran + cybersecurity relevance, and writes
one dated Markdown file per day into news/.

Run it yourself with:   python3 scripts/collect.py
Nothing is written outside news/ .
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "sources.yml"
NEWS_DIR = ROOT / "news"
SEEN_FILE = NEWS_DIR / ".seen.json"

PERSIAN = re.compile(r"[\u0600-\u06ff]")

UA = "Mozilla/5.0 (compatible; RaazNetCalendar/1.0; +https://github.com/r-valipour)"
TIMEOUT = 25


# ─────────────────────────── helpers ───────────────────────────

def log(msg: str) -> None:
    print(msg, flush=True)


def fetch(url: str) -> bytes | None:
    """GET a URL, returning None instead of raising on any failure."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.read()
    except Exception as exc:  # noqa: BLE001 - a dead source must not kill the run
        log(f"    ! skipped ({type(exc).__name__}): {url}")
        return None


def clean(text: str, limit: int = 400) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit] + ("…" if len(text) > limit else "")


def entry_date(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        parsed = entry.get(key)
        if parsed:
            return datetime(*parsed[:6], tzinfo=timezone.utc)
    return None


def item_id(url: str, title: str) -> str:
    return hashlib.sha1(f"{url}|{title}".encode()).hexdigest()[:16]


# ─────────────────────────── relevance ───────────────────────────

class Matcher:
    def __init__(self, keywords: dict):
        self.iran = [k.lower() for k in keywords.get("iran", [])]
        self.cyber = [k.lower() for k in keywords.get("cyber", [])]

    def hits(self, text: str) -> tuple[list[str], list[str]]:
        low = text.lower()
        return (
            [k for k in self.iran if k in low],
            [k for k in self.cyber if k in low],
        )

    def is_relevant(self, text: str, require_both: bool) -> tuple[bool, list[str]]:
        iran_hits, cyber_hits = self.hits(text)
        ok = bool(iran_hits and cyber_hits) if require_both else bool(iran_hits or cyber_hits)
        return ok, sorted(set(iran_hits + cyber_hits))


# ─────────────────────────── collectors ───────────────────────────

def read_feed(url: str, source: str, lang: str, category: str, cutoff: datetime) -> list[dict]:
    raw = fetch(url)
    if not raw:
        return []
    parsed = feedparser.parse(raw)
    out = []
    for entry in parsed.entries[:60]:
        when = entry_date(entry)
        if when and when < cutoff:
            continue
        link = entry.get("link", "")
        title = clean(entry.get("title", ""), 300)
        if not link or not title:
            continue
        summary = clean(entry.get("summary", ""))
        out.append(
            {
                "title": title,
                "url": link,
                "summary": summary,
                "source": source,
                # trust the script over the feed's declared language: English
                # feeds carry Persian items and vice versa
                "lang": "fa" if PERSIAN.search(title + summary) else lang,
                "category": category,
                "date": (when or datetime.now(timezone.utc)).isoformat(),
            }
        )
    return out


def google_news(query: str, lang: str, cutoff: datetime) -> list[dict]:
    """Google News RSS — this is the 'surf the web for hints' part."""
    params = (
        {"hl": "fa", "gl": "IR", "ceid": "IR:fa"}
        if lang == "fa"
        else {"hl": "en-US", "gl": "US", "ceid": "US:en"}
    )
    url = "https://news.google.com/rss/search?q=" + urllib.parse.quote(
        f"{query} when:7d"
    ) + "&" + urllib.parse.urlencode(params)
    return read_feed(url, f"Web search: {query}", lang, "search", cutoff)


def telegram_channel(channel: str, cutoff: datetime) -> list[dict]:
    """Scrape a public Telegram channel's web preview (t.me/s/<name>)."""
    raw = fetch(f"https://t.me/s/{channel}")
    if not raw:
        return []
    page = raw.decode("utf-8", "ignore")
    blocks = re.findall(
        r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', page, re.S
    )
    links = re.findall(r'href="(https://t\.me/[^/]+/\d+)"', page)
    out = []
    for i, body in enumerate(blocks[-25:]):
        text = clean(body, 500)
        if len(text) < 25:
            continue
        out.append(
            {
                "title": text[:160],
                "url": links[i] if i < len(links) else f"https://t.me/s/{channel}",
                "summary": text,
                "source": f"Telegram @{channel}",
                "lang": "fa" if PERSIAN.search(text) else "en",
                "category": "social",
                "date": datetime.now(timezone.utc).isoformat(),
            }
        )
    return out


def twitter_account(handle: str, instances: list[str], cutoff: datetime) -> list[dict]:
    """Nitter RSS. Mirrors go down constantly, so try each in turn."""
    for base in instances:
        items = read_feed(
            f"{base.rstrip('/')}/{handle}/rss", f"X @{handle}", "en", "social", cutoff
        )
        if items:
            return items
    return []


def reddit_sub(sub: str, cutoff: datetime) -> list[dict]:
    return read_feed(
        f"https://www.reddit.com/r/{sub}/new/.rss", f"Reddit r/{sub}", "en", "social", cutoff
    )


# ─────────────────────────── output ───────────────────────────

FLAG = {"fa": "🇮🇷 فارسی", "en": "🇬🇧 English"}
SECTIONS = [
    ("main", "📌 Main sources / منابع اصلی"),
    ("security", "🛡 Security press / رسانه‌های امنیتی"),
    ("persian", "📰 Persian press / رسانه‌های فارسی"),
    ("search", "🔎 Web hints / سرنخ‌های وب"),
    ("social", "💬 Social media / شبکه‌های اجتماعی"),
]


def render_day(day: str, items: list[dict]) -> str:
    lines = [
        f"# RaazNet — {day}",
        "",
        f"_Iran cybersecurity watch · {len(items)} items · "
        f"generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC_",
        "",
    ]
    for key, heading in SECTIONS:
        group = [i for i in items if i["category"] == key]
        if not group:
            continue
        lines += [f"## {heading}", "", f"_{len(group)} items_", ""]
        for it in sorted(group, key=lambda x: x["date"], reverse=True):
            lines.append(f"### [{it['title']}]({it['url']})")
            meta = f"`{it['source']}` · {FLAG.get(it['lang'], it['lang'])} · {it['date'][:10]}"
            if it.get("matched"):
                meta += " · " + " ".join(f"`{m}`" for m in it["matched"][:6])
            lines += [meta, ""]
            if it["summary"]:
                lines += [f"> {it['summary']}", ""]
        lines.append("---")
        lines.append("")
    lines += [
        "",
        "<sub>Collected automatically from `sources.yml`. "
        "Nothing here is verified — treat every item as a lead, not a fact.</sub>",
    ]
    return "\n".join(lines)


def rebuild_index() -> None:
    days = sorted(
        (p for p in NEWS_DIR.glob("20*.md")), key=lambda p: p.stem, reverse=True
    )
    lines = [
        "# 🗓 RaazNet Security Calendar",
        "",
        "Daily automated watch on Iran-related cybersecurity news, in English and Persian.",
        "",
        "| Date | Items |",
        "|---|---|",
    ]
    for path in days[:120]:
        count = len(re.findall(r"^### \[", path.read_text(encoding="utf-8"), re.M))
        lines.append(f"| [{path.stem}]({path.name}) | {count} |")
    lines += ["", f"_Last updated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC_"]
    (NEWS_DIR / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


# ─────────────────────────── main ───────────────────────────

def main() -> int:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    settings = cfg.get("settings", {})
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.get("lookback_days", 3))
    require_both = settings.get("require_both_topics", True)
    matcher = Matcher(cfg.get("keywords", {}))
    social = cfg.get("social", {}) or {}

    NEWS_DIR.mkdir(exist_ok=True)
    seen: dict = json.loads(SEEN_FILE.read_text()) if SEEN_FILE.exists() else {}

    raw_items: list[dict] = []
    trusted_ids: set[str] = set()  # items exempt from keyword filtering

    log("→ main sources")
    for f in cfg.get("main_feeds") or []:
        got = read_feed(f["url"], f["name"], f.get("lang", "en"), "main", cutoff)
        # a main source with `filter: false` bypasses keyword matching
        if not f.get("filter", True):
            for it in got:
                trusted_ids.add(item_id(it["url"], it["title"]))
        raw_items += got

    for key, category in (("security_feeds", "security"), ("persian_feeds", "persian")):
        log(f"→ {key}")
        for f in cfg.get(key) or []:
            raw_items += read_feed(f["url"], f["name"], f.get("lang", "en"), category, cutoff)

    log("→ web searches")
    for lang, queries in (cfg.get("search_queries") or {}).items():
        for q in queries:
            raw_items += google_news(q, lang, cutoff)
            time.sleep(1)  # be polite to Google News

    log("→ social media")
    for ch in social.get("telegram") or []:
        raw_items += telegram_channel(ch, cutoff)
    instances = social.get("nitter_instances") or ["https://nitter.net"]
    for handle in social.get("twitter") or []:
        raw_items += twitter_account(handle, instances, cutoff)
    for sub in social.get("reddit") or []:
        raw_items += reddit_sub(sub, cutoff)
    for f in social.get("fediverse") or []:
        raw_items += read_feed(f["url"], f["name"], f.get("lang", "en"), "social", cutoff)

    # filter + de-duplicate
    kept: list[dict] = []
    ids_today: set[str] = set()
    for it in raw_items:
        uid = item_id(it["url"], it["title"])
        if uid in seen or uid in ids_today:
            continue
        if uid in trusted_ids:
            it["matched"] = []
        else:
            ok, matched = matcher.is_relevant(
                f"{it['title']} {it['summary']}", require_both
            )
            if not ok:
                continue
            it["matched"] = matched
        ids_today.add(uid)
        kept.append(it)

    log(f"\n{len(raw_items)} fetched → {len(kept)} relevant and new")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if not kept:
        log("nothing new today; index left as-is")
        rebuild_index()
        return 0

    (NEWS_DIR / f"{today}.md").write_text(render_day(today, kept), encoding="utf-8")
    rebuild_index()

    # remember what we've published, trimmed to the most recent 5000 ids
    now = datetime.now(timezone.utc).isoformat()
    seen.update({uid: now for uid in ids_today})
    trimmed = dict(sorted(seen.items(), key=lambda kv: kv[1], reverse=True)[:5000])
    SEEN_FILE.write_text(json.dumps(trimmed, indent=0), encoding="utf-8")

    log(f"wrote news/{today}.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
