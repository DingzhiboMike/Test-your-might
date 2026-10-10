#!/usr/bin/env python3
"""Регистрирует число в реестре чисел задачи: tasks/<задача>/numbers.csv.

Число, на котором стоит вывод, живёт с паспортом: что измерено, где, за какой период, от какой базы,
кто произвёл. В артефакте рядом с числом ставится его id: «12 тыс. компаний [N-003]».

Факт из источника — фрагмент с числом должен найтись в сыром тексте источника:
  python3 scripts/add_number.py --task tasks/<папка> --kind fact --key smb_count \
      --what "число МСП в сегменте" --value 12400 --unit "компаний" --as-written "12,4 тыс." \
      --scope "Россия, ОКВЭД 69" --period 2025-12 --source F-007 --fragment "насчитывалось 12,4 тыс. организаций"

Производное — только формулой из других чисел реестра, скрипт пересчитывает сам:
  python3 scripts/add_number.py --task tasks/<папка> --kind derived --key need_clients \
      --what "нужно клиентов под цель" --formula "N-001 / N-002" --value 834 --unit "клиентов"

Допущение — без источника, с причиной:
  python3 scripts/add_number.py --task tasks/<папка> --kind assumption --key share \
      --what "доля сегмента за год" --value 0.03 --unit "доля" --note "нет внутренней конверсии"

Печатает id. Ошибка — код 2 и причина.
"""
import argparse
import ast
import csv
import operator
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_quotes import norm  # noqa: E402

FIELDS = ["id", "key", "kind", "what", "value", "unit", "as_written", "scope", "period", "base",
          "source", "fragment", "formula", "note"]
KINDS = {"fact", "derived", "assumption"}
OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
TOLERANCE = 0.01  # 1%: округление при записи


def fail(msg):
    sys.stderr.write("add_number: " + msg + "\n")
    sys.exit(2)


def read(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def evaluate(formula, values):
    """Безопасный пересчёт: только числа, N-id и + - * / со скобками."""
    expr = re.sub(r"N-(\d{3,})", r"N_\1", formula)
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        raise ValueError("формула не разбирается: " + formula)

    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.BinOp) and type(n.op) in OPS:
            return OPS[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.USub):
            return -ev(n.operand)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, ast.Name) and n.id.startswith("N_"):
            nid = "N-" + n.id[2:]
            if nid not in values:
                raise ValueError("в формуле {} нет в реестре чисел".format(nid))
            return values[nid]
        raise ValueError("в формуле допустимы только числа, N-id и + - * /")
    return ev(tree)


def close(a, b):
    return abs(a - b) <= TOLERANCE * max(abs(a), abs(b), 1e-9)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--task", required=True)
    p.add_argument("--kind", required=True, choices=sorted(KINDS))
    p.add_argument("--key", required=True, help="короткий ключ показателя латиницей: одинаковый у одного и того же показателя из разных источников")
    p.add_argument("--what", required=True, help="что именно измерено, словами")
    p.add_argument("--value", required=True, type=float, help="значение числом, без пробелов: 12400, 0.03")
    p.add_argument("--unit", required=True, help="единица: компаний, руб., %, доля, руб./год")
    p.add_argument("--as-written", default="", help="как число записано в источнике, если не совпадает с --value: «12,4 тыс.»")
    p.add_argument("--scope", default="", help="где: страна, регион, сегмент")
    p.add_argument("--period", default="", help="к какому периоду или дате относятся данные: 2025, 2025-Q3, 2025-12")
    p.add_argument("--base", default="", help="от чего доля или с чем сравнение: «от всех МСП», «к 2024»")
    p.add_argument("--source", default="", help="id источника из sources.csv (для fact)")
    p.add_argument("--fragment", default="", help="дословный фрагмент источника с этим числом (для fact)")
    p.add_argument("--formula", default="", help="для derived: выражение из N-id, например N-001 / N-002 * 100")
    p.add_argument("--note", default="")
    a = p.parse_args()

    if not os.path.isdir(a.task):
        fail("папки задачи нет: " + a.task)
    if not re.match(r"^[a-z0-9_]+$", a.key):
        fail("--key — латиница, цифры и _: smb_count, avg_check")
    path = os.path.join(a.task, "numbers.csv")
    rows = read(path)
    values = {r["id"]: float(r["value"]) for r in rows}

    if a.kind == "fact":
        if not a.source or not a.fragment:
            fail("для fact нужны --source и --fragment")
        if a.formula:
            fail("у fact нет формулы — это derived")
        sources = {r["id"]: r for r in read(os.path.join(a.task, "sources.csv"))}
        src = sources.get(a.source)
        if not src:
            fail("источника {} нет в sources.csv — сначала add_source.py".format(a.source))
        if src.get("read") == "not-read" or src.get("method") == "summary":
            fail("источник {} не прочитан или есть только пересказ — число из него опорой не будет".format(a.source))
        raw_path = os.path.join(a.task, "sources", "raw", a.source + ".txt")
        raw = norm(open(raw_path, encoding="utf-8").read()) if os.path.exists(raw_path) else ""
        if norm(a.fragment) not in raw:
            fail("фрагмента нет в сыром тексте {}: «{}»".format(a.source, a.fragment[:80]))
        written = a.as_written or ("%g" % a.value)
        squash = lambda s: re.sub(r"[\s  ]", "", norm(s))
        if squash(written) not in squash(a.fragment):
            fail("во фрагменте нет числа «{}» — укажи --as-written так, как оно записано".format(written))
        if not a.period:
            sys.stderr.write("add_number: внимание — нет --period: к какой дате относятся данные? (D3)\n")
    elif a.kind == "derived":
        if not a.formula:
            fail("для derived нужна --formula из N-id")
        if a.source or a.fragment:
            fail("у derived нет источника — его опора в формуле")
        try:
            got = evaluate(a.formula, values)
        except (ValueError, ZeroDivisionError) as e:
            fail(str(e))
        if not close(got, a.value):
            fail("по формуле {} получается {:g}, а не {:g}".format(a.formula, got, a.value))
    else:
        if a.source or a.formula:
            fail("у допущения нет источника и формулы")
        if not a.note:
            fail("у допущения нужен --note: почему допущение и что заменило бы его фактом")

    if a.unit.strip() in ("%", "доля") and not a.base:
        sys.stderr.write("add_number: внимание — доля без --base: от чего она посчитана? (D4)\n")

    nums = [int(r["id"][2:]) for r in rows if r["id"].startswith("N-")]
    nid = "N-{:03d}".format(max(nums) + 1 if nums else 1)
    row = {k: "" for k in FIELDS}
    row.update(id=nid, key=a.key, kind=a.kind, what=a.what, value="%g" % a.value, unit=a.unit,
               as_written=a.as_written, scope=a.scope, period=a.period, base=a.base, source=a.source,
               fragment=a.fragment, formula=a.formula, note=a.note)
    new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)
    print(nid)


if __name__ == "__main__":
    main()
