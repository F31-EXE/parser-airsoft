"""Сборка дайджеста: подробный Markdown для себя и черновик поста для ВК."""
from __future__ import annotations

from datetime import datetime

from .models import REGION_RUSSIA, REGION_TITLES, REGION_URAL, REGION_WORLD, NewsItem

REGION_ORDER = [REGION_URAL, REGION_RUSSIA, REGION_WORLD]
REGION_EMOJI = {REGION_URAL: "🏔", REGION_RUSSIA: "🇷🇺", REGION_WORLD: "🌍"}
TAG_TITLES = {
    "games": "игра/анонс",
    "law": "законы",
    "tournament": "турнир",
    "gear": "снаряжение",
}


def group_by_region(items: list[NewsItem], per_region: int) -> dict[str, list[NewsItem]]:
    groups: dict[str, list[NewsItem]] = {r: [] for r in REGION_ORDER}
    for item in items:
        groups.setdefault(item.region or REGION_RUSSIA, []).append(item)
    for region, lst in groups.items():
        lst.sort(key=lambda i: (i.score, i.published.timestamp() if i.published else 0), reverse=True)
        groups[region] = lst[:per_region]
    return groups


def _date(item: NewsItem) -> str:
    return item.published.strftime("%d.%m %H:%M") if item.published else "—"


def render_markdown(groups: dict[str, list[NewsItem]], generated: datetime) -> str:
    lines = [f"# Страйкбол-дайджест от {generated:%d.%m.%Y %H:%M}", ""]
    for region in REGION_ORDER:
        items = groups.get(region, [])
        lines.append(f"## {REGION_EMOJI[region]} {REGION_TITLES[region]} ({len(items)})")
        lines.append("")
        if not items:
            lines += ["_Ничего нового._", ""]
            continue
        for item in items:
            tags = ", ".join(TAG_TITLES.get(t, t) for t in item.tags)
            meta = f"{_date(item)} · {item.source}" + (f" · {tags}" if tags else "")
            lines.append(f"- **[{item.title}]({item.url})**  ")
            lines.append(f"  {meta}")
            if item.text and item.text.strip() != item.title.strip():
                snippet = " ".join(item.text.split())
                lines.append(f"  > {snippet[:300]}{'…' if len(snippet) > 300 else ''}")
        lines.append("")
    return "\n".join(lines)


def render_vk_post(groups: dict[str, list[NewsItem]], generated: datetime, hashtags: str = "") -> str:
    """Черновик поста. ВК не понимает Markdown, поэтому только текст, эмодзи и ссылки."""
    lines = [f"📰 Новости страйкбола — {generated:%d.%m.%Y}", ""]
    for region in REGION_ORDER:
        items = groups.get(region, [])
        if not items:
            continue
        lines.append(f"{REGION_EMOJI[region]} {REGION_TITLES[region].upper()}")
        for item in items:
            lines.append(f"▪ {item.title}")
            lines.append(f"  {item.url}")
        lines.append("")
    if hashtags:
        lines.append(hashtags)
    return "\n".join(lines).strip() + "\n"
