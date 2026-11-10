"""Accuracy of direction classification on a hand-labeled sample of real titles.

labeled_titles.tsv: id, title, acceptable directions ("A|B" when a title honestly fits two).
Run with -s to see the mistakes.
"""
from pathlib import Path

from app.classify import DIRECTIONS, OTHER, classify, extract_role

ROWS = [line.rstrip("\n").split("\t")
        for line in (Path(__file__).parent / "fixtures" / "labeled_titles.tsv").read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")]


def test_labels_use_known_directions():
    known = {*DIRECTIONS, OTHER}
    for _, title, labels in ROWS:
        assert set(labels.split("|")) <= known, title


def test_accuracy():
    wrong = [(t, classify(t), lab) for _, t, lab in ROWS if classify(t) not in lab.split("|")]
    for t, got, lab in wrong:
        print(f"{got} != {lab}: {t}")
    accuracy = 1 - len(wrong) / len(ROWS)
    assert accuracy >= 0.95, f"accuracy {accuracy:.1%}"


def test_extract_role():
    assert extract_role("В компанию «Hilli Söwda» требуется Специалист Отдела кадров") == "Специалист Отдела кадров"
    assert extract_role("ADB Turkmenistan Seeks Project Analyst") == "Project Analyst"
    assert extract_role("Вакансия: Маркетолог в «Премиальный банный и SPA-комплекс»") == "Маркетолог"
    assert extract_role("ХО «TМТ Consulting Group» принимает заявки на вакансию «Дизайнер»") == "Дизайнер"
    assert extract_role("Вакансия: Офисный администратор (в инженерную компанию)") == "Офисный администратор"
