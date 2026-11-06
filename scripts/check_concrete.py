#!/usr/bin/env python3
"""«Нет данных» — не ответ и в валидации: у каждого такого утверждения есть лучшая догадка и путь к конкретике.

  python3 scripts/check_concrete.py tasks/<папка>

Тип «валидация», любой уровень профиля. Проверяет форму, а не смысл:
1. `02c-validation.md`: у каждого утверждения «У-k» с исходом «нет данных» есть поля «Версии», «Скорее»,
   «Что даст ответ», «Где посмотреть». «Скорее» — одна версия с уверенностью (низкая / средняя / высокая),
   а не отказ («нет данных», «не различимы», «зависит от» …). «Где посмотреть» — три ступени от дешёвой к дорогой:
   «у вас —», «открыто —», «живая проверка —»; ступень, которой нет, пишется «нет — почему».
2. `06-validation.md`: в таблице утверждений есть столбец «Скорее», и у строк с исходом «нет данных» он заполнен
   версией, а не отказом.
Держит ли догадка смысл, скрипт не видит: это проверка смысла и аудит.
Ошибка — код возврата 1. Отчёт: tasks/<папка>/checks/concrete.md.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_forecast import REFUSAL, fields, meaningful  # noqa: E402

NO_DATA = re.compile(r"нет\s+данных|не\s+проверено", re.I)
FIELDS = ("Версии", "Что косвенно за каждую", "Что каждая значит для идеи", "Скорее", "Что даст ответ",
          "Где посмотреть", "Опор", "Что не так", "Причина исхода", "Из контекста", "Из сети", "Исход")
REQUIRED = ("Версии", "Скорее", "Что даст ответ", "Где посмотреть")
NOT_SURE = re.compile(r"^\W*(не\s+различим|равновероятн|50\s*/\s*50|непонятно|сложно сказать)", re.I)
CONFIDENCE = re.compile(r"уверенност\w*\s*[:—–-]?\s*(низк|средн|высок)", re.I)
RUNGS = (("у вас", r"у\s+вас\s*[—–:-]"), ("открыто", r"открыт\w*\s*[—–:-]"),
         ("живая проверка", r"живая\s+проверка\s*[—–:-]"))


def read(path):
    return open(path, encoding="utf-8").read() if os.path.exists(path) else ""


def refusal(value):
    v = re.sub(r"\[оценка\]|^\W*оценка\W*", "", value.strip(), flags=re.I)
    return bool(REFUSAL.match(v) or NOT_SURE.match(v))


def claims(text):
    """[(номер, текст блока)] — блоки «У-k — …» до следующего утверждения или заголовка."""
    heads = list(re.finditer(r"^\s*(?:#{1,4}\s*)?\**У-(\d+)\b(?!\+)", text, re.M))
    out = []
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        stop = re.search(r"^#{1,3}\s*(Приложение|ПРИЛОЖЕНИЕ)", text[m.end():end], re.M)
        if stop:
            end = m.end() + stop.start()
        out.append((m.group(1), text[m.start():end]))
    return out


def check_validation(text):
    errors, n_open = [], 0
    for num, block in claims(text):
        got = fields(block, FIELDS)
        outcome = got.get("Исход", ("", ""))[1].split("\n")[0]
        if not NO_DATA.search(outcome):
            continue
        n_open += 1
        where = "У-%s" % num
        for f in REQUIRED:
            if f not in got or not meaningful(got[f][1]):
                errors.append("%s: исход «нет данных», а поля «%s» нет или оно пустое" % (where, f))
        if "Скорее" in got and meaningful(got["Скорее"][1]):
            value = got["Скорее"][1]
            if refusal(value):
                errors.append("%s: в «Скорее» отказ («%s…»), а нужна одна версия с уверенностью"
                              % (where, value[:40].strip()))
            elif not CONFIDENCE.search(value):
                errors.append("%s: в «Скорее» нет уверенности (низкая / средняя / высокая)" % where)
        if "Что даст ответ" in got and refusal(got["Что даст ответ"][1]):
            errors.append("%s: в «Что даст ответ» отказ, а нужны данные и какой ответ на что укажет" % where)
        if "Где посмотреть" in got and meaningful(got["Где посмотреть"][1]):
            value = got["Где посмотреть"][1]
            for label, pat in RUNGS:
                m = re.search(pat + r"\s*(.*)", value, re.I)
                if not m or not meaningful(m.group(1)):
                    errors.append("%s: в «Где посмотреть» нет ступени «%s —» (если её нет — «нет — почему»)"
                                  % (where, label))
    return n_open, errors


def table_rows(text):
    """(заголовок, строки) первой таблицы, в шапке которой есть «Скорее» или «исход»."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith("|") and re.search(r"исход", line, re.I):
            head = [c.strip() for c in line.strip().strip("|").split("|")]
            rows = []
            for row in lines[i + 2:]:
                if not row.strip().startswith("|"):
                    break
                rows.append([c.strip() for c in row.strip().strip("|").split("|")])
            return head, rows
    return None, []


def check_document(text):
    errors = []
    head, rows = table_rows(text)
    if head is None:
        return ["06-validation.md: нет таблицы утверждений со столбцом исхода"]
    low = [h.lower() for h in head]
    i_out = next((i for i, h in enumerate(low) if "исход" in h), None)
    i_guess = next((i for i, h in enumerate(low) if "скорее" in h), None)
    if i_guess is None:
        return ["06-validation.md: в таблице утверждений нет столбца «Скорее»"]
    for row in rows:
        if i_out is None or i_out >= len(row) or not NO_DATA.search(row[i_out]):
            continue
        name = row[0][:40] if row else "?"
        cell = row[i_guess] if i_guess < len(row) else ""
        if not meaningful(cell):
            errors.append("06-validation.md, «%s»: исход «нет данных», а «Скорее» пусто" % name)
        elif refusal(cell):
            errors.append("06-validation.md, «%s»: в «Скорее» отказ («%s»)" % (name, cell[:40]))
    return errors


def main():
    if len(sys.argv) < 2:
        sys.stderr.write(__doc__)
        return 2
    task = sys.argv[1].rstrip("/")
    val, doc = read(os.path.join(task, "02c-validation.md")), read(os.path.join(task, "06-validation.md"))
    if not val and not doc:
        print("Проверки по сути и документа валидации нет: проверять нечего.")
        return 0
    n_open, errors = check_validation(val) if val else (0, [])
    if doc:
        errors += check_document(doc)
    os.makedirs(os.path.join(task, "checks"), exist_ok=True)
    out = ["# Конкретика по «нет данных»: " + os.path.basename(task), "",
           "Утверждений с исходом «нет данных»: %d" % n_open, "", "## Ошибки"] + (["- " + e for e in errors] or ["- нет"])
    open(os.path.join(task, "checks", "concrete.md"), "w", encoding="utf-8").write("\n".join(out) + "\n")
    for e in errors:
        print("конкретика: " + e)
    if not errors:
        print("Конкретика: утверждений «нет данных» %d, у всех есть догадка и где посмотреть." % n_open)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
