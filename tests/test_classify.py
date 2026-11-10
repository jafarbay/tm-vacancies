import pytest

from app.classify import OTHER, classify, detect_lang, extract_salary


@pytest.mark.parametrize("title, expected", [
    ("В компанию требуется главный бухгалтер", "Финансы и бухгалтерия"),
    ("Degreplast ищет Python-разработчика", "IT"),
    ("SLB searches for Drilling Fluids Engineer", "Строительство и инженерия"),
    ("В компанию «Сада Улгам» требуется декларант-фрилансер", "Логистика и ВЭД"),
    ("Азиатский банк развития объявляет вакансию эксперта", "Международные организации"),
    ("Kompaniýa sürüji wezipesine işgär gözleýär", "Транспорт и водители"),
    ("Ничего конкретного", OTHER),
])
def test_classify_by_title(title, expected):
    assert classify(title) == expected


def test_classify_falls_back_to_body():
    assert classify("Компания объявляет набор", "Требуется опытный повар в ресторан") == "Общепит и гостиницы"


@pytest.mark.parametrize("title, lang", [
    ("Требуется бухгалтер", "ru"), ("Seeks QA/QC Engineer", "en"), ("Kompaniýa satyjy gözleýär", "tm"),
])
def test_detect_lang(title, lang):
    assert detect_lang(title) == lang


@pytest.mark.parametrize("text, salary", [
    ("Официальное трудоустройство, стабильная выплата зарплаты. ЗП: 5000 манат.", "5000 манат"),
    ("Зарплата: от 3000 до 5000 манат", "от 3000 до 5000 манат"),
    ("Заработная плата: по договорённости", "по договорённости"),
    ("Salary: competitive", "competitive"),
    ("Своевременная выплата зарплаты", ""),
])
def test_extract_salary(text, salary):
    assert extract_salary(text) == salary
