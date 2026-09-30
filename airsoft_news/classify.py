"""Фильтрация по теме, определение региона и тегов.

Слова в конфиге задаются основами («страйкбол», «екатеринбург») — совпадение ищется
с начала слова, поэтому «страйкбол» найдёт и «страйкбольный», и «страйкболистов».
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from .models import REGION_RUSSIA, REGION_URAL, REGION_WORLD, NewsItem

CYRILLIC = re.compile(r"[а-яё]", re.IGNORECASE)


def _pattern(words: list[str]) -> re.Pattern | None:
    words = [w.strip().lower() for w in words if w and w.strip()]
    if not words:
        return None
    return re.compile(r"(?<!\w)(?:" + "|".join(re.escape(w) for w in words) + ")", re.IGNORECASE)


class Classifier:
    def __init__(self, cfg: dict):
        self.keywords = _pattern(cfg.get("keywords", []))
        self.exclude = _pattern(cfg.get("exclude", []))
        self.ural = _pattern(cfg.get("ural_places", []))
        self.tags = {tag: _pattern(words) for tag, words in cfg.get("tags", {}).items()}

    def is_relevant(self, item: NewsItem) -> bool:
        text = item.full_text
        if self.exclude and self.exclude.search(text):
            return False
        if item.always_relevant:
            return True
        return bool(self.keywords and self.keywords.search(text))

    def region_of(self, item: NewsItem) -> str:
        text = item.full_text
        if item.region == REGION_URAL or (self.ural and self.ural.search(text)):
            return REGION_URAL
        if item.region in (REGION_RUSSIA, REGION_WORLD):
            return item.region
        return REGION_RUSSIA if CYRILLIC.search(text) else REGION_WORLD

    def apply(self, item: NewsItem) -> NewsItem:
        item.region = self.region_of(item)
        item.tags = [tag for tag, pat in self.tags.items() if pat and pat.search(item.full_text)]
        hits = len(self.keywords.findall(item.full_text)) if self.keywords else 0
        # Чем больше упоминаний темы и тегов — тем выше в дайджесте.
        item.score = hits + 2 * len(item.tags)
        return item


def filter_items(items: list[NewsItem], classifier: Classifier, since: datetime) -> list[NewsItem]:
    result = []
    for item in items:
        if item.published is not None:
            published = item.published if item.published.tzinfo else item.published.replace(tzinfo=timezone.utc)
            if published < since:
                continue
        if classifier.is_relevant(item):
            result.append(classifier.apply(item))
    return result
