#!/usr/bin/env python3
"""Чувствительность формулы из реестра чисел: какой параметр сильнее всего двигает итог.

  python3 scripts/sensitivity.py --task tasks/<папка> --formula "N-001 * N-002 * N-003" \
      --range N-002=0.25..0.40 --range N-003=0.55..0.75 [--threshold 800]

Базовые значения берутся из tasks/<папка>/numbers.csv. Параметры меняются по одному — от нижней границы до верхней,
остальные остаются базовыми. Параметры упорядочиваются по размаху итога («торнадо»): сверху тот, что двигает итог
сильнее. С --threshold печатается, пересекает ли итог порог при изменении параметра (вывод меняется на
противоположный). Формулы — как в add_number.py: + - * / **, sqrt, ln, exp, phi, ppf.

Метод: методология, О · Чувствительность. Скрипт считает размах, а не вероятность: диапазоны задаёт человек.
"""
import argparse
import csv
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from add_number import evaluate  # noqa: E402


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--task", required=True)
    p.add_argument("--formula", required=True)
    p.add_argument("--range", action="append", default=[], dest="ranges", help="N-id=низ..верх, можно несколько раз")
    p.add_argument("--threshold", type=float, default=None)
    a = p.parse_args()
    path = os.path.join(a.task, "numbers.csv")
    if not os.path.exists(path):
        sys.exit("sensitivity: нет %s" % path)
    with open(path, newline="", encoding="utf-8") as f:
        values = {r["id"]: float(r["value"]) for r in csv.DictReader(f)}
    if not a.ranges:
        sys.exit("sensitivity: нужен хотя бы один --range N-id=низ..верх")
    try:
        base = evaluate(a.formula, values)
    except (ValueError, ZeroDivisionError) as e:
        sys.exit("sensitivity: формула не считается: %s" % e)
    rows = []
    for spec in a.ranges:
        m = re.match(r"^(N-\d{3,})=(-?[\d.]+)\.\.(-?[\d.]+)$", spec.replace(",", "."))
        if not m:
            sys.exit("sensitivity: диапазон «%s» — ожидается N-001=0.25..0.40" % spec)
        nid, lo, hi = m.group(1), float(m.group(2)), float(m.group(3))
        if nid not in values:
            sys.exit("sensitivity: %s нет в реестре чисел" % nid)
        if lo > hi:
            lo, hi = hi, lo
        res = []
        for v in (lo, hi):
            vv = dict(values)
            vv[nid] = v
            try:
                res.append(evaluate(a.formula, vv))
            except (ValueError, ZeroDivisionError) as e:
                sys.exit("sensitivity: при %s=%g формула не считается: %s" % (nid, v, e))
        rows.append((abs(res[1] - res[0]), nid, lo, hi, res[0], res[1]))
    rows.sort(reverse=True)
    print("итог при базовых значениях: %.6g" % base)
    print("%-3s %-8s %-18s %-14s %-14s %s" % ("№", "параметр", "диапазон", "итог внизу", "итог вверху", "размах"))
    for i, (sw, nid, lo, hi, r0, r1) in enumerate(rows, 1):
        print("%-3d %-8s %-18s %-14.6g %-14.6g %.6g" % (i, nid, "%g..%g" % (lo, hi), r0, r1, sw))
    print("порядок влияния: " + " > ".join(r[1] for r in rows))
    if a.threshold is not None:
        print("порог %g: итог при базовых значениях %s" % (a.threshold, "выше" if base >= a.threshold else "ниже"))
        for sw, nid, lo, hi, r0, r1 in rows:
            crosses = min(r0, r1) < a.threshold <= max(r0, r1)
            print("  %s: %s" % (nid, "вывод меняется внутри диапазона" if crosses else "вывод не меняется внутри диапазона"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
