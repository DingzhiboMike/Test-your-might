#!/usr/bin/env python3
"""Проверяет, что разбор материалов прочитал весь контекст, а не два-три удобных файла.

  python3 scripts/check_knowledge.py tasks/<папка>

Сверяет `00k-knowledge.md` с реестром `sources.csv` и с ТЗ:
1. Каждый источник контекста из реестра (kind=context) есть в таблице «ПОКРЫТИЕ ФАЙЛОВ» — строкой со своим id,
   с заполненными полями «прочитан» и «к каким пунктам GAP относится». Для «не относится» нужна причина.
2. По каждому пункту GAP из `00-tz.md` есть раздел «GAP k», и в нём непустая строка «Чего нет».
3. Файл, отмеченный «прочитан частично», — предупреждение, а не ошибка: так и должно быть написано, если не дочитан.

Цитаты в карте проверяет `check_quotes.py`, как в любом артефакте. Ошибка — код возврата 1.
Отчёт: tasks/<папка>/checks/knowledge.md. Нет `00k-knowledge.md` — проверять нечего.
"""
import csv
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_path import gap_numbers  # noqa: E402


def read(path):
    return open(path, encoding="utf-8").read() if os.path.exists(path) else ""


def context_ids(task):
    path = os.path.join(task, "sources.csv")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [r["id"] for r in csv.DictReader(f) if r.get("kind") == "context"]


def section(text, title_re):
    m = re.search(title_re, text, re.M)
    if not m:
        return ""
    rest = text[m.end():]
    stop = re.search(r"^\**\d+\.\s+[А-ЯЁA-Z]{3,}", rest, re.M)
    return rest[:stop.start()] if stop else rest


def main():
    if len(sys.argv) < 2:
        sys.stderr.write(__doc__)
        return 2
    task = sys.argv[1].rstrip("/")
    kn = read(os.path.join(task, "00k-knowledge.md"))
    if not kn:
        print("Разбора материалов нет: проверять нечего.")
        return 0
    errors, warns = [], []

    cover = section(kn, r"ПОКРЫТИЕ ФАЙЛОВ")
    if not cover:
        errors.append("нет раздела «ПОКРЫТИЕ ФАЙЛОВ»")
    rows = {}
    for line in cover.splitlines():
        if not line.strip().startswith("|"):
            continue
        m = re.search(r"\bF-\d+\b", line)
        if m:
            rows[m.group(0)] = [c.strip() for c in line.strip().strip("|").split("|")]
    for fid in context_ids(task):
        if fid not in rows:
            errors.append("%s: файла контекста нет в таблице покрытия" % fid)
            continue
        cells = rows[fid]
        if len(cells) < 5 or any(not c for c in cells[:5]):
            errors.append("%s: в строке покрытия пустые поля" % fid)
            continue
        read_cell, gaps_cell = cells[2].lower(), cells[3]
        if "частич" in read_cell:
            warns.append("%s: прочитан частично — %s" % (fid, cells[2]))
        elif "целиком" not in read_cell:
            errors.append("%s: в поле «прочитан» нет ни «целиком», ни «частично»" % fid)
        if not re.search(r"\d", gaps_cell):
            if "не относится" not in gaps_cell.lower() or len(gaps_cell) < 18:
                errors.append("%s: не указано, к каким пунктам GAP относится, или «не относится» без причины" % fid)

    for n in sorted(gap_numbers(read(os.path.join(task, "00-tz.md")))):
        m = re.search(r"^\s*\**GAP\s+%d\b" % n, kn, re.M)
        if not m:
            errors.append("GAP %d: нет раздела в карте знания" % n)
            continue
        rest = kn[m.end():]
        nxt = re.search(r"^\s*\**GAP\s+\d+\b|^\**\d+\.\s+[А-ЯЁA-Z]{3,}", rest, re.M)
        block = rest[:nxt.start()] if nxt else rest
        cm = re.search(r"Чего нет:\s*\n?((?:\s*[-—].*\n?)+|.*)", block)
        if not cm or not cm.group(1).strip().strip("-— ").strip():
            errors.append("GAP %d: пустая строка «Чего нет»" % n)

    os.makedirs(os.path.join(task, "checks"), exist_ok=True)
    out = ["# Разбор материалов: " + os.path.basename(task), "",
           "Файлов контекста в реестре: %d, строк покрытия: %d" % (len(context_ids(task)), len(rows)), "",
           "## Ошибки"] + (["- " + e for e in errors] or ["- нет"]) + ["", "## Предупреждения"] + (["- " + w for w in warns] or ["- нет"])
    open(os.path.join(task, "checks", "knowledge.md"), "w", encoding="utf-8").write("\n".join(out) + "\n")
    for e in errors:
        print("материалы: " + e)
    for w in warns:
        print("материалы (внимание): " + w)
    if not errors:
        print("Разбор материалов: файлов %d, ошибок нет." % len(rows))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
