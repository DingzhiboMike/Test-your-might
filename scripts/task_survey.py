#!/usr/bin/env python3
"""Сводка по завершённым задачам: где ответ мог остановиться на «нет данных» или «сузить». Для задач про саму систему.

  python3 scripts/task_survey.py [tasks]        # таблица по папкам с 08-handoff.md и итоги

По каждой задаче из файлов, без модели: вердикты проверки по сути (`02c-validation.md`), исходы шагов оркестратора
(`log.md`, строки «Результат:»), на каком месте сдачи стоит блок «Лучшая версия», чем открывается сдача (данные и
«рано» вместо версии — отметка «данные первыми») и сколько веб-источников в реестре. Скрипт считает форму: он не
знает, полезен ли ответ человеку. Сколько человек запустил после сдачи — он видит сам, это в сводку не попадает.
Задачи читаются как объект диагностики системы; ничего из них в `context/` не переносится.
"""
import csv
import os
import re
import sys

OPEN_HEAD = re.compile(r"что нужно.*(дальше|двигаться)|нужно, чтобы", re.I)
OPEN_TEXT = re.compile(r"рано|нечего|нет данных|не подтвержд|без ваших|ни одно направление", re.I)
VERDICT = re.compile(r"^\s*Вердикт\s*:\s*([а-яё]+(?: [а-яё]+){0,2})", re.M | re.I)
STEP = re.compile(r"^Результат:\s*(совпал|частичный промах|промах)", re.M)
HEAD = re.compile(r"^(#{1,2})\s+(.*?)\s*$", re.M)


def read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def count(rx, text):
    out = {}
    for m in rx.finditer(text):
        k = m.group(1).strip().lower()
        out[k] = out.get(k, 0) + 1
    return out


def web_sources(task):
    try:
        rows = list(csv.DictReader(open(os.path.join(task, "sources.csv"), encoding="utf-8", newline="")))
    except OSError:
        return 0
    return sum(1 for r in rows if r.get("kind") == "web")


def handoff_facts(text):
    heads = [h for h in HEAD.findall(text) if h[0] == "##"]
    names = [h[1] for h in heads]
    version = next((i + 1 for i, n in enumerate(names) if re.search(r"лучшая версия|на что ставить|что делать", n, re.I)), 0)
    first_body = ""
    m = HEAD.search(text)
    if m:
        first_body = text[m.end():m.end() + 400]
    data_first = bool(names and OPEN_HEAD.search(names[0])) or bool(OPEN_TEXT.search(first_body))
    return len(names), version, data_first


def survey(root):
    rows = []
    for name in sorted(os.listdir(root)):
        task = os.path.join(root, name)
        ho = read(os.path.join(task, "08-handoff.md"))
        if not ho:
            continue
        verdicts = count(VERDICT, read(os.path.join(task, "02c-validation.md")))
        steps = count(STEP, read(os.path.join(task, "log.md")))
        total, version, data_first = handoff_facts(ho)
        rows.append({"task": name, "verdicts": verdicts, "steps": steps, "sections": total, "version_at": version,
                     "data_first": data_first, "web": web_sources(task)})
    return rows


def fmt(d):
    return ", ".join("%s %d" % (k, v) for k, v in sorted(d.items())) or "—"


def main():
    root = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "tasks"
    if not os.path.isdir(root):
        print("task_survey: нет папки %s" % root)
        return 1
    rows = survey(root)
    if not rows:
        print("task_survey: в %s нет задач с 08-handoff.md" % root)
        return 0
    print("| Задача | Вердикты | Исходы шагов | «Лучшая версия» — раздел № | Данные первыми | Веб-источников |")
    print("| --- | --- | --- | --- | --- | --- |")
    for r in rows:
        print("| %s | %s | %s | %s | %s | %d |" % (r["task"], fmt(r["verdicts"]), fmt(r["steps"]),
                                                   r["version_at"] or "нет", "да" if r["data_first"] else "нет", r["web"]))
    allv, alls = {}, {}
    for r in rows:
        for k, v in r["verdicts"].items():
            allv[k] = allv.get(k, 0) + v
        for k, v in r["steps"].items():
            alls[k] = alls.get(k, 0) + v
    nv, ns = sum(allv.values()), sum(alls.values())
    print()
    print("Задач: %d. Вердиктов: %d (%s)." % (len(rows), nv, fmt(allv)))
    if nv and allv.get("сузить"):
        print("Доля «сузить»: %d%%." % round(100 * allv["сузить"] / nv))
    if ns:
        print("Шагов с исходом: %d (%s); «совпал» — %d%%." % (ns, fmt(alls), round(100 * alls.get("совпал", 0) / ns)))
    nd = sum(1 for r in rows if r["data_first"])
    print("Сдач, открытых данными или «рано»: %d из %d. Это отметка по форме текста, не оценка пользы." % (nd, len(rows)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
