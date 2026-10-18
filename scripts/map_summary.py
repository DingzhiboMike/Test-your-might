#!/usr/bin/env python3
"""Сводка карты документов для диспетчера — без модели: что в контексте есть, до согласования ТЗ.

  python3 scripts/map_summary.py tasks/<папка>

Берёт то, что уже посчитал `map_docs.py` (map/index.csv, map/<id>.json), и паспорта из `sources.csv`. Печатает и
пишет в map/summary.md:
- таблицу документов: id, файл, тип по реестру, дата, статус чтения, строк, строк с числами, срезами, продуктом,
  риском; документы без строк и прочитанные не целиком — отдельным списком «Не читается или частично»;
- какие срезы встречаются и в скольких документах (слова, на которых сработал тег «срез») — кандидаты для ГРУППЫ;
- строки с тегом «продукт» — до трёх на документ, с номером строки: кандидаты для РАМКИ ПРОДУКТА, которые
  подтверждает человек на согласовании, а досье и модель предмета сверяют после.

Ничего не оценивает: важность документов считает rank_impact.py, досье пишет document-mapper после согласования.
Нет map/ — сначала map_docs.py (код 1).
"""
import csv
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from map_docs import GRP, PRD  # noqa: E402

PER_DOC = 3


def read_csv(path):
    try:
        with open(path, encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))
    except OSError:
        return []


def summary(task):
    index = read_csv(os.path.join(task, "map", "index.csv"))
    if not index:
        return None
    meta = {r.get("id"): r for r in read_csv(os.path.join(task, "sources.csv"))}
    rows, weak, slices, product = [], [], Counter(), []
    for i in index:
        rid = i["id"]
        try:
            data = json.load(open(os.path.join(task, "map", rid + ".json"), encoding="utf-8"))
        except (OSError, ValueError):
            data = {"lines": []}
        lines = data.get("lines", [])
        count = Counter(t for l in lines for t in l.get("tags", []))
        seen = set()
        for l in lines:
            if "срез" in l.get("tags", []):
                seen.update(m.group(0).lower() for m in GRP.finditer(l["text"]))
        slices.update(seen)
        prod = [l for l in lines if "продукт" in l.get("tags", [])][:PER_DOC]
        for l in prod:
            terms = ", ".join(sorted({m.group(0).lower() for m in PRD.finditer(l["text"])}))
            product.append("- %s L%d (%s): %s" % (rid, l["n"], terms, l["text"][:200]))
        m = meta.get(rid, {})
        date = m.get("data_date") or m.get("pub_date") or "—"
        read = i.get("read") or m.get("read") or "—"
        rows.append("| %s | %s | %s | %s | %s | %d | %d | %d | %d | %d |" % (
            rid, os.path.basename(i.get("location", "")) or "—", m.get("ctx_type") or m.get("kind") or "—", date,
            read, len(lines), count["число"], count["срез"], count["продукт"], count["риск"]))
        if not lines or read not in ("full", "полностью", "—"):
            weak.append("- %s — %s" % (rid, "строк нет" if not lines else "прочитан: " + read))
    out = ["# Сводка карты: " + os.path.basename(task), "",
           "| id | Файл | Тип | Дата | Чтение | Строк | Числа | Срезы | Продукт | Риск |",
           "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"] + rows
    out += ["", "## Не читается или частично"] + (weak or ["- нет"])
    out += ["", "## Срезы — в скольких документах (кандидаты для ГРУППЫ)"]
    out += ["- %s — %d" % (k, n) for k, n in slices.most_common()] or ["- не найдено"]
    out += ["", "## Строки про продукт (кандидаты для РАМКИ ПРОДУКТА, подтверждает человек)"]
    out += product or ["- не найдено"]
    return "\n".join(out) + "\n"


def main():
    if len(sys.argv) < 2:
        sys.stderr.write(__doc__)
        return 2
    task = sys.argv[1].rstrip("/")
    text = summary(task)
    if text is None:
        print("Карты нет: сначала python3 scripts/map_docs.py %s" % task)
        return 1
    with open(os.path.join(task, "map", "summary.md"), "w", encoding="utf-8") as f:
        f.write(text)
    print(text, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
