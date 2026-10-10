#!/usr/bin/env python3
"""Проверяет реестр чисел задачи и числа в артефактах.

  python3 scripts/check_numbers.py tasks/<папка>

- факты: фрагмент с числом всё ещё есть в сыром тексте источника;
- производные: пересчёт по формуле совпадает с записанным значением;
- в артефактах: у каждой ссылки [N-id] рядом стоит именно это число;
- один и тот же показатель (key) с разными значениями: если период, место, единица или база
  различаются — это не противоречие, а разные условия (V18); если совпадают — настоящее
  противоречие, в тексте должны быть обе цифры;
- предупреждения: факт без периода (D3), доля без базы (D4).

Пишет отчёт в tasks/<папка>/checks/numbers.md. Код 1 — есть ошибки.
"""
import csv
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_quotes import norm  # noqa: E402
from add_number import evaluate, close  # noqa: E402

SKIP = {"log.md", "00-tz.md"}
REF_RE = re.compile(r"\[(N-\d{3,})\]")


def squash(s):
    return re.sub(r"[\s  ]", "", norm(s)).replace(",", ".")


def forms(r):
    v = float(r["value"])
    out = {squash(r["as_written"])} if r.get("as_written") else set()
    out |= {squash("%g" % v), squash("{:,.0f}".format(v).replace(",", " "))}
    if r["unit"].strip() == "доля":
        out.add(squash("%g" % (v * 100)))
    return {x for x in out if x}


def main():
    if len(sys.argv) < 2:
        sys.stderr.write(__doc__)
        sys.exit(2)
    task = sys.argv[1].rstrip("/")
    path = os.path.join(task, "numbers.csv")
    if not os.path.exists(path):
        print("реестра чисел нет")
        return
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    by_id = {r["id"]: r for r in rows}
    values = {r["id"]: float(r["value"]) for r in rows}
    errors, warns, out = [], [], ["# Проверка чисел: " + os.path.basename(task), "", "Чисел в реестре: {}.".format(len(rows))]

    for r in rows:
        if r["kind"] == "fact":
            raw = os.path.join(task, "sources", "raw", r["source"] + ".txt")
            if not os.path.exists(raw) or norm(r["fragment"]) not in norm(open(raw, encoding="utf-8").read()):
                errors.append("[{}] фрагмента больше нет в источнике {}".format(r["id"], r["source"]))
            if not r.get("period"):
                warns.append("[{}] {} — нет периода данных (D3)".format(r["id"], r["what"]))
        elif r["kind"] == "derived":
            try:
                got = evaluate(r["formula"], values)
                if not close(got, values[r["id"]]):
                    errors.append("[{}] по формуле {} получается {:g}, записано {}".format(r["id"], r["formula"], got, r["value"]))
            except (ValueError, ZeroDivisionError) as e:
                errors.append("[{}] {}".format(r["id"], e))
        if r["unit"].strip() in ("%", "доля") and not r.get("base"):
            warns.append("[{}] {} — доля без базы (D4)".format(r["id"], r["what"]))

    groups = defaultdict(list)
    for r in rows:
        if r["kind"] == "fact":
            groups[r["key"]].append(r)
    conflicts, real_keys = [], set()
    for key, rs in groups.items():
        if len({r["value"] for r in rs}) < 2:
            continue
        same = defaultdict(list)
        for r in rs:
            same[tuple(r.get(f, "") for f in ("period", "scope", "unit", "base"))].append(r)
        for cond, grp in same.items():
            if len({r["value"] for r in grp}) > 1:
                real_keys.add(key)
                conflicts.append("{}: {} — одинаковые условия, разные значения: настоящее противоречие, в тексте нужны обе цифры".format(
                    key, ", ".join("{}={} {}".format(r["id"], r["value"], r["unit"]) for r in grp)))
        if len(same) > 1:
            conflicts.append("{}: {} — разные условия (период, место, единица или база), это не противоречие; сравнивать только с оговоркой".format(
                key, ", ".join("{}={} {}".format(r["id"], r["value"], r["unit"]) for r in rs)))

    names = sorted(n for n in os.listdir(task) if n.endswith(".md") and n not in SKIP)
    cited = defaultdict(set)
    for name in names:
        text = open(os.path.join(task, name), encoding="utf-8").read()
        for m in REF_RE.finditer(text):
            nid = m.group(1)
            cited[nid].add(name)
            r = by_id.get(nid)
            if not r:
                errors.append("{}: [{}] нет в реестре чисел".format(name, nid))
                continue
            before = text[max(0, m.start() - 60):m.start()]
            before = before[before.rfind("]") + 1:]  # не захватывать число предыдущей ссылки
            window = squash(before)
            if not any(f in window for f in forms(r)):
                errors.append("{}: рядом с [{}] нет числа {} {}".format(name, nid, r.get("as_written") or r["value"], r["unit"]))
        for key in real_keys:
            used = [r["id"] for r in groups[key] if r["id"] in REF_RE.findall(text)]
            if len(used) == 1:
                warns.append("{}: по показателю {} есть противоречие, а в тексте только {}".format(name, key, used[0]))

    out += ["", "## Ошибки"] + (["- " + e for e in errors] or ["- нет"])
    out += ["", "## Разные значения одного показателя"] + (["- " + c for c in conflicts] or ["- нет"])
    out += ["", "## Предупреждения"] + (["- " + w for w in warns] or ["- нет"])
    report = "\n".join(out) + "\n"
    os.makedirs(os.path.join(task, "checks"), exist_ok=True)
    with open(os.path.join(task, "checks", "numbers.md"), "w", encoding="utf-8") as f:
        f.write(report)
    sys.stdout.write(report)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
