"""Сборщики новостей из разных источников.

Каждый сборщик получает словарь с настройками источника из config.yaml
и возвращает список NewsItem. Ошибка одного источника не должна ронять весь запуск,
поэтому исключения ловятся в collect_all.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser
import requests
from bs4 import BeautifulSoup

from .models import NewsItem

log = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (compatible; airsoft-news-bot/1.0)"
VK_API = "https://api.vk.com/method/"
VK_API_VERSION = "5.199"
TIMEOUT = 20


def _get(url: str, **kwargs) -> requests.Response:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT, **kwargs)
    resp.raise_for_status()
    return resp


def _strip_html(html: str) -> str:
    return BeautifulSoup(html or "", "html.parser").get_text(" ", strip=True)


def _first_line(text: str, limit: int = 120) -> str:
    line = next((l.strip() for l in text.splitlines() if l.strip()), "")
    return line if len(line) <= limit else line[: limit - 1].rstrip() + "…"


# ---------- RSS / Atom ----------

def parse_rss(content: bytes | str, name: str) -> list[NewsItem]:
    feed = feedparser.parse(content)
    items = []
    for entry in feed.entries:
        published = None
        parsed = entry.get("published_parsed") or entry.get("updated_parsed")
        if parsed:
            published = datetime(*parsed[:6], tzinfo=timezone.utc)
        elif entry.get("published"):
            try:
                published = parsedate_to_datetime(entry.published)
            except (TypeError, ValueError):
                pass
        items.append(NewsItem(
            source=name,
            title=_strip_html(entry.get("title", "")),
            url=entry.get("link", ""),
            text=_strip_html(entry.get("summary", "")),
            published=published,
        ))
    return items


def fetch_rss(cfg: dict) -> list[NewsItem]:
    return parse_rss(_get(cfg["url"]).content, cfg.get("name", cfg["url"]))


# ---------- ВКонтакте ----------

def _vk_call(method: str, params: dict, token: str) -> dict:
    resp = _get(VK_API + method, params={**params, "access_token": token, "v": VK_API_VERSION})
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"VK API {method}: {data['error'].get('error_msg')}")
    # Ограничение VK API — не больше 3 запросов в секунду.
    time.sleep(0.35)
    return data["response"]


def vk_posts_to_items(posts: list[dict], name: str) -> list[NewsItem]:
    items = []
    for post in posts:
        text = post.get("text", "")
        # Репосты: текст лежит в copy_history.
        if not text and post.get("copy_history"):
            text = post["copy_history"][0].get("text", "")
        if not text.strip():
            continue
        items.append(NewsItem(
            source=name,
            title=_first_line(text),
            url=f"https://vk.com/wall{post['owner_id']}_{post['id']}",
            text=text,
            published=datetime.fromtimestamp(post["date"], tz=timezone.utc),
        ))
    return items


def fetch_vk_wall(cfg: dict, token: str) -> list[NewsItem]:
    """Стена сообщества/страницы. Хватает сервисного ключа приложения."""
    params = {"count": cfg.get("count", 30)}
    if str(cfg["group"]).lstrip("-").isdigit():
        params["owner_id"] = cfg["group"]
    else:
        params["domain"] = cfg["group"]
    response = _vk_call("wall.get", params, token)
    posts = [p for p in response["items"] if not p.get("is_pinned")]
    return vk_posts_to_items(posts, cfg.get("name", f"vk.com/{cfg['group']}"))


def fetch_vk_search(cfg: dict, token: str, since: datetime) -> list[NewsItem]:
    """Поиск по всем открытым постам ВК (newsfeed.search). Нужен пользовательский токен."""
    response = _vk_call("newsfeed.search", {
        "q": cfg["query"],
        "count": cfg.get("count", 100),
        "start_time": int(since.timestamp()),
    }, token)
    return vk_posts_to_items(response["items"], cfg.get("name", f"Поиск ВК: {cfg['query']}"))


# ---------- Telegram (публичные каналы через веб-превью t.me/s/) ----------

def parse_telegram(html: str, name: str) -> list[NewsItem]:
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for msg in soup.select("div.tgme_widget_message[data-post]"):
        text_el = msg.select_one("div.tgme_widget_message_text")
        if text_el is None:
            continue
        for br in text_el.find_all("br"):
            br.replace_with("\n")
        text = text_el.get_text().strip()
        time_el = msg.select_one("a.tgme_widget_message_date time[datetime]")
        published = datetime.fromisoformat(time_el["datetime"]) if time_el else None
        items.append(NewsItem(
            source=name,
            title=_first_line(text),
            url=f"https://t.me/{msg['data-post']}",
            text=text,
            published=published,
        ))
    return items


def fetch_telegram(cfg: dict) -> list[NewsItem]:
    channel = cfg["channel"].lstrip("@")
    return parse_telegram(_get(f"https://t.me/s/{channel}").text, cfg.get("name", f"t.me/{channel}"))


# ---------- Общий запуск ----------

def collect_all(sources: list[dict], vk_token: str | None, since: datetime) -> list[NewsItem]:
    result: list[NewsItem] = []
    for cfg in sources:
        kind = cfg.get("type")
        label = cfg.get("name") or cfg.get("url") or cfg.get("group") or cfg.get("channel") or cfg.get("query")
        try:
            if kind == "rss":
                items = fetch_rss(cfg)
            elif kind in ("vk_wall", "vk_search"):
                if not vk_token:
                    log.warning("Пропускаю %s: не задан VK_TOKEN", label)
                    continue
                items = fetch_vk_wall(cfg, vk_token) if kind == "vk_wall" else fetch_vk_search(cfg, vk_token, since)
            elif kind == "telegram":
                items = fetch_telegram(cfg)
            else:
                log.warning("Неизвестный тип источника %r у %s", kind, label)
                continue
        except Exception as exc:  # noqa: BLE001 — один сломанный источник не должен ронять весь сбор
            log.error("Ошибка источника %s: %s", label, exc)
            continue

        for item in items:
            item.region = cfg.get("region")
            item.always_relevant = bool(cfg.get("always_relevant", False))
        log.info("%s: %d записей", label, len(items))
        result.extend(items)
    return result


def normalize_title(title: str) -> str:
    return re.sub(r"[^\w]+", " ", title.lower()).strip()
