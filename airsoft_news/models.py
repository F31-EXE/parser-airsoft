from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

REGION_URAL = "ural"
REGION_RUSSIA = "russia"
REGION_WORLD = "world"

REGION_TITLES = {
    REGION_URAL: "Свердловская область",
    REGION_RUSSIA: "Россия",
    REGION_WORLD: "Мир",
}


@dataclass
class NewsItem:
    source: str
    title: str
    url: str
    text: str = ""
    published: datetime | None = None
    # Регион по умолчанию берётся из настроек источника, classify может его уточнить.
    region: str | None = None
    # Источник целиком про страйкбол — фильтр по ключевым словам не нужен.
    always_relevant: bool = False
    tags: list[str] = field(default_factory=list)
    score: int = 0

    @property
    def full_text(self) -> str:
        return f"{self.title}\n{self.text}"
