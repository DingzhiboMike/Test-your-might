#!/usr/bin/env python3
"""Разбор отчёта проверки смысла (review-*.md) и ответов автора на него.

Общий модуль для check_artifact.py и trust_map.py: один и тот же разбор в обоих, чтобы счёт не расходился.

Отчёт проверяющего: строки «С-01 [блок] Вид — …» и «С-02 [замечание] Вид — …».
Ответ автора в блоке «ПО ПРОВЕРКЕ СМЫСЛА» в конце артефакта: «С-01 — исправлено: что поменял»,
«С-02 — снято», «С-03 — оспорено: причина с фрагментом».

Принимается как есть, без правки артефакта вручную: маркер списка («- », «* », «1. »), жирный шрифт,
метка [блок] или [замечание] после номера, тире любого вида или двоеточие.
"""
import re

ID = r"[А-ЯA-Z]-\d{2,}"
LEAD = r"^[ \t]*(?:[-*•][ \t]+|\d+[.)][ \t]+)?\**"
SEP = r"[ \t]*(?:\[[^\]]*\][ \t]*)?[—–:\-]+[ \t]*\**"

BLOCKING = re.compile(LEAD + "(" + ID + r")\**[ \t]*\[блок\]", re.M)
REMARK = re.compile(LEAD + "(" + ID + r")\**[ \t]*\[замечание\]", re.M)
ANSWER = re.compile(LEAD + "(" + ID + r")\**" + SEP + r"(исправлено|снято|оспорено)\**[ \t]*(?::[ \t]*(.*))?$", re.M | re.I)
NOT_CHECKED = re.compile(r"Не проверено:[ \t]*(.*)", re.S)


def blocking_ids(review_text):
    return BLOCKING.findall(review_text)


def remark_ids(review_text):
    return REMARK.findall(review_text)


def answer_block(artifact_text):
    """Текст после «ПО ПРОВЕРКЕ СМЫСЛА» или None, если блока нет."""
    parts = artifact_text.split("ПО ПРОВЕРКЕ СМЫСЛА", 1)
    return parts[1] if len(parts) == 2 else None


def answers(block_text):
    """{id: (статус, причина)}; статус — исправлено / снято / оспорено."""
    out = {}
    for m in ANSWER.finditer(block_text):
        out[m.group(1)] = (m.group(2).lower(), (m.group(3) or "").strip())
    return out


def not_checked(review_text, limit=700):
    """Что проверяющий сам назвал несверенным; пусто, если нечего."""
    m = NOT_CHECKED.search(review_text)
    if not m:
        return ""
    s = re.sub(r"\s+", " ", m.group(1)).strip()
    if s.lower().strip(" .—-") in ("", "нет", "ничего", "всё проверено", "все проверено"):
        return ""
    return s if len(s) <= limit else s[:limit].rstrip() + "…"
