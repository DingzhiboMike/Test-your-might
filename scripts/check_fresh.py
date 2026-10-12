#!/usr/bin/env python3
"""Проверяет, что старые веб-источники не выдаются за текущее положение дел.

  python3 scripts/check_fresh.py tasks/<папка> <артефакт> [--years 2]

Для каждой ссылки [F-id] в артефакте, если источник из веба (kind=web в sources.csv):
- дата данных (`data_date`, а если её нет — `pub_date`) старше порога (по умолчанию два года, как в web-protocol.md,
  п. 3) — в той же строке должен стоять год этой даты: читатель видит, что это история, а не сегодня. Нет года — ошибка;
- даты нет (unknown) — предупреждение: такой источник не может быть единственной опорой вывода о текущем рынке.

Источники контекста и интервью не проверяются: их свежесть решает диспетчер на согласовании.
Отчёт: tasks/<папка>/checks/fresh.md. Код возврата 1 — есть ошибки.
"""
import argparse
import csv
import datetime
import glob
import os
import re
import sys


def parse_date(value):
    m = re.match(r"^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?$", value or "")
    if not m:
        return None
    return datetime.date(int(m.group(1)), int(m.group(2) or 1), int(m.group(3) or 1))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("task")
    p.add_argument("artifact", help="файл или маска внутри папки задачи")
    p.add_argument("--years", type=float, default=2.0)
    p.add_argument("--today", default="", help="для самопроверки: дата вместо сегодняшней, ГГГГ-ММ-ДД")
    a = p.parse_args()
    task = a.task.rstrip("/")
    reg = os.path.join(task, "sources.csv")
    if not os.path.exists(reg):
        print("Свежесть: реестра нет — проверять нечего.")
        return 0
    with open(reg, encoding="utf-8") as f:
        web = {r["id"]: r for r in csv.DictReader(f) if r.get("kind") == "web"}
    today = parse_date(a.today) or datetime.date.today()
    limit = today - datetime.timedelta(days=int(365.25 * a.years))
    errors, warns, cited = [], [], set()
    files = sorted(glob.glob(os.path.join(task, a.artifact))) or [os.path.join(task, a.artifact)]
    for path in files:
        if not os.path.exists(path):
            continue
        name = os.path.basename(path)
        for i, line in enumerate(open(path, encoding="utf-8").read().splitlines(), 1):
            for sid in re.findall(r"\b(F-\d+)\b", line):
                row = web.get(sid)
                if not row:
                    continue
                cited.add(sid)
                raw = row.get("data_date") if row.get("data_date") not in ("", "unknown", None) else row.get("pub_date")
                d = parse_date(raw)
                if d is None:
                    if (sid, "unknown") not in {(w[0], w[1]) for w in warns}:
                        warns.append((sid, "unknown", "%s:%d" % (name, i)))
                    continue
                if d < limit and str(d.year) not in line:
                    errors.append("%s:%d — %s от %s старше %g лет: поставь год в текст («по данным %d года») "
                                  "или найди свежее" % (name, i, sid, raw, a.years, d.year))

    os.makedirs(os.path.join(task, "checks"), exist_ok=True)
    out = ["# Свежесть веб-источников: " + os.path.basename(task), "",
           "Порог: %g лет (раньше %s). Веб-источников в тексте: %d" % (a.years, limit.isoformat(), len(cited)), "",
           "## Ошибки"] + (["- " + e for e in errors] or ["- нет"])
    out += ["", "## Без даты"] + (["- %s (первое упоминание %s)" % (w[0], w[2]) for w in warns] or ["- нет"])
    open(os.path.join(task, "checks", "fresh.md"), "w", encoding="utf-8").write("\n".join(out) + "\n")
    for e in errors:
        print("свежесть: " + e)
    for w in warns:
        print("свежесть (внимание): %s без даты — %s" % (w[0], w[2]))
    if not errors:
        print("Свежесть: веб-источников %d, без года в тексте старых нет, без даты %d." % (len(cited), len(warns)))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
