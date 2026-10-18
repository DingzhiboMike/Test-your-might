#!/usr/bin/env python3
"""Важность документов для задачи — по формуле, а не по суждению модели; кандидаты на углубление.

  python3 scripts/rank_impact.py tasks/<папка> [--limit 8 | --tier 1|2]

Читает досье `00d-map.md`, строки схемы `00m-schema.txt`, карту `map/`, клетки `00m-cells.csv` (если уже есть)
и рамки `00r-limits.md` (если есть). Для каждого документа считает баллы:
  +3  документ типа отчёт о тесте, опрос, интервью, выгрузка или исследование, и в «Про кого» названа группа
      из схемы (слово из названия строки);
  +1  в карте не меньше пяти строк с числами;
  +1  в «Про продукт» есть сказанное о продукте;
  +2  статус «частично», если документ относится к группе схемы;
  +2  (после сборки модели) на документ опирается клетка со слабой надёжностью — версия или идея;
  +2  (после сборки модели) документ относится к группе схемы, а ни одна клетка на него не опирается.
Документ со статусом «не читается» не углубляется: он попадает в «нужна расшифровка».
Кандидаты на углубление — первые N по баллам (N — `--limit` или 12 для Tier 1 и 8 для Tier 2). Это порядок для
ограниченного бюджета, а не вердикт «важно или нет»: решать, читать ли вглубь, остаётся за оркестратором.

Пишет `00i-impact.md`. Код возврата 1 — нет досье или схемы.
"""
import csv
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_map import blocks, fields, read  # noqa: E402
from build_model import read_schema  # noqa: E402

POINT_TYPES = ["отчёт о тесте", "опрос", "интервью", "выгрузка", "исследование"]


def stems(rows):
    out = []
    for r in rows:
        for w in re.findall(r"[А-Яа-яЁёA-Za-z]{4,}", r):
            out.append(w.lower()[:6])
    return sorted(set(out))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.stderr.write(__doc__)
        return 2
    task = args[0].rstrip("/")
    limit = 8
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    elif "--tier" in sys.argv:
        limit = 12 if sys.argv[sys.argv.index("--tier") + 1] == "1" else 8
    text = read(os.path.join(task, "00d-map.md"))
    rows, feats = read_schema(task)
    if not text or not rows:
        print("Нет досье 00d-map.md или схемы 00m-schema.txt: считать нечего.")
        return 1
    st = stems(rows)
    cited = {}
    cells = os.path.join(task, "00m-cells.csv")
    have_model = os.path.exists(cells)
    if have_model:
        from build_model import entry_level
        for e in csv.DictReader(open(cells, encoding="utf-8", newline="")):
            e = {k: (v or "").strip() for k, v in e.items() if k}
            cited.setdefault(e.get("source", ""), []).append(entry_level(e) if e.get("n") is not None and e.get("group_match") in
                                                                ("точная", "соседняя", "другая") else "идея")
    res = []
    for fid, b in blocks(text).items():
        f = fields(b)
        typ = f.get("Тип", "").lower()
        status = f.get("Статус чтения", "").lower()
        who = f.get("Про кого", "").lower()
        group = any(s in who for s in st)
        point = any(typ.startswith(t) for t in POINT_TYPES)
        nnum = 0
        mp = os.path.join(task, "map", fid + ".json")
        if os.path.exists(mp):
            nnum = sum(1 for l in json.load(open(mp, encoding="utf-8"))["lines"] if "число" in l["tags"])
        prod = f.get("Про продукт", "").strip().lower()
        score, why = 0, []
        if status.startswith("не читается"):
            res.append((fid, -1, "нужна расшифровка", typ, status))
            continue
        if point and group:
            score += 3
            why.append("группа +3")
        if nnum >= 5:
            score += 1
            why.append("числа +1")
        if prod and not prod.startswith("нет"):
            score += 1
            why.append("продукт +1")
        if status.startswith("частично") and group:
            score += 2
            why.append("частично +2")
        if have_model:
            lv = cited.get(fid, [])
            if any(x in ("версия", "идея") for x in lv) and "значение" not in lv:
                score += 2
                why.append("слабая клетка +2")
            if group and not lv:
                score += 2
                why.append("ни одна клетка +2")
        res.append((fid, score, ", ".join(why) or "—", typ, status))
    ranked = sorted([r for r in res if r[1] >= 0], key=lambda r: (-r[1], r[0]))
    cand = [r[0] for r in ranked[:limit] if r[1] > 0]
    unread = [r[0] for r in res if r[1] < 0]
    md = ["# Важность документов (посчитано скриптом): %s" % os.path.basename(task), "",
          "Формула — в докстринге `scripts/rank_impact.py`. Лимит углубления: %d. Модель собрана: %s." % (limit, "да" if have_model else "нет"), "",
          "## Кандидаты на углубление", ""] + (["- " + c for c in cand] or ["- нет"]) + \
         ["", "## Нужна расшифровка (не читается)", ""] + (["- " + c for c in unread] or ["- нет"]) + \
         ["", "## Все документы по баллам", "", "| id | баллы | из чего | тип | статус |", "| --- | --- | --- | --- | --- |"] + \
         ["| %s | %s | %s | %s | %s |" % (r[0], r[1] if r[1] >= 0 else "—", r[2], r[3], r[4]) for r in
          sorted(res, key=lambda r: (-r[1], r[0]))]
    open(os.path.join(task, "00i-impact.md"), "w", encoding="utf-8").write("\n".join(md) + "\n")
    print("Важность: документов %d, кандидатов на углубление %d, нужна расшифровка %d." % (len(res), len(cand), len(unread)))
    print("  Углубить: " + (", ".join(cand) or "—"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
