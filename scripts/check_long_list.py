#!/usr/bin/env python3
"""Отсев длинного списка ходов в режиме ширины — по правилам, записанным до генерации, а не на глаз.

  python3 scripts/check_long_list.py tasks/<папка> [--top 5]

Читает таблицу из `02-long-list.md` (генератор, режим «ширина»). Колонки по порядку:

| № | Ход | Кому | Вариант решения | Опора | Дешёвая проверка | Дней до сигнала |

Правила отсева — неизменные, их знает генератор до того, как пишет список:
1. Строк 15–25. Меньше или больше — ошибка: режим ширины не сработал или превратился в свалку.
2. Вариант решения — буква из поля РЕШЕНИЕ в ТЗ. Нет буквы или её нет в ТЗ — отсеян «не сдвигает решение».
   Если в ТЗ «решения нет», правило не применяется.
3. Нет ни одной опоры [F-id] и нет дешёвой проверки — отсеян «не на чем стоять и нечем проверить».
4. Дней до сигнала больше 30 или не число — отсеян «дороже месяца».
5. Ход дословно повторяет предыдущий (после нормализации) — отсеян «повтор».

Вес опоры — по типу источника в `sources.csv`: прямая речь, данные, результат — 2; веб и прочее — 1; утверждение
команды (claim) — 0: бриф опорой не служит. Ход стоит на сумме весов разных источников.

В глубину (`--top`, по умолчанию 5) — по покрытию, а не по числу цитат, иначе дешёвые мелочи с одной цитатой
вытесняют направления:
1. лучший ход с пометкой «[наперекор]» — против утверждения команды;
2. лучший «[контрольный]» — вне вектора консультанта;
3. по одному лучшему ходу на каждый ещё не занятый слой (колонка «Слой»), слои — по весу их лучшего хода;
4. остаток — по весу.
«Лучший» — больше вес опоры, при равенстве меньше дней до сигнала, при равенстве раньше в списке. Ход, который
почти повторяет уже отобранный (общих основ слов 60% и больше), пропускается и идёт «в запас». Остальные
прошедшие — «в запасе». Опора здесь только взвешивается; цитаты сверяет check_quotes, держится ли ход — проверка
по сути.

Отчёт: tasks/<папка>/checks/long-list.md — таблица «в глубину / в запасе / отсеян — причина». Его оркестратор
передаёт генератору как вход второго вызова. Код возврата 1 — строк не 15–25 или прошло меньше трёх.
"""
import argparse
import csv
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_path import decision_variants  # noqa: E402
from check_diversity import jaccard, layer, stems  # noqa: E402

WEIGHT = {"voice": 2, "data": 2, "result": 2, "claim": 0}


def weights(task):
    """Вес источника по реестру: прямая речь и данные — 2, утверждение команды — 0, остальное — 1."""
    out = {}
    try:
        with open(os.path.join(task, "sources.csv"), encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                out[r["id"]] = WEIGHT.get(r.get("ctx_type") or "", 1)
    except OSError:
        pass
    return out


def read(path):
    return open(path, encoding="utf-8").read() if os.path.exists(path) else ""


def norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[«»\"*_`.,;:!?]", "", s.replace("ё", "е").lower())).strip()


def rows(text):
    out = []
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 7 or not re.match(r"^\d+$", cells[0]):
            continue
        out.append(cells)
    return out


def empty(cell):
    return not cell.strip(" —-–") or cell.strip().lower() in ("нет", "n/a")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("task")
    p.add_argument("--top", type=int, default=5)
    a = p.parse_args()
    task = a.task.rstrip("/")
    text = read(os.path.join(task, "02-long-list.md"))
    if not text:
        print("Длинного списка нет: проверять нечего.")
        return 0
    tz = read(os.path.join(task, "00-tz.md"))
    variants = decision_variants(tz)
    table = rows(text)
    head = next(([c.strip().lower() for c in l.strip().strip("|").split("|")] for l in text.splitlines()
                 if l.strip().startswith("|") and "ход" in l.lower() and "кому" in l.lower()), [])
    li = head.index("слой") if "слой" in head else None
    w = weights(task)
    errors = []
    if not 15 <= len(table) <= 25:
        errors.append("строк в списке %d, нужно 15–25" % len(table))
    passed, dropped, seen = [], [], set()
    for idx, c in enumerate(table):
        num, move, _who, var, support, cheap, days = c[:7]
        reason = ""
        letters = set(re.findall(r"\b([А-ЯЁA-Z])\b", var))
        refs = set(re.findall(r"\bF-\d+\b", support))
        d = re.match(r"^\s*(\d+)", days)
        key = norm(move)
        if variants and not (letters & set(variants)):
            reason = "не сдвигает решение"
        elif not refs and empty(cheap):
            reason = "не на чем стоять и нечем проверить"
        elif not d or int(d.group(1)) > 30:
            reason = "дороже месяца"
        elif key in seen:
            reason = "повтор"
        seen.add(key)
        if reason:
            dropped.append((num, move, reason))
        else:
            weight = sum(w.get(r, 1) for r in refs)
            lay = layer(c[li]) if li is not None and li < len(c) else None
            passed.append({"key": (-weight, int(d.group(1)), idx), "num": num, "move": move, "w": weight,
                           "days": int(d.group(1)), "layer": lay, "stems": stems(move), "why": ""})
    passed.sort(key=lambda r: r["key"])
    deep = []

    def take(r, why):
        if len(deep) >= a.top or r in deep or any(jaccard(r["stems"], x["stems"]) >= 0.6 for x in deep):
            return
        r["why"] = why
        deep.append(r)

    for mark, why in (("[наперекор]", "наперекор"), ("[контрольн", "контрольный")):
        best = next((r for r in passed if mark in r["move"].lower()), None)
        if best:
            take(best, why)
    for r in passed:
        if r["layer"] and r["layer"] not in {x["layer"] for x in deep}:
            take(r, "слой: " + r["layer"])
    for r in passed:
        take(r, "по опоре")
    spare = [r for r in passed if r not in deep]
    if len(passed) < 3:
        errors.append("прошли отсев %d ходов, нужно хотя бы 3" % len(passed))

    os.makedirs(os.path.join(task, "checks"), exist_ok=True)
    out = ["# Отсев длинного списка: " + os.path.basename(task), "",
           "Строк: %d, прошли: %d, в глубину: %d, отсеяно: %d" % (len(table), len(passed), len(deep), len(dropped)), "",
           "| № | Ход | Итог | Вес опоры | Дней | Почему |", "| --- | --- | --- | --- | --- | --- |"]
    out += ["| %s | %s | в глубину | %d | %d | %s |" % (r["num"], r["move"], r["w"], r["days"], r["why"]) for r in deep]
    out += ["| %s | %s | в запасе | %d | %d | |" % (r["num"], r["move"], r["w"], r["days"]) for r in spare]
    out += ["| %s | %s | отсеян — %s | | | |" % r for r in dropped]
    out += ["", "## Ошибки"] + (["- " + e for e in errors] or ["- нет"])
    open(os.path.join(task, "checks", "long-list.md"), "w", encoding="utf-8").write("\n".join(out) + "\n")
    for e in errors:
        print("длинный список: " + e)
    print("Длинный список: строк %d, прошли %d, в глубину %s." % (len(table), len(passed), ", ".join(r["num"] for r in deep) or "—"))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
