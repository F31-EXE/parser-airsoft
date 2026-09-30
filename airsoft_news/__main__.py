"""Запуск: python -m airsoft_news [--config config.yaml] [--days 3] [--send-telegram]"""
from __future__ import annotations

import argparse
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from .classify import Classifier, filter_items
from .digest import group_by_region, render_markdown, render_vk_post
from .notify import send_telegram
from .sources import collect_all
from .storage import Storage


def main() -> None:
    parser = argparse.ArgumentParser(description="Сбор новостей страйкбола в дайджест")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--days", type=int, help="Брать новости не старше N дней (перекрывает конфиг)")
    parser.add_argument("--out", default="output", help="Папка для дайджестов")
    parser.add_argument("--db", default="data/seen.sqlite3", help="База уже виденных новостей")
    parser.add_argument("--no-dedup", action="store_true", help="Не учитывать ранее виденные новости")
    parser.add_argument("--send-telegram", action="store_true",
                        help="Отправить черновик поста в Telegram (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(message)s")
    log = logging.getLogger("airsoft_news")

    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=args.days or cfg.get("max_age_days", 7))

    raw = collect_all(cfg.get("sources", []), os.environ.get("VK_TOKEN"), since)
    items = filter_items(raw, Classifier(cfg.get("filters", {})), since)
    log.info("Собрано %d, по теме %d", len(raw), len(items))

    if not args.no_dedup:
        storage = Storage(args.db)
        items = storage.filter_new(items)
        storage.close()
        log.info("Новых: %d", len(items))

    groups = group_by_region(items, cfg.get("per_region", 10))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stamp = f"{now:%Y-%m-%d_%H%M}"
    md_path = out / f"digest_{stamp}.md"
    vk_path = out / f"vk_post_{stamp}.txt"
    md_path.write_text(render_markdown(groups, now), encoding="utf-8")
    vk_text = render_vk_post(groups, now, cfg.get("hashtags", ""))
    vk_path.write_text(vk_text, encoding="utf-8")
    log.info("Готово: %s, %s", md_path, vk_path)

    if args.send_telegram:
        token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
        if not (token and chat):
            log.error("Для --send-telegram нужны TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID")
        elif not items:
            log.info("Новых новостей нет — в Telegram ничего не отправляю")
        else:
            send_telegram(vk_text, token, chat)
            log.info("Отправлено в Telegram")


if __name__ == "__main__":
    main()
