import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("DB_PATH", BASE_DIR.parent / "data" / "vacancies.db"))
SITE_NAME = os.getenv("SITE_NAME", "Вакансии ТМ")
SITE_URL = os.getenv("SITE_URL", "").rstrip("/")  # e.g. https://jobs.example.com, used in sitemap/OG
SCRAPER_PROXY = os.getenv("SCRAPER_PROXY") or None  # http://user:pass@host:port, optional
SCRAPE_DELAY = float(os.getenv("SCRAPE_DELAY", "1.5"))
SCRAPE_WORKERS = int(os.getenv("SCRAPE_WORKERS", "4"))  # parallel detail downloads
