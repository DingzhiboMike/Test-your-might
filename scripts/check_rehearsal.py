#!/usr/bin/env python3
"""Проверяет, что пробный прогон на синтетике родил следствия, а не ушёл в приложение.

  python3 scripts/check_rehearsal.py tasks/<папка> [--rehearsal-only]

1. В `03c-rehearsal.md` есть раздел «СЛЕДСТВИЯ» с частями «Для эксперимента», «Для решения», «Что подсказали персоны».
   Две последние не пустые.
2. В «Для эксперимента» — строка «Строка N — статус: …» (или «Карточка <название> — статус: …») со статусом
   «как есть», «после правки» или «не запускать». Если есть `03-backlog.md` — статус есть у каждой его строки.
3. Без `--rehearsal-only`: в `03-backlog.md` (или `03-plan.md`, если бэклога нет) есть блок «ПО ПРОБНОМУ ПРОГОНУ»,
   и на каждое следствие со статусом не «как есть» там ответ «применено», «человеку» или «отклонено» с текстом
   после двоеточия.

Вместо текста — блоки данных «следствия» и «по_пробному_прогону» (data_block.py): проверяются по схеме.

Ключ `--rehearsal-only` — сразу после прогона, до исправления бэклога. Ошибка — код возврата 1.
Отчёт: tasks/<папка>/checks/rehearsal.md. Нет `03c-rehearsal.md` — проверять нечего (код 0).
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_readable import backlog_rows  # noqa: E402
import data_block  # noqa: E402

UNIT = re.compile(r"^\s*[-*]?\s*\**(Строка\s+\d+|Карточка\s+[^—:\n]+?)\**\s*[—:-]\s*(?:статус\s*:\s*)?(.*)$", re.I | re.M)
STATUS = re.compile(r"как есть|после правки|не запускать", re.I)
ANSWER = re.compile(r"^(применено|человеку|отклонено)\s*:\s*(.+)$", re.I)


def read(path):
    return open(path, encoding="utf-8").read() if os.path.exists(path) else ""


def part(text, title, stops):
    m = re.search(r"^#{0,4}\s*%s\b.*$" % title, text, re.M | re.I)
    if not m:
        return None
    rest = text[m.end():]
    stop = re.search(r"^#{0,4}\s*(%s)\b" % "|".join(stops), rest, re.M | re.I)
    return rest[:stop.start()] if stop else rest


def key(unit):
    return re.sub(r"\s+", " ", unit.strip().lower())


def check(task, rehearsal_only):
    reh = read(os.path.join(task, "03c-rehearsal.md"))
    if not reh:
        return None, []
    errors = []
    canon, block_errors = data_block.canonical(reh, "следствия")
    errors += block_errors
    if canon is not None:
        reh = canon
    m = re.search(r"^#{0,3}\s*СЛЕДСТВИЯ\s*$", reh, re.M)
    if not m:
        return {}, ["нет раздела «СЛЕДСТВИЯ»: прогон не сказал, что он меняет в эксперименте и решении"]
    body = reh[m.end():]
    body = body[:re.search(r"^#{1,2}\s(?!#)", body, re.M).start()] if re.search(r"^#{1,2}\s(?!#)", body, re.M) else body
    names = ("Для эксперимента", "Для решения", "Что подсказали персоны")
    parts = {n: part(body, n, [x for x in names if x != n] + ["Приложение"]) for n in names}
    for n in names:
        if parts[n] is None:
            errors.append("СЛЕДСТВИЯ: нет части «%s»" % n)
    for n in names[1:]:
        if parts[n] is not None and len(re.sub(r"\s+", "", parts[n])) < 15:
            errors.append("СЛЕДСТВИЯ: часть «%s» пустая" % n)

    units = {}
    for um in UNIT.finditer(parts["Для эксперимента"] or ""):
        st = STATUS.search(um.group(2))
        if not st:
            errors.append("%s: нет статуса — «как есть», «после правки» или «не запускать»" % um.group(1).strip())
            continue
        units[key(um.group(1))] = (um.group(1).strip(), st.group(0).lower())
    if parts["Для эксперимента"] is not None and not units:
        errors.append("СЛЕДСТВИЯ: в «Для эксперимента» нет ни одного теста со статусом")

    backlog = read(os.path.join(task, "03-backlog.md"))
    for row in backlog_rows(backlog):
        if "строка %s" % row[0] not in units:
            errors.append("Строка %s бэклога: у пробного прогона нет статуса по ней" % row[0])

    if not rehearsal_only:
        target_name = "03-backlog.md" if backlog else "03-plan.md"
        target = backlog or read(os.path.join(task, target_name))
        canon, block_errors = data_block.canonical(target, "по_пробному_прогону")
        errors += ["%s: %s" % (target_name, e) for e in block_errors]
        if canon is not None:
            target = canon
        block = part(target, r"ПО ПРОБНОМУ ПРОГОНУ", ["ПО ПРОВЕРКЕ СМЫСЛА", "Чего этот"]) if target else None
        pending = [(lab, st) for lab, st in units.values() if st != "как есть"]
        if pending and block is None:
            errors.append("%s: нет блока «ПО ПРОБНОМУ ПРОГОНУ» — следствия прогона не применены" % target_name)
        elif pending:
            answers = {}
            for am in UNIT.finditer(block):
                a = ANSWER.match(am.group(2).strip())
                if a:
                    answers[key(am.group(1))] = a
            for lab, st in pending:
                if key(lab) not in answers:
                    errors.append("%s (%s): в «ПО ПРОБНОМУ ПРОГОНУ» нет ответа на следствие" % (lab, st))
    return units, errors


def main():
    if len(sys.argv) < 2:
        sys.stderr.write(__doc__)
        return 2
    task = sys.argv[1].rstrip("/")
    units, errors = check(task, "--rehearsal-only" in sys.argv[2:])
    if units is None:
        print("Пробного прогона нет: проверять нечего.")
        return 0
    counts = {}
    for _, st in units.values():
        counts[st] = counts.get(st, 0) + 1
    summary = ", ".join("%s — %d" % (k, v) for k, v in sorted(counts.items())) or "статусов нет"
    os.makedirs(os.path.join(task, "checks"), exist_ok=True)
    out = ["# Пробный прогон: " + os.path.basename(task), "", "Тестов со статусом: %d (%s)" % (len(units), summary), "",
           "## Ошибки"] + (["- " + e for e in errors] or ["- нет"])
    open(os.path.join(task, "checks", "rehearsal.md"), "w", encoding="utf-8").write("\n".join(out) + "\n")
    for e in errors:
        print("пробный прогон: " + e)
    if not errors:
        print("Пробный прогон: тестов %d (%s), ошибок нет." % (len(units), summary))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
