#!/usr/bin/env python3
"""Модель предмета: матрица «группа × признак» из клеток; надёжность считает скрипт, а не модель.

  python3 scripts/build_model.py tasks/<папка> [--today ГГГГ-ММ-ДД]

Читает:
- `00m-schema.txt` — строки и признаки матрицы (задаёт диспетчер из ТЗ): `row: Бросившие ИП`, `feature: Причины`;
- `00m-cells.csv` — клетки, их пишет модель (скилл `subject-model`), по одной записи на источник:
  row, feature, value, quote, source, lines, group_match, group_note, n, type, date
  - quote — дословная цитата из строк карты `map/<id>.json` (`lines`: `L45` или `L45-L47`);
  - group_match: точная | соседняя | другая — совпадает ли группа источника с группой строки;
  - n: целое число или «не указано»; type: поведение | результат теста | слова | описание | утверждение команды;
  - date: год (2026), месяц (2026-04) или «не указана».

Надёжность клетки считается по правилам, записанным заранее:
- «значение» — группа точная И n — целое И тип «поведение» или «результат теста»;
- «версия» — группа точная или соседняя, тип слова, описание, поведение или результат теста, не один респондент;
- «идея» — всё остальное: другая группа, утверждение команды, один респондент;
- «нет данных» — для клетки нет ни одной записи.
У клетки несколько записей — берётся лучшая; «независимых документов» — число разных источников (перепечатки
с общим корнем из реестра считаются одним). Источник старше года от даты расчёта помечается.

Пишет `00m-model.md` (матрица, пустые и слабые клетки, старые данные) и `00m-model.json` (для check_chain,
check_rank). Ошибка — код возврата 1: нет схемы, клетка вне схемы, цитата не из указанных строк, неверные значения.
"""
import csv
import datetime
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_map import lines_of, squeeze  # noqa: E402

TYPES = ["поведение", "результат теста", "слова", "описание", "утверждение команды"]
MATCH = ["точная", "соседняя", "другая"]
RANK = {"значение": 3, "версия": 2, "идея": 1, "нет данных": 0}
LINES = re.compile(r"^L(\d+)(?:\s*[-–]\s*L?(\d+))?$")


def read_schema(task):
    p = os.path.join(task, "00m-schema.txt")
    rows, feats = [], []
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            m = re.match(r"^\s*(row|feature)\s*:\s*(.+?)\s*$", line)
            if m:
                (rows if m.group(1) == "row" else feats).append(m.group(2))
    return rows, feats


def roots(task):
    p = os.path.join(task, "sources.csv")
    out = {}
    if os.path.exists(p):
        for r in csv.DictReader(open(p, encoding="utf-8")):
            out[r["id"]] = r.get("root") or r["id"]
    return out


def entry_level(e):
    n = e["n"]
    n_int = n.isdigit() and int(n) >= 1
    if e["group_match"] == "точная" and n_int and e["type"] in ("поведение", "результат теста"):
        return "значение"
    if (e["group_match"] in ("точная", "соседняя") and e["type"] in ("слова", "описание", "поведение", "результат теста")
            and not (n == "1" and e["type"] == "слова")):
        return "версия"
    return "идея"


def old(date, today):
    m = re.match(r"^(\d{4})(?:-(\d{2}))?", date.strip())
    if not m:
        return False
    y, mo = int(m.group(1)), int(m.group(2) or 6)
    return (today.year - y) * 12 + (today.month - mo) > 12


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.stderr.write(__doc__)
        return 2
    task = args[0].rstrip("/")
    today = datetime.date.today()
    if "--today" in sys.argv:
        today = datetime.date.fromisoformat(sys.argv[sys.argv.index("--today") + 1])
    rows, feats = read_schema(task)
    errors = []
    if not rows or not feats:
        print("Нет 00m-schema.txt со строками (row:) и признаками (feature:): модель собирать не из чего.")
        return 1
    cells_path = os.path.join(task, "00m-cells.csv")
    entries = []
    if os.path.exists(cells_path):
        with open(cells_path, encoding="utf-8", newline="") as f:
            entries = list(csv.DictReader(f))
    root = roots(task)
    ids = set(root)
    cache = {}
    cells = {}
    for i, e in enumerate(entries, 2):
        e = {k: (v or "").strip() for k, v in e.items() if k}
        tag = "строка %d" % i
        for k in ("row", "feature", "value", "quote", "source", "lines", "group_match", "n", "type", "date"):
            if not e.get(k):
                errors.append("%s: пусто поле «%s»" % (tag, k))
        if errors and errors[-1].startswith(tag):
            continue
        if e["row"] not in rows:
            errors.append("%s: строка «%s» вне схемы" % (tag, e["row"]))
        if e["feature"] not in feats:
            errors.append("%s: признак «%s» вне схемы" % (tag, e["feature"]))
        if e["source"] not in ids:
            errors.append("%s: источника %s нет в реестре" % (tag, e["source"]))
        if e["type"] not in TYPES:
            errors.append("%s: type «%s» — допустимо: %s" % (tag, e["type"], ", ".join(TYPES)))
        if e["group_match"] not in MATCH:
            errors.append("%s: group_match «%s» — допустимо: %s" % (tag, e["group_match"], ", ".join(MATCH)))
        if not (e["n"].isdigit() or e["n"].lower() == "не указано"):
            errors.append("%s: n должно быть целым числом или «не указано»" % tag)
        m = LINES.match(e["lines"])
        if not m:
            errors.append("%s: lines «%s» — ожидается L45 или L45-L47" % (tag, e["lines"]))
        elif e["source"] in ids:
            lines = cache.setdefault(e["source"], lines_of(task, e["source"]))
            a, b = int(m.group(1)), int(m.group(2) or m.group(1))
            if lines is None:
                errors.append("%s: нет карты map/%s.json — запусти scripts/map_docs.py" % (tag, e["source"]))
            elif a not in lines or b not in lines:
                errors.append("%s: в карте %s нет строк L%d–L%d" % (tag, e["source"], a, b))
            else:
                span = squeeze(" ".join(lines[n]["text"] for n in range(a, b + 1)))
                if squeeze(e["quote"].rstrip("…").rstrip(".")) not in span:
                    errors.append("%s: цитата не найдена в %s L%d–L%d: «%s…»" % (tag, e["source"], a, b, e["quote"][:40]))
        e["n"] = e["n"].lower() if e["n"].lower() == "не указано" else e["n"]
        cells.setdefault((e["row"], e["feature"]), []).append(e)
    out_cells = {}
    for r in rows:
        for ft in feats:
            es = cells.get((r, ft), [])
            if not es:
                out_cells[(r, ft)] = {"level": "нет данных", "sources": [], "roots": 0, "old": False, "entries": []}
                continue
            best = max((entry_level(e) for e in es), key=lambda x: RANK[x])
            src = sorted({e["source"] for e in es})
            out_cells[(r, ft)] = {"level": best, "sources": src, "roots": len({root.get(s, s) for s in src}),
                                  "old": all(old(e["date"], today) for e in es),
                                  "entries": [{k: e[k] for k in ("value", "source", "lines", "group_match", "n", "type", "date")}
                                              for e in es]}
    counts = {k: 0 for k in RANK}
    for c in out_cells.values():
        counts[c["level"]] += 1
    mark = {"значение": "● значение", "версия": "◐ версия", "идея": "○ идея", "нет данных": "— нет данных"}
    md = ["# Модель предмета: %s" % os.path.basename(task), "",
          "Клеток: %d (значение %d, версия %d, идея %d, нет данных %d). Надёжность посчитана скриптом по правилам из "
          "`scripts/build_model.py`; модель её не назначает." % (len(out_cells), counts["значение"], counts["версия"],
                                                                 counts["идея"], counts["нет данных"]), "",
          "| Группа | " + " | ".join(feats) + " |", "| --- |" + " --- |" * len(feats)]
    for r in rows:
        md.append("| %s | " % r + " | ".join(
            mark[out_cells[(r, ft)]["level"]] + (" (%s)" % ", ".join(out_cells[(r, ft)]["sources"]) if out_cells[(r, ft)]["sources"] else "")
            + (", старше года" if out_cells[(r, ft)]["old"] else "") for ft in feats) + " |")
    md += ["", "## Пустые клетки", ""]
    md += ["- %s × %s" % k for k, c in out_cells.items() if c["level"] == "нет данных"] or ["- нет"]
    md += ["", "## Слабые клетки (версия или идея)", ""]
    md += ["- %s × %s — %s (%s)" % (k[0], k[1], c["level"], ", ".join(c["sources"])) for k, c in out_cells.items()
           if c["level"] in ("версия", "идея")] or ["- нет"]
    md += ["", "## Клетки со старыми данными (старше года)", ""]
    md += ["- %s × %s" % k for k, c in out_cells.items() if c["old"]] or ["- нет"]
    md += ["", "## Записи", ""]
    for k, c in out_cells.items():
        for e in c["entries"]:
            md.append("- %s × %s: %s — %s %s, группа %s, n %s, %s, %s" % (k[0], k[1], e["value"], e["source"], e["lines"],
                                                                         e["group_match"], e["n"], e["type"], e["date"]))
    md += ["", "## Ошибки", ""] + (["- " + x for x in errors] or ["- нет"])
    open(os.path.join(task, "00m-model.md"), "w", encoding="utf-8").write("\n".join(md) + "\n")
    json.dump({"rows": rows, "features": feats,
               "cells": {"%s × %s" % k: {kk: vv for kk, vv in c.items() if kk != "entries"} for k, c in out_cells.items()}},
              open(os.path.join(task, "00m-model.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("Модель: клеток %d (значение %d, версия %d, идея %d, нет данных %d), ошибок %d."
          % (len(out_cells), counts["значение"], counts["версия"], counts["идея"], counts["нет данных"], len(errors)))
    for e in errors[:15]:
        print("  ОШИБКА " + e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
