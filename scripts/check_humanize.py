#!/usr/bin/env python3
"""Сдача прошла humanizer и при этом не потеряла фактов: сверка с копией до правки.

  python3 scripts/check_humanize.py tasks/<папка>

Перед вызовом humanizer оркестратор сохраняет копии: `checks/08-handoff.before-humanizer.md` и, если правится итоговая
позиция, `checks/02e-position.before-humanizer.md`. Для каждого файла, у которого есть копия:
1. Числа — ни одно не пропало и не появилось новое (сравниваются множества чисел).
2. Цитаты в ёлочках длиннее 20 знаков — все на месте дословно.
3. Ссылки (http…) и строки в обратных кавычках — все на месте.
4. Заголовки `## …` — те же и в том же порядке.
5. Строк таблиц столько же.
6. Раздел `## Что лежит в папке задачи` не изменился.

Есть `08-handoff.md`, но нет копии `checks/08-handoff.before-humanizer.md` — ошибка: сдача не прошла humanizer.
Смысл — не усилена ли оценка до факта — скрипт не видит: это выборочный аудит и проверка смысла.
Отчёт: tasks/<папка>/checks/humanize.md. Код возврата 1 — есть ошибки.
"""
import os
import re
import sys

PAIRS = ("08-handoff.md", "02e-position.md")
NUM = re.compile(r"(?<![\w-])\d+(?:[.,]\d+)?")
QUOTE = re.compile(r"«([^»]{21,})»")
LINK = re.compile(r"https?://[^\s)>\]]+")
CODE = re.compile(r"`([^`\n]+)`")
INDEX = "## Что лежит в папке задачи"


def read(path):
    return open(path, encoding="utf-8").read() if os.path.exists(path) else ""


def index_part(text):
    i = text.find(INDEX)
    if i < 0:
        return ""
    rest = text[i + len(INDEX):]
    m = re.search(r"^## ", rest, re.M)
    return rest[:m.start()] if m else rest


def compare(name, before, after, errors):
    lost = sorted(set(NUM.findall(before)) - set(NUM.findall(after)))
    new = sorted(set(NUM.findall(after)) - set(NUM.findall(before)))
    if lost:
        errors.append("%s: пропали числа: %s" % (name, ", ".join(lost[:10])))
    if new:
        errors.append("%s: появились новые числа: %s" % (name, ", ".join(new[:10])))
    for kind, rx in (("цитата", QUOTE), ("ссылка", LINK), ("строка в обратных кавычках", CODE)):
        miss = [x for x in dict.fromkeys(rx.findall(before)) if x not in after]
        for x in miss[:5]:
            errors.append("%s: пропала %s: %s…" % (name, kind, x[:50]))
    hb = re.findall(r"^## .*$", before, re.M)
    ha = re.findall(r"^## .*$", after, re.M)
    if [h.strip() for h in hb] != [h.strip() for h in ha]:
        errors.append("%s: заголовки разделов «## …» изменились или переставлены" % name)
    rows_b = len(re.findall(r"^\s*\|", before, re.M))
    rows_a = len(re.findall(r"^\s*\|", after, re.M))
    if rows_b != rows_a:
        errors.append("%s: строк таблиц было %d, стало %d" % (name, rows_b, rows_a))
    if index_part(before).strip() != index_part(after).strip():
        errors.append("%s: раздел «Что лежит в папке задачи» изменён" % name)


def main():
    if len(sys.argv) < 2:
        sys.stderr.write(__doc__)
        return 2
    task = sys.argv[1].rstrip("/")
    if not os.path.exists(os.path.join(task, "08-handoff.md")):
        print("Сдачи нет: проверять нечего.")
        return 0
    errors, done = [], []
    for name in PAIRS:
        after = read(os.path.join(task, name))
        before = read(os.path.join(task, "checks", name.replace(".md", ".before-humanizer.md")))
        if not after:
            continue
        if not before:
            if name == "08-handoff.md":
                errors.append("08-handoff.md: нет копии checks/08-handoff.before-humanizer.md — сдача не прошла humanizer")
            continue
        if before == after:
            done.append(name + " (без изменений)")
            continue
        compare(name, before, after, errors)
        done.append(name)
    lines = ["# Сдача после humanizer", "", "Сверено с копией до правки: %s" % (", ".join(done) or "—"), ""]
    lines += (["Ошибки:"] + ["- " + e for e in errors]) if errors else ["Ошибок нет."]
    os.makedirs(os.path.join(task, "checks"), exist_ok=True)
    open(os.path.join(task, "checks", "humanize.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print("Сдача после humanizer: %s" % ("ОШИБКИ (%d)" % len(errors) if errors else "ок"))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
