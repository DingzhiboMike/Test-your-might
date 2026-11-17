#!/usr/bin/env python3
"""Гипотезы о процессе (`ПРЕДМЕТ: процесс` в ТЗ): форма генератора и планка проверки по сути — без клиентских рамок.

  python3 scripts/check_process.py tasks/<папка>

Действует только при `ПРЕДМЕТ: процесс` в 00-tz.md; иначе ничего не проверяет.

`02-hypotheses.md` (блоки «### Г-N — …», формат — `.claude/skills/hypothesis-generator/SKILL.md`, `hypothesis-generator/process.md`):
1. Заполнены слоты: Узел, Изменение, Эффект, Ось, Механизм, Цена внедрения, Риск регресса, Опровергнет, Опора.
2. Узел — из списка: постановка, сбор данных, поиск, синтез, проверка, планирование, сдача, координация.
3. Ось — из списка: качество, цена, скорость, надёжность, удобство.
4. Опора начинается со ступени (обзор, сравнение, кейс, практик, вендор) или «нет».
5. Клиентских слотов нет: строки «Субъект:» нет, в «Рамка:» нет push / pull / inertia / anxiety / точки слома.
6. При трёх гипотезах и больше — не больше половины в одном узле и не меньше двух разных осей.

`02c-validation.md` (блоки «ГИПОТЕЗА N — …», `hypothesis-validator/process.md`):
7. У каждого блока строка «Перенос:» со ступенью и условиями «есть / частично / нет».
8. «Держится на бумаге» — только при ступени обзор или сравнение, либо кейс с условиями «есть»; при «практик» и
   «вендор» — не выше «сузить».

Отчёт: tasks/<папка>/checks/process.md. Код возврата 1 — есть ошибки (оркестратор: один перезапрос с отчётом).
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_effort import tz_field  # noqa: E402

SLOTS = ("Узел", "Изменение", "Эффект", "Ось", "Механизм", "Цена внедрения", "Риск регресса", "Опровергнет", "Опора")
NODES = ("постановка", "сбор данных", "поиск", "синтез", "проверка", "планирование", "сдача", "координация")
AXES = ("качество", "цена", "скорость", "надежность", "удобство")
STEPS = ("обзор", "сравнение", "кейс", "практик", "вендор")
CLIENT_FRAMES = re.compile(r"\b(push|pull|inertia|anxiety|точка слома)\b", re.I)
HYP = re.compile(r"(?m)^#{2,4}\s*(Г-\d+)\b")
VAL = re.compile(r"(?m)^\W*(ГИПОТЕЗА\s+\d+)\b")
LINE = re.compile(r"^\s*[-*]?\s*\**\s*([А-ЯЁ][А-Яа-яЁё ]{1,30}?)\s*:\s*\**\s*(.*)$")


def read(path):
    return open(path, encoding="utf-8").read() if os.path.exists(path) else ""


def norm(s):
    return s.replace("ё", "е").replace("Ё", "Е").lower().strip(" *«»\"`.")


def split(text, head):
    heads = list(head.finditer(text))
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        yield m.group(1), text[m.end():end]


def fields(block):
    out = {}
    for line in block.splitlines():
        m = LINE.match(line)
        if m and m.group(1).strip() not in out:
            out[m.group(1).strip()] = m.group(2).strip()
    return out


def first_of(value, options):
    v = norm(value)
    for o in sorted(options, key=len, reverse=True):
        if v.startswith(o):
            return o
    return None


def check_hypotheses(text, errors):
    nodes, axes, n = [], [], 0
    for label, block in split(text, HYP):
        n += 1
        f = fields(block)
        missing = [s for s in SLOTS if not f.get(s, "").strip(" —-–")]
        if missing:
            errors.append("02-hypotheses.md, %s: не заполнено — %s" % (label, ", ".join(missing)))
        node = first_of(f.get("Узел", ""), NODES)
        if f.get("Узел") and not node:
            errors.append("02-hypotheses.md, %s: узел не из списка (%s)" % (label, ", ".join(NODES)))
        axis = first_of(f.get("Ось", ""), AXES)
        if f.get("Ось") and not axis:
            errors.append("02-hypotheses.md, %s: ось не из списка (%s)" % (label, ", ".join(AXES)))
        support = f.get("Опора", "")
        if support and not (first_of(support, STEPS) or norm(support).startswith("нет")):
            errors.append("02-hypotheses.md, %s: опора не начинается со ступени (%s) или «нет»" % (label, ", ".join(STEPS)))
        if "Субъект" in f:
            errors.append("02-hypotheses.md, %s: клиентский слот «Субъект» в гипотезе о процессе" % label)
        if CLIENT_FRAMES.search(f.get("Рамка", "")):
            errors.append("02-hypotheses.md, %s: клиентская рамка в гипотезе о процессе" % label)
        if node:
            nodes.append(node)
        if axis:
            axes.append(axis)
    if n == 0:
        errors.append("02-hypotheses.md: нет блоков «### Г-N — …»")
    if n >= 3:
        top = max((nodes.count(x) for x in set(nodes)), default=0)
        if top * 2 > n:
            errors.append("02-hypotheses.md: %d из %d гипотез в одном узле — больше половины" % (top, n))
        if len(set(axes)) < 2:
            errors.append("02-hypotheses.md: у всех гипотез одна ось — разброса нет")
    return n


def check_validation(text, errors):
    n = 0
    for label, block in split(text, VAL):
        n += 1
        f = fields(block)
        carry = f.get("Перенос", "")
        if not carry:
            errors.append("02c-validation.md, %s: нет строки «Перенос:»" % label)
            continue
        step = None
        m = re.search(r"ступень\s*[—:-]\s*([а-яё]+)", norm(carry))
        if m and m.group(1) in STEPS:
            step = m.group(1)
        cond = re.search(r"условия[^—:-]*[—:-]\s*(есть|частично|нет)", norm(carry))
        if not step:
            errors.append("02c-validation.md, %s: в «Перенос:» нет ступени (%s)" % (label, ", ".join(STEPS)))
        if not cond:
            errors.append("02c-validation.md, %s: в «Перенос:» нет условий «есть / частично / нет»" % label)
        verdict = norm(f.get("Вердикт", ""))
        if verdict.startswith("держится") and step:
            if step in ("практик", "вендор"):
                errors.append("02c-validation.md, %s: «держится на бумаге» при ступени «%s» — не выше «сузить»" % (label, step))
            elif step == "кейс" and (not cond or cond.group(1) != "есть"):
                errors.append("02c-validation.md, %s: «держится на бумаге» при ступени «кейс» без условий переноса «есть»" % label)
    return n


def main():
    if len(sys.argv) < 2:
        sys.stderr.write(__doc__)
        return 2
    task = sys.argv[1].rstrip("/")
    subject = norm(tz_field(read(os.path.join(task, "00-tz.md")), "ПРЕДМЕТ"))
    if not subject.startswith("процесс"):
        print("Предмет не «процесс»: проверять нечего.")
        return 0
    errors, stats = [], []
    hyp = read(os.path.join(task, "02-hypotheses.md"))
    if hyp:
        stats.append("гипотез: %d" % check_hypotheses(hyp, errors))
    val = read(os.path.join(task, "02c-validation.md"))
    if val:
        stats.append("блоков проверки: %d" % check_validation(val, errors))
    lines = ["# Гипотезы о процессе", "", "; ".join(stats) or "файлов гипотез и проверки нет", ""]
    lines += (["Ошибки:"] + ["- " + e for e in errors]) if errors else ["Ошибок нет."]
    os.makedirs(os.path.join(task, "checks"), exist_ok=True)
    open(os.path.join(task, "checks", "process.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print("Гипотезы о процессе: %s" % ("ОШИБКИ (%d)" % len(errors) if errors else "ок"))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
