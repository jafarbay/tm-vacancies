"""Scraper for business.com.tm vacancies -> SQLite.

The source site accepts only RU/TM IPs: run on the RU server or set SCRAPER_PROXY.

    python -m app.scraper                 # incremental: new listings + their full texts
    python -m app.scraper --full          # walk all listing pages
    python -m app.scraper --details 50    # cap number of detail pages per run
    python -m app.scraper --import-json vacancies.json
    python -m app.scraper --reclassify    # after editing classify.py keywords
"""
import argparse
import json
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from . import db
from .config import SCRAPE_DELAY, SCRAPE_WORKERS, SCRAPER_PROXY

LIST_URL = "https://business.com.tm/ru/work/a/index?path=rabota%2Fvakansii&page={page}"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/130.0 Safari/537.36",
    "Accept-Language": "ru,en;q=0.8",
}
CONTENT_SELECTORS = (".border-left-big1", ".entry-content", ".work-content", ".post-content")
IMG_SKIP = re.compile(r"logo|icon|banner|avatar|placeholder|/themes?/|\.gif$", re.I)
log = logging.getLogger("scraper")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def fetch(s: requests.Session, url: str, retries: int = 4) -> str | None:
    """Return page HTML, None on 404. Raises after all retries fail."""
    for attempt in range(retries):
        try:
            r = s.get(url, timeout=(10, 30))
            if r.status_code == 404:
                return None
            if r.status_code == 429 or r.status_code >= 500:
                raise requests.HTTPError(f"HTTP {r.status_code}")
            r.raise_for_status()
            return r.text
        except requests.RequestException as e:
            if attempt == retries - 1:
                raise
            wait = 3 * 2 ** attempt
            log.warning("%s: %s, retry in %ss", url, e, wait)
            time.sleep(wait)


def _icon_text(node, icon: str) -> str:
    i = node.select_one(f"i.{icon}")
    return _norm(i.parent.get_text(" ")) if i else ""


def parse_list(html: str) -> tuple[list[dict], int]:
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for art in soup.select("#work-grid article"):
        a = art.select_one("h4.entry-title a, .entry-title a")
        m = a and re.search(r"/work/(\d+)", a.get("href", ""))
        if not m:
            continue
        badge = art.select_one(".data .badge")
        try:
            day = datetime.strptime(badge.get_text(strip=True), "%d.%m.%Y").date().isoformat()
        except (AttributeError, ValueError):
            day = ""
        city, company = _icon_text(art, "fa-map-marker"), _icon_text(art, "fa-building")
        body = art.select_one(".media-body") or art
        for t in body.select(".entry-header, .data, sub"):
            t.extract()
        items.append({
            "id": int(m.group(1)),
            "title": _norm(a.get_text()),
            "url": a["href"],
            "date": day,
            "city": city or "Не указан",
            "company": company,
            "summary": _norm(body.get_text(" ")).rstrip(". "),
        })
    last = 1
    last_a = soup.select_one(".pagination li.last a")
    if last_a and (m := re.search(r"page=(\d+)", last_a.get("href", ""))):
        last = int(m.group(1))
    return items, last


def _to_text(node) -> str:
    for a in node.find_all("a", href=True):
        # keep link targets that are not visible in the text (e.g. "откликнуться" -> form URL)
        href = a["href"].strip()
        target = href.removeprefix("mailto:").removeprefix("tel:")
        if href.startswith(("http", "mailto:", "tel:")) and target not in a.get_text():
            a.append(f" ({target})")
    for p in node.find_all(["p", "div", "h2", "h3", "h4", "h5"]):
        # block whose whole text is bold (or a real heading) -> "## heading"
        txt = _norm(p.get_text(" "))
        bold = " ".join(_norm(b.get_text(" ")) for b in p.find_all(["strong", "b"]))
        if txt and len(txt) < 80 and (p.name.startswith("h") or _norm(bold) == txt):
            p.clear()
            p.append("## " + txt.rstrip(":"))
    for br in node.find_all("br"):
        br.replace_with("\n")
    for li in node.find_all("li"):
        li.insert(0, "• ")
    for el in node.find_all(["p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "ul", "ol"]):
        el.append("\n")
    lines = (re.sub(r"[ \t\xa0]+", " ", line).strip() for line in node.get_text().split("\n"))
    return "\n".join(line for line in lines if line and line != "•")


def parse_detail(html: str, vid: int, title: str, summary: str, base_url: str = "") -> dict:
    """Full vacancy page -> {body, contacts, images, posted_at}."""
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript", "form"]):
        t.decompose()

    contacts = []
    for row in soup.select(".place-info"):
        label, value = row.select_one(".place-info_label"), row.select_one(".place-info_labeled")
        if label and value:
            lv = (_norm(label.get_text(" ")).rstrip(":"), _norm(value.get_text(" ")))
            if lv[1] and lv not in contacts:
                contacts.append(lv)

    t = soup.select_one("time.article_header_date[datetime]")
    posted_at = t["datetime"] if t else None

    h1 = soup.select_one("h1.post_header")
    main = (h1 and h1.find_parent("div", class_="col-md-8")) or soup.select_one(".border-left-big1") or soup
    images = []
    for img in main.select("img[src]"):
        src = urljoin(base_url, img["src"])
        if src.startswith("http") and not IMG_SKIP.search(src) and src not in images:
            images.append(src)

    return {"body": _body(soup, vid, title, summary), "contacts": contacts, "images": images, "posted_at": posted_at}


def _body(soup, vid: int, title: str, summary: str) -> str:
    node = None
    for sel in CONTENT_SELECTORS:
        cand = soup.select_one(sel)
        if cand and len(cand.get_text(strip=True)) > 50:
            node = cand
            break
    if node is None and summary:
        # Fallback: smallest block that contains the listing summary and no self-link
        # (self-links appear in "latest vacancies" widgets).
        key, min_len, best = _norm(summary)[:40], len(_norm(summary)) * 0.9, None
        for el in soup.find_all(["div", "article", "section", "td"]):
            txt = _norm(el.get_text(" "))
            if key in txt and len(txt) >= min_len and not el.select_one(f'a[href$="/work/{vid}"]'):
                if best is None or len(txt) < best[0]:
                    best = (len(txt), el)
        node = best and best[1]
    if node is None:
        return ""
    text = _to_text(node)
    if text.startswith(title):
        text = text[len(title):].lstrip()
    return text


_local = threading.local()


def _session() -> requests.Session:
    if not hasattr(_local, "s"):
        s = requests.Session()
        s.headers.update(HEADERS)
        if SCRAPER_PROXY:
            s.proxies = {"http": SCRAPER_PROXY, "https": SCRAPER_PROXY}
        _local.s = s
    return _local.s


def _detail_job(r: dict) -> dict | None:
    html = fetch(_session(), r["url"])
    time.sleep(SCRAPE_DELAY)  # per-worker politeness delay
    return parse_detail(html, r["id"], r["title"], r["summary"] or "", r["url"]) if html else None


def _fetch_details(limit: int) -> None:
    """Fetch pending detail pages with SCRAPE_WORKERS threads; DB writes stay in this thread."""
    with db.session() as conn:
        pending = [dict(r) for r in db.pending_details(conn, limit)]
    log.info("details to fetch: %d (workers: %d)", len(pending), SCRAPE_WORKERS)
    done = fails = 0
    with ThreadPoolExecutor(SCRAPE_WORKERS) as pool:
        futures = {pool.submit(_detail_job, r): r for r in pending}
        for fut in as_completed(futures):
            r = futures[fut]
            try:
                detail = fut.result()
                if detail is not None and not detail["body"]:
                    log.warning("id %s: content block not found, keeping summary", r["id"])
                with db.session() as conn:
                    db.set_detail(conn, r["id"], detail or {})
                fails = 0
            except Exception as e:  # one broken page must not stop the run
                fails += 1
                log.error("id %s: %s", r["id"], e)
                if fails >= 5:
                    log.error("5 failures in a row: site blocks us or is down (VPN on?). Stop, rerun later.")
                    for f in futures:
                        f.cancel()
                    break
            done += 1
            if done % 50 == 0:
                log.info("details: %d/%d", done, len(pending))


def run(full: bool = False, max_pages: int = 0, details: int = 0, skip_details: bool = False) -> None:
    db.init()
    s = requests.Session()
    s.headers.update(HEADERS)
    if SCRAPER_PROXY:
        s.proxies = {"http": SCRAPER_PROXY, "https": SCRAPER_PROXY}

    page, last, new_total = 1, 1, 0
    while page <= last and (not max_pages or page <= max_pages):
        html = fetch(s, LIST_URL.format(page=page))
        items, last = parse_list(html) if html else ([], page)
        if not items:
            log.warning("page %d: no items, stop", page)
            break
        with db.session() as conn:
            new = sum(db.upsert_listing(conn, v) for v in items)
        new_total += new
        log.info("list page %d/%d: %d items, %d new", page, last, len(items), new)
        if not new and not full:
            break
        page += 1
        time.sleep(SCRAPE_DELAY)

    if not skip_details:
        _fetch_details(details)

    with db.session() as conn:
        db.set_meta(conn, "last_scrape", db.now())
    log.info("done, new vacancies: %d", new_total)


def import_json(path: str) -> None:
    db.init()
    items = json.loads(Path(path).read_text(encoding="utf-8"))["items"]
    with db.session() as conn:
        for v in items:
            db.upsert_listing(conn, {k: v.get(k, "") for k in ("id", "title", "url", "date", "city", "company")}
                              | {"summary": v.get("desc", "").rstrip(". ")})
        db.set_meta(conn, "last_scrape", db.now())
    log.info("imported %d", len(items))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="walk all listing pages")
    ap.add_argument("--pages", type=int, default=0, help="max listing pages")
    ap.add_argument("--details", type=int, default=0, help="max detail pages per run (0 = all pending)")
    ap.add_argument("--no-details", action="store_true")
    ap.add_argument("--import-json")
    ap.add_argument("--reclassify", action="store_true")
    ap.add_argument("--detail-file", nargs=2, metavar=("ID", "HTML"), help="load a saved vacancy page (offline test)")
    ap.add_argument("--refetch", action="store_true", help="mark all details as pending (after parser changes)")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    if a.refetch:
        db.init()
        with db.session() as conn:
            conn.execute("UPDATE vacancies SET has_detail=0")
        log.info("all details marked for refetch")
    if a.detail_file:
        db.init()
        vid, html = int(a.detail_file[0]), Path(a.detail_file[1]).read_text(encoding="utf-8")
        with db.session() as conn:
            v = db.get(conn, vid)
            db.set_detail(conn, vid, parse_detail(html, vid, v["title"], v["summary"] or "", v["url"]))
        log.info("loaded detail for %s", vid)
    elif a.import_json:
        import_json(a.import_json)
    elif a.reclassify:
        db.init()
        with db.session() as conn:
            log.info("reclassified %d", db.reclassify(conn))
    else:
        run(a.full, a.pages, a.details, a.no_details)


if __name__ == "__main__":
    main()
