import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Site on a temporary DB with two vacancies."""
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    import app.config
    import app.db
    import app.main
    importlib.reload(app.config)
    importlib.reload(app.db)
    db = app.db
    db.init()
    with db.session() as conn:
        db.upsert_listing(conn, {"id": 1, "title": "IT специалист", "url": "https://x/1", "date": "2026-11-10",
                                 "city": "Ашгабат", "company": "Test", "summary": "Требования: опыт"})
        db.upsert_listing(conn, {"id": 2, "title": "Elite Elektronika ищет продавца", "url": "https://x/2",
                                 "date": "2025-11-10", "city": "Балкан", "company": "", "summary": "With it"})
        db.set_detail(conn, 1, {"body": "## Требования\n• Опыт 2 года\nТел: +993 61 00-00-00, ЗП: 3000-4000 манат",
                                "contacts": [["Телефон", "+99361000000"]], "images": [], "posted_at": None})
    importlib.reload(app.main)
    return TestClient(app.main.app)


def test_pages(client):
    for url in ("/", "/?city=Балкан", "/?period=7&lang=ru", "/vacancy/1", "/vacancy/2", "/sitemap.xml",
                "/robots.txt", "/healthz", "/api/vacancies"):
        assert client.get(url).status_code == 200, url
    assert client.get("/vacancy/999").status_code == 404


def test_short_word_search_is_whole_word(client):
    items = client.get("/api/vacancies", params={"q": "it"}).json()["items"]
    assert [v["id"] for v in items] == [1]  # not "Elite" / "With it" in body


def test_vacancy_page_formatting(client):
    html = client.get("/vacancy/1").text
    assert "<h2>Требования</h2>" in html
    assert 'href="tel:+99361000000"' in html
    assert 'tel:30004000' not in html  # salary range is not a phone
    assert "может быть уже закрыта" in client.get("/vacancy/2").text  # stale warning
