"""SQLite-база уже виденных новостей, чтобы не показывать одно и то же дважды."""
from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import NewsItem
from .sources import normalize_title


def _url_key(url: str) -> str:
    # Отбрасываем utm-метки и якоря, чтобы одна ссылка с разными хвостами считалась одной.
    base = url.split("#", 1)[0]
    if "?" in base:
        path, query = base.split("?", 1)
        kept = "&".join(p for p in query.split("&") if not p.startswith("utm_"))
        base = f"{path}?{kept}" if kept else path
    return hashlib.sha1(base.rstrip("/").encode()).hexdigest()


class Storage:
    def __init__(self, path: str | Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS seen ("
            " url_key TEXT PRIMARY KEY, title_key TEXT, url TEXT, title TEXT,"
            " source TEXT, region TEXT, first_seen TEXT)"
        )
        self.db.execute("CREATE INDEX IF NOT EXISTS seen_title ON seen(title_key)")

    def filter_new(self, items: list[NewsItem]) -> list[NewsItem]:
        """Возвращает только новые записи и сразу помечает их как виденные."""
        now = datetime.now(timezone.utc).isoformat()
        fresh = []
        for item in items:
            url_key = _url_key(item.url)
            title_key = normalize_title(item.title)
            dup = self.db.execute(
                "SELECT 1 FROM seen WHERE url_key = ? OR (title_key = ? AND length(?) > 20)",
                (url_key, title_key, title_key),
            ).fetchone()
            if dup:
                continue
            self.db.execute(
                "INSERT INTO seen VALUES (?, ?, ?, ?, ?, ?, ?)",
                (url_key, title_key, item.url, item.title, item.source, item.region, now),
            )
            fresh.append(item)
        self.db.commit()
        return fresh

    def close(self) -> None:
        self.db.close()
