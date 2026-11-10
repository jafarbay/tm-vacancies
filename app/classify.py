"""Direction classification, language detection, salary extraction."""
import re

OTHER = "Другое"

# Order matters: on equal score the earlier (more specific) direction wins.
DIRECTIONS = {
    "Международные организации": ["абр", "азиатск", "adb", "asian development", "unicef", "юнисеф", "osce", "обсе",
                                  "оон", "undp", "iom", "usaid", "winrock", "giz", "посольств", "embassy",
                                  "world bank", "всемирный банк", "consultant", "эксперт", "expert"],
    "IT": ["аналитик", "power bi", "analyst", "ии-", "ai-", "техническ поддерж", "технической поддерж", "it intern", "it hünärmen", "cmms", "программист", "разработчик", "developer", "frontend", "backend", "fullstack", "python", "php", "java",
           "1с", "1c", "системный администратор", "сисадмин", "сетевой", "тестировщ", "devops", "веб-разработ",
           "it-специалист", "it специалист", "it-отдел", "it support", "it specialist", "it manager", "it engineer",
           "software", "data analyst", "аналитик данных", "web developer", "programmer"],
    "Медицина": ["фарм", "пациент", "врач", "медсестр", "медбрат", "медицин", "фармацевт", "провизор", "стоматолог", "клиник", "аптек",
                 "doctor", "nurse", "medic", "pharmac", "dentist"],
    "Юриспруденция": ["юрист", "юрисконсульт", "адвокат", "нотариус", "правов", "lawyer", "legal"],
    "Финансы и бухгалтерия": ["ревизор", "кредит", "buhgalter", "бухгалт", "экономист", "финанс", "аудит", "налог", "кассир-операционист",
                              "accountant", "accounting", "finance", "financial", "auditor", "economist"],
    "Логистика и ВЭД": ["внешнеэконом", "gümrük", "визов", "тендер", "контракт", "экспорт", "tender", "export", "şertnama", "логист", "декларант", "таможен", "склад", "вэд", "экспедитор", "закуп", "снабжен",
                        "logistic", "warehouse", "procurement", "customs", "supply", "buyer"],
    "Маркетинг и SMM": ["маркетолог", "маркетинг", "smm", "таргет", "реклам", "контент", "копирайт", "pr-менеджер",
                        "бренд", "marketing", "content", "copywriter", "brand"],
    "Дизайн и медиа": ["dizaýner", "редактор", "журналист", "editor", "дизайнер", "дизайн", "3d", "видеомонтаж", "монтажер", "фотограф", "видеограф", "оператор съем",
                       "иллюстратор", "designer", "photographer", "video editor"],
    "Образование и языки": ["terjimeçi", "учител", "преподават", "репетитор", "педагог", "воспитател", "переводчик", "методист",
                            "teacher", "translator", "interpreter", "tutor", "instructor"],
    "Красота и спорт": ["парикмахер", "маникюр", "косметолог", "визажист", "салон красоты", "барбер", "массажист",
                        "фитнес", "тренер", "stylist", "fitness"],
    "Общепит и гостиницы": ["чайхан", "повар", "официант", "бариста", "бармен", "кондитер", "пекарь", "ресторан", "кафе",
                            "горничн", "отел", "гостиниц", "cook", "chef", "waiter", "hotel", "barista"],
    "Транспорт и водители": ["sürüji", "гида", "экскурсовод", "авиа", "awia", "aviation", "pilot", "водител", "курьер", "доставщик", "шофер", "шофёр", "driver", "courier"],
    "Строительство и инженерия": ["электро", "буров", "пто", "лаборатор", "laboratoriýa", "агроном", "agronom", "supervisor", "электросвар", "пожар", "отоплен", "вентиляц", "ndt", "нк", "инспектор", "inspect", "fabricator", "fitter", "installer", "drilling", "geolog", "геолог", "гидролог", "ремонт", "стандартизац", "качеств", "quality", "inžener", "инженер", "строит", "прораб", "архитект", "сметчик", "электрик", "сантехник",
                                  "сварщик", "механик", "технолог", "энергетик", "геодезист", "engineer",
                                  "construction", "qa/qc", "technician", "electrician", "welder", "mechanic",
                                  "hse", "safety", "surveyor"],
    "Производство и рабочие": ["önümçilik", "helper", "рабоч", "оператор станк", "грузчик", "швея", "швеи", "упаковщ", "производств",
                               "уборщ", "охранник", "разнорабоч", "столяр", "слесар", "токар", "worker", "operator",
                               "cleaner", "security guard"],
    "Управление и проекты": ["руководител", "директор", "начальник", "заместител", "проектн", "менеджер проект",
                             "project", "programme", "program", "director", "head of", "senior manager", "officer",
                             "управляющ", "müdir"],
    "Офис и персонал": ["документовед", "архив", "arhiw", "clerk", "домработниц", "помощник", "kömekçi", "intern", "стажер", "стажёр", "администратор", "секретар", "офис-менеджер", "офис менеджер", "ассистент", "делопроизвод",
                        "hr", "кадр", "персонал", "рекрутер", "оператор call", "колл-центр", "call-центр",
                        "оператор", "receptionist", "assistant", "document controller", "administrat",
                        "secretary", "recruit", "coordinator", "координатор", "office manager"],
    "Продажи и клиенты": ["satyjy", "обзвон", "ведущ", "менеджер", "партнёр по работе", "партнер по работе", "продав", "продаж", "торгов", "менеджер по работе с клиент", "кассир", "консультант",
                          "мерчендайз", "супервайзер", "агент", "sales", "seller", "cashier", "merchandis",
                          "account manager", "customer"],
}

_PATTERNS = {name: re.compile(r"\b(?:" + "|".join(map(re.escape, words)) + ")", re.I)
             for name, words in DIRECTIONS.items()}


def _best(text: str) -> str | None:
    best, best_score = None, 0
    for name, pat in _PATTERNS.items():
        score = len(pat.findall(text))
        if score > best_score:
            best, best_score = name, score
    return best


def classify(title: str, text: str = "") -> str:
    """Title decides first; body text is the fallback."""
    return _best(title or "") or _best(text or "") or OTHER


def detect_lang(title: str) -> str:
    if re.search(r"[а-яё]", title, re.I):
        return "ru"
    if re.search(r"[äňöşüýžç]", title, re.I):
        return "tm"
    return "en"


_SALARY_RE = re.compile(
    r"\b(?:з/п|зп|зарплата|заработная плата|оклад|доход|salary|aýlyk(?: hak)?|zähmet haky)\b\s*[:\-–—]?\s*"
    r"(?P<v>[^\n]{0,25}?(?:\d|договор|собеседован|обсужда|индивидуальн|negotiable|competitive|ylalaşyk)[^\n;]{0,60})",
    re.I)


def extract_salary(text: str) -> str:
    m = _SALARY_RE.search(text or "")
    return m.group("v").strip(" :.,-•\t")[:90] if m else ""
