from datetime import datetime, timezone
from pathlib import Path

import yaml

from airsoft_news.classify import Classifier, filter_items
from airsoft_news.digest import group_by_region, render_markdown, render_vk_post
from airsoft_news.models import NewsItem
from airsoft_news.sources import parse_rss, parse_telegram, vk_posts_to_items
from airsoft_news.storage import Storage

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).parent / "fixtures"
SINCE = datetime(2026, 9, 20, tzinfo=timezone.utc)


def classifier():
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    return Classifier(cfg["filters"])


def test_rss_filter_and_regions():
    items = parse_rss((FIXTURES / "feed.xml").read_bytes(), "test")
    assert len(items) == 6
    result = {i.title: i for i in filter_items(items, classifier(), SINCE)}
    # Барахолка, нерелевантное и старое отброшены.
    assert set(result) == {
        "В Екатеринбурге прошла страйкбольная игра «Уральский рубеж»",
        "Госдума обсуждает закон о страйкболе",
        "Airsoft championship announced in Poland",
    }
    assert result["В Екатеринбурге прошла страйкбольная игра «Уральский рубеж»"].region == "ural"
    assert "games" in result["В Екатеринбурге прошла страйкбольная игра «Уральский рубеж»"].tags
    assert result["Госдума обсуждает закон о страйкболе"].region == "russia"
    assert "law" in result["Госдума обсуждает закон о страйкболе"].tags
    assert result["Airsoft championship announced in Poland"].region == "world"


def test_telegram_parse_and_always_relevant():
    items = parse_telegram((FIXTURES / "telegram.html").read_text(encoding="utf-8"), "tg")
    assert len(items) == 1  # пост без текста пропущен
    item = items[0]
    assert item.url == "https://t.me/testchan/101"
    assert item.title == "Анонс игры в Первоуральске"
    assert "Регистрация" in item.text
    # Слова «страйкбол» нет, но канал помечен как профильный.
    assert filter_items([item], classifier(), SINCE) == []
    item.always_relevant = True
    [kept] = filter_items([item], classifier(), SINCE)
    assert kept.region == "ural"


def test_vk_posts():
    posts = [
        {"id": 5, "owner_id": -123, "date": 1790000000, "text": "Страйкбол в эти выходные\nподробности"},
        {"id": 6, "owner_id": -123, "date": 1790000000, "text": "",
         "copy_history": [{"text": "Репост про airsoft"}]},
        {"id": 7, "owner_id": -123, "date": 1790000000, "text": ""},
    ]
    items = vk_posts_to_items(posts, "vk")
    assert [i.url for i in items] == ["https://vk.com/wall-123_5", "https://vk.com/wall-123_6"]
    assert items[0].title == "Страйкбол в эти выходные"


def test_storage_dedup(tmp_path):
    storage = Storage(tmp_path / "db.sqlite3")
    a = NewsItem("s", "Большая страйкбольная игра под Екатеринбургом", "https://x.ru/1?utm_source=a")
    same_url = NewsItem("s", "Другой заголовок", "https://x.ru/1")
    same_title = NewsItem("s2", "Большая страйкбольная игра под Екатеринбургом!", "https://y.ru/9")
    assert storage.filter_new([a]) == [a]
    assert storage.filter_new([same_url, same_title]) == []


def test_digest_render():
    items = filter_items(parse_rss((FIXTURES / "feed.xml").read_bytes(), "test"), classifier(), SINCE)
    groups = group_by_region(items, 10)
    now = datetime(2026, 9, 30, tzinfo=timezone.utc)
    md = render_markdown(groups, now)
    assert "## 🏔 Свердловская область (1)" in md
    assert "https://example.ru/news/1?utm_source=rss" in md
    post = render_vk_post(groups, now, "#страйкбол")
    assert post.startswith("📰 Новости страйкбола — 30.09.2026")
    assert post.index("СВЕРДЛОВСКАЯ") < post.index("РОССИЯ") < post.index("МИР")
    assert post.rstrip().endswith("#страйкбол")
