#!/usr/bin/env python3
"""Источники, найденные на шаге, но не процитированные в артефакте.

Для проверки смысла: в найденном, но не вошедшем чаще всего лежит пропущенное — противоречащий
фрагмент, решающая деталь, одиночный сильный сигнал. Оркестратор передаёт этот список проверяющему.

  python3 scripts/list_unused.py tasks/<папка> src-market.md --since <время начала шага>

Без --since — все источники реестра, которых нет в артефакте.
"""
import argparse
import csv
import os
import re


def main():
    p = argparse.ArgumentParser()
    p.add_argument("task")
    p.add_argument("artifact")
    p.add_argument("--since", type=float, default=0)
    a = p.parse_args()

    reg = os.path.join(a.task, "sources.csv")
    if not os.path.exists(reg):
        print("реестра нет")
        return
    text = open(os.path.join(a.task, a.artifact), encoding="utf-8").read()
    cited = set(re.findall(r"\[(F-\d{3,})\]", text))
    with open(reg, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    unused = []
    for r in rows:
        if r["id"] in cited or r.get("read") == "not-read":
            continue
        ts = float(r.get("ts") or 0)
        if a.since and ts < a.since:
            continue
        unused.append(r)
    if not unused:
        print("неиспользованных источников нет")
        return
    print("Найдены, но не процитированы в {} ({}):".format(a.artifact, len(unused)))
    for r in unused:
        kind = r.get("level") and "уровень " + r["level"] or r.get("ctx_type") or r["kind"]
        print("- [{}] {} · {} · {} знаков{}".format(r["id"], r["location"], kind, r.get("chars", "?"),
                                                   " · " + r["note"] if r.get("note") else ""))


if __name__ == "__main__":
    main()
