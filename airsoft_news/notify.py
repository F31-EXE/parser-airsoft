"""Отправка готового дайджеста себе в Telegram, чтобы не открывать файлы руками."""
from __future__ import annotations

import requests

TELEGRAM_LIMIT = 4096


def _chunks(text: str, limit: int = TELEGRAM_LIMIT) -> list[str]:
    chunks, current = [], ""
    for line in text.splitlines(keepends=True):
        if len(current) + len(line) > limit and current:
            chunks.append(current)
            current = ""
        current += line[:limit]
    if current:
        chunks.append(current)
    return chunks


def send_telegram(text: str, bot_token: str, chat_id: str) -> None:
    for chunk in _chunks(text):
        resp = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": chunk, "disable_web_page_preview": True},
            timeout=20,
        )
        resp.raise_for_status()
