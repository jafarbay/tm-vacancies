from pathlib import Path

from app.scraper import parse_detail, parse_list

FIX = Path(__file__).parent / "fixtures"


def test_parse_list():
    items, last = parse_list((FIX / "list_page.html").read_text(encoding="utf-8"))
    assert last == 143
    assert [v["id"] for v in items] == [9001, 9000]
    first = items[0]
    assert first["date"] == "2026-11-10"
    assert first["city"] == "Ашгабат"
    assert first["company"] == "Компания «Test Trade»"
    assert first["summary"].startswith("Требования")
    assert items[1]["company"] == ""


def test_parse_detail():
    d = parse_detail((FIX / "detail_page.html").read_text(encoding="utf-8"), 9001,
                     "В компанию «Test Trade» требуется бухгалтер", "Требования: Опыт работы от 2 лет", "https://x/")
    body = d["body"]
    assert "• Опыт работы от 2 лет." in body
    assert "## Чем предстоит заниматься" in body            # bold paragraph -> heading
    assert "(https://example.com/form)" in body             # hidden link target kept
    assert "Читайте также" not in body                      # sidebar/related blocks excluded
    assert [list(c) for c in d["contacts"]] == [
        ["Работодатель", "Компания «Test Trade»"], ["Телефон", "+99361000000"], ["Регион", "Ашгабат"]]
    assert d["posted_at"] == "2026-11-10T10:21:39+05:00"
