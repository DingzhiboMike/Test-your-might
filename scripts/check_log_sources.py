#!/usr/bin/env python3
"""Проверяет, что каждый шаг-источник в логе поставлен, а не взят «для полноты».

  python3 scripts/check_log_sources.py tasks/<папка>

Шаг-источник — заголовок «ШАГ N — <скилл>», где скилл один из семи источников данных. В его блоке (до следующего
«ШАГ» или конца лога) должны быть строки:
- «Вопрос:»       — вопрос, канал, критерий ответа до поиска, бюджет запросов;
- «Зачем:»        — что без этого ответа генератору или проверке по сути пришлось бы угадывать;
- «Уже известно:» — что по вопросу уже лежит в контексте и реестре; утверждения команды — с пометкой «проверяется».

Пустое значение («Зачем: —», «Зачем:») не засчитывается. Ошибка — код возврата 1. Отчёт: tasks/<папка>/checks/log-sources.md.
"""
import os
import re
import sys

SOURCES = ("interview-analyst", "interview-synthesis", "market-analyze", "target-audience-analyst",
           "alternatives-analyst", "customer-path", "market-sizing")
FIELDS = ("Вопрос", "Зачем", "Уже известно")
STEP = re.compile(r"^ШАГ\s+(\d+)\s*[—-]\s*([\w-]+)", re.M)


def main():
    if len(sys.argv) < 2:
        sys.stderr.write(__doc__)
        return 2
    task = sys.argv[1].rstrip("/")
    path = os.path.join(task, "log.md")
    if not os.path.exists(path):
        print("Лога нет: проверять нечего.")
        return 0
    text = open(path, encoding="utf-8").read()
    heads = list(STEP.finditer(text))
    errors, checked = [], 0
    for i, m in enumerate(heads):
        skill = m.group(2)
        if skill not in SOURCES:
            continue
        checked += 1
        block = text[m.end():heads[i + 1].start() if i + 1 < len(heads) else len(text)]
        for field in FIELDS:
            f = re.search(r"^\s*%s:[ \t]*(.*)$" % re.escape(field), block, re.M)
            value = f.group(1).strip(" —-–\t") if f else ""
            if not value:
                errors.append("ШАГ %s — %s: нет строки «%s:» или она пустая" % (m.group(1), skill, field))

    os.makedirs(os.path.join(task, "checks"), exist_ok=True)
    out = ["# Шаги-источники в логе: " + os.path.basename(task), "", "Шагов-источников: %d" % checked, "", "## Ошибки"]
    out += ["- " + e for e in errors] or ["- нет"]
    open(os.path.join(task, "checks", "log-sources.md"), "w", encoding="utf-8").write("\n".join(out) + "\n")
    for e in errors:
        print("лог: " + e)
    if not errors:
        print("Шаги-источники: %d, ошибок нет." % checked)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
