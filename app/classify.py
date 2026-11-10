"""Direction classification, language detection, salary extraction.

Rule-based, no ML: the role is cut out of the title ("В компанию «X» требуется бухгалтер" -> "бухгалтер"),
then matched against keyword stems. Accuracy is tracked on a hand-labeled sample in tests/.
"""
import re

OTHER = "Другое"
INTL = "Международные организации"

# Keywords are word-start prefixes (regex \b + text). Score = total length of matched keywords,
# so a specific phrase ("qa engineer", "менеджер по закупкам") beats a generic word ("engineer", "менеджер").
# On equal score the earlier direction wins.
DIRECTIONS = {
    "IT": ["программист", "разработчик", "developer", "frontend", "front-end", "backend", "back-end", "fullstack",
           "python", "php", "java", "react", "1с", "1c", "bitrix", "битрикс", "системный администратор",
           "системного администратора", "сисадмин", "сетевой", "тестировщ", "qa engineer", "manual testing", "devops",
           "веб-разработ", "it-специалист", "it специалист", "it-менеджер", "it менеджер", "it-отдел", "it support",
           "it specialist", "it manager", "it engineer", "it intern", "it hünärmen", "software", "programmer",
           "data analyst", "аналитик данных", "maglumat", "power bi", "bi-аналитик", "техническ поддерж",
           "технической поддерж", "специалист технической поддержки", "cmms", "гис", "gis", "ui/ux"],
    "Медицина": ["врач", "медсестр", "медбрат", "медицин", "фармацевт", "провизор", "стоматолог", "клиник", "аптек",
                 "фарм", "пациент", "реаниматолог", "reanimatolog", "lukman", "doctor", "nurse", "medic", "pharmac",
                 "dentist"],
    "Юриспруденция": ["юрист", "юрисконсульт", "адвокат", "нотариус", "правов", "lawyer", "legal", "head of legal",
                      "senior associate"],
    "Финансы и бухгалтерия": ["бухгалт", "buhgalter", "экономист", "финанс", "аудитор", "налог", "кассир-операционист",
                              "ревизор", "кредит", "accountant", "accounting", "finance", "financial", "auditor",
                              "economist"],
    "Логистика и ВЭД": ["логист", "logistic", "декларант", "таможен", "gümrük", "customs", "склад", "warehouse",
                        "вэд", "вэс", "внешнеэконом", "экспедитор", "закуп", "менеджер по закупкам", "procurement",
                        "снабжен", "supply", "buyer", "тендер", "tender", "контракт", "şertnama", "экспорт", "export",
                        "визов", "поставщик", "перевоз"],
    "Маркетинг и SMM": ["маркетолог", "маркетинг", "marketing", "smm", "таргет", "реклам", "контент", "content",
                        "копирайт", "copywriter", "pr-менеджер", "бренд", "brand"],
    "Дизайн и медиа": ["дизайнер", "дизайн", "dizaýner", "designer", "3d", "визуализатор", "видеомонтаж", "монтажер",
                       "монтажёр", "фотограф", "photographer", "видеограф", "оператор съем", "иллюстратор",
                       "художник", "аниматор", "ai-видео", "редактор", "editor", "журналист", "video editor",
                       "videographer", "video", "podcast", "подкаст"],
    "Образование и языки": ["учител", "преподават", "репетитор", "педагог", "воспитател", "методист", "переводчик",
                            "terjimeçi", "teacher", "translator", "interpreter", "tutor", "instructor",
                            "language teacher"],
    "Красота и спорт": ["парикмахер", "маникюр", "косметолог", "визажист", "салон красоты", "барбер", "массажист",
                        "фитнес", "тренер", "stylist", "fitness"],
    "Общепит и гостиницы": ["повар", "официант", "бариста", "бармен", "кондитер", "пекарь", "ресторан", "кафе",
                            "чайхан", "горничн", "отел", "гостиниц", "cook", "chef", "waiter", "hotel", "barista"],
    "Транспорт и водители": ["водител", "sürüji", "шофер", "шофёр", "driver", "курьер", "courier", "доставщик",
                             "гида", "экскурсовод", "авиа", "awia", "aviation", "pilot"],
    "Сельское хозяйство": ["агроном", "agronom", "ekerançylyk", "oba hojalyk", "ферм", "теплиц", "ветеринар",
                           "земледел", "орошаем", "мелиорац", "irrigation", "agricultur", "сельск", "agro"],
    "Строительство и инженерия": ["инженер", "inžener", "engineer", "строит", "construction", "прораб",
                                  "начальник участка", "архитект", "сметчик", "estimator", "пто", "электрик",
                                  "электромонт", "электромех", "электрообмот", "электросвар", "электрооборуд",
                                  "электроэнерг", "electrician", "сантехник", "сварщик", "welder", "welding",
                                  "механик", "mechanic", "технолог", "энергетик", "геодезист", "surveyor",
                                  "геолог", "geolog", "гидролог", "буров", "drilling", "fabricator", "fitter",
                                  "installer", "technician", "лифт", "пожар", "отоплен", "вентиляц", "ndt", "нк",
                                  "инспектор", "inspector", "inspect", "qa/qc", "quality", "качеств",
                                  "стандартизац", "ремонт", "maintenance", "supervisor", "лаборатор", "laboratoriýa",
                                  "техник", "технике безопасности", "охране труда", "hse", "safety", "gaz hojalyk",
                                  "месторожден"],
    "Производство и рабочие": ["рабоч", "разнорабоч", "оператор станк", "грузчик", "швея", "швеи", "упаковщ",
                               "производств", "önümçilik", "уборщ", "охранник", "сторож", "столяр", "слесар",
                               "токар", "печатник", "helper", "worker", "cleaner", "security guard", "security"],
    "Офис и персонал": ["администратор", "administrat", "admin", "секретар", "secretary", "офис-менеджер",
                        "офис менеджер", "office manager", "офис-координатор", "ассистент", "assistant",
                        "ассистент директора", "помощник", "kömekçi", "документовед", "документ-контрол",
                        "document control", "делопроизвод", "архив", "arhiw", "clerk", "hr", "кадр", "отдела кадров",
                        "персонал", "рекрутер", "recruit", "intern", "стажер", "стажёр", "стажиров", "receptionist",
                        "ресепшн", "оператор", "компьютерный оператор", "координатор", "coordinator", "data entry",
                        "домработниц"],
    "Управление и проекты": ["руководител", "директор", "director", "начальник", "заместител", "управляющ",
                             "head of", "senior manager", "проектн", "менеджер проект", "project manager",
                             "project", "programme", "program", "officer", "müdir"],
    "Продажи и клиенты": ["продав", "продаж", "sales", "seller", "satyjy", "торгов", "торговый агент",
                          "торгового агента", "агента по", "агент по", "sales agent", "мерчендайз", "merchandis",
                          "супервайзер", "кассир", "cashier", "по работе с клиент", "по работе с бизнес-клиент",
                          "по работе с дизайнер", "b2b", "account manager", "customer", "обзвон", "колл-центр",
                          "call-центр", "оператор call", "продавец-консульт", "консультант по продаж", "менеджер",
                          "партнёр по работе", "партнер по работе", "клиентской поддерж", "customer support"],
    INTL: [],  # decided by employer markers (_INTL_RE), not by role words
}
GENERIC = {"Офис и персонал", "Управление и проекты"}
# Words that say little about the field: they only break ties ("SMM-менеджер" -> SMM, "Начальник ПТО" -> ПТО).
WEAK = {"менеджер", "оператор", "помощник", "ассистент", "assistant", "координатор", "coordinator", "руководител",
        "начальник", "директор", "director", "заместител", "управляющ", "project", "programme", "program", "officer",
        "проектн", "admin", "intern", "стажер", "стажёр", "техник", "кадр", "персонал"}
WEAK_SCORE = 2

_INTL_RE = re.compile(
    r"\b(?:абр|азиатск\w* банк|adb|asian development|unicef|юнисеф|osce|обсе|оон|проон|undp|unfpa|unhcr|unodc|"
    r"iom|usaid|winrock|giz|carec|world bank|всемирн\w* банк|ебрр|ebrd|посольств|embassy|un resident|un rco|"
    r"united nations|expertise france|"
    r"national (?:expert|consultant)|национальн\w* (?:эксперт|специалист|консультант)|эксперт|expert|consultant)",
    re.I)

_PATTERNS = {name: re.compile(r"\b(?:" + "|".join(map(re.escape, sorted(words, key=len, reverse=True))) + ")", re.I)
             for name, words in DIRECTIONS.items() if words}

# --- cutting the role out of a title ---
_DASHES = re.compile(r"[‐-―−]")
_QUOTED = re.compile(r"«[^»]*»|“[^”]*”|„[^“”]*[“”]|\"[^\"]*\"|”[^”]*”")
_VERB = re.compile(
    r"\b(?:требу\w+|ищ(?:ет|ем|ут)|приглаша\w+|набира\w+|нуж(?:ен|на|ны)|"
    r"объявля\w+ (?:набор|вакансию)|объявил\w* (?:набор|вакансию)|открыва\w+ (?:набор|вакансию)|"
    r"открыт\w* ваканси\w+|принима\w+ заявки на вакансию|"
    r"seeks|is seeking|searches for|is searching for|is looking for|looking for|is hiring|hiring|"
    r"announces (?:\w+ )?vacancy for|opens (?:a )?vacancy for|opens applications for|"
    r"is opening a position for|invites applications for|opens)\b\s*(?:a |an |the )?",
    re.I)
_LEAD = re.compile(r"^(?:вакансия|vacancy|wakansiýa|job vacancy)\s*[:\-–—]\s*", re.I)
_LEAD_ROLE = re.compile(r"^(?:на (?:позицию|должность|работу|вакансию)|в (?:свою )?команду|сотрудников на позицию)"
                        r"\s*[:\-–—]?\s*", re.I)
_TRAIL_PLACE = re.compile(r"\s+(?:в|во|для)\s+(?:компани|магазин|ресторан|кафе|офис|центр|салон|типографи|шоу-рум|"
                          r"команд|отдел|филиал|[«\"“]|[A-Z])[^()]*$")
_PAREN_PLACE = re.compile(r"\((?:в|во|для|in|for)\s[^)]*\)", re.I)


def extract_role(title: str) -> str:
    """'В компанию «X» требуется бухгалтер' -> 'бухгалтер'; 'ADB seeks Project Analyst' -> 'Project Analyst'."""
    t = _DASHES.sub("-", (title or "").replace("\xa0", " "))
    t = _LEAD.sub("", _PAREN_PLACE.sub(" ", t).strip())
    m = _VERB.search(_QUOTED.sub(lambda q: "§" * len(q.group()), t))  # verbs inside company names don't count
    if m:
        tail = t[m.end():]
        no_quotes = _QUOTED.sub(" ", tail)
        # role is usually unquoted; but "принимает заявки на вакансию «Дизайнер»" has it in quotes
        t = no_quotes if no_quotes.strip(" :.-") else re.sub(r"[«»“”„\"]", " ", tail)
    else:
        t = _QUOTED.sub(" ", t)
    t = _LEAD_ROLE.sub("", t.strip())
    t = _TRAIL_PLACE.sub("", t)
    t = re.sub(r"\s+(?:в|во|для|in|for|at)\s*$", "", t.strip())  # preposition left after removing «Company»
    return re.sub(r"\s+", " ", t).strip(" :.-")


def _best(text: str) -> str | None:
    if not text:
        return None
    text = _DASHES.sub("-", text)
    scores = {name: sum(WEAK_SCORE if m.lower() in WEAK else len(m) for m in pat.findall(text))
              for name, pat in _PATTERNS.items()}
    best = max(scores, key=lambda k: scores[k])  # first one wins on ties = dict order
    return best if scores[best] else None


def classify(title: str, text: str = "") -> str:
    """The role from the title decides. For generic roles (assistant, expert, officer) at UN/embassies/banks
    -> 'Международные организации'. Then the whole title without company names, then the body start."""
    title = title or ""
    role_dir = _best(extract_role(title))
    if role_dir and role_dir not in GENERIC:
        return role_dir
    if _INTL_RE.search(title):
        return INTL
    if role_dir:
        return role_dir
    return _best(_QUOTED.sub(" ", title)) or _best((text or "")[:1500]) or OTHER


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
