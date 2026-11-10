#!/usr/bin/env python3
"""Реестр находок: ключевая находка разбора материалов не теряется по дороге к сдаче.

  python3 scripts/check_carry.py tasks/<папка>

Находки — строки таблицы «КЛЮЧЕВЫЕ НАХОДКИ» в `00k-knowledge.md`: | Н-01 | находка | «опора» [F-id] | чем ключевая |.
Нет таблицы — проверять нечего (код 0). Проверяется только то, для чего уже есть файл:

1. Таблица: номера не повторяются, строк не больше 12, в каждой строке есть опора «…» [F-id] и причина, чем ключевая.
2. `00a-audit.md` (аудит находок до генерации): у каждой находки строка `Н-01 | выжила | основание`,
   `Н-02 | исправлена | было → стало; основание` или `Н-03 | снята | причина`. Находки вне реестра — ошибка.
3. `02-hypotheses.md` при наличии аудита: у гипотез есть слот «Стоит на:» с номерами находок или «вне находок»;
   гипотеза на снятой находке или на номере, которого нет в реестре, — ошибка.
4. `08-handoff.md` написан: в `08-service.md` раздел «Судьба находок» — по строке на находку:
   | Н-01 | в сдаче | «дословная фраза из 08-handoff.md» | или | Н-03 | снята | причина |.
   Фраза сверяется с текстом сдачи без учёта регистра, ё/е, кавычек и пробелов.

Скрипт сверяет форму: дошла ли находка до сдачи по смыслу, видит проверка смысла и человек.
Отчёт: tasks/<папка>/checks/carry.md. Код возврата 1 — есть ошибки.
"""
import os
import re
import sys

ROW_RE = re.compile(r"^\|\s*(Н-\d{2,})\s*\|(.*)\|\s*$", re.M)
AUDIT_RE = re.compile(r"^\W*(Н-\d{2,})\s*\|\s*([А-Яа-яё]+)\s*\|(.*)$", re.M)
STAND_RE = re.compile(r"^\W*Стоит на:\s*(.*)$", re.M)
ID_RE = re.compile(r"Н-\d{2,}")
QUOTE_RE = re.compile(r"«([^«»]{3,})»")
STATUSES = ("выжила", "исправлена", "снята")
MAX_ROWS = 12


def read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def norm(s):
    s = s.lower().replace("ё", "е")
    s = re.sub(r"[\"'“”„«»`*_]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def cells(rest):
    return [c.strip() for c in rest.split("|")]


def findings(task):
    """[(номер, [ячейки после номера])] из 00k-knowledge.md."""
    return [(m.group(1), cells(m.group(2))) for m in ROW_RE.finditer(read(os.path.join(task, "00k-knowledge.md")))]


def section(text, title):
    m = re.search(r"^##\s*" + re.escape(title) + r"\s*$(.*?)(?=^##\s|\Z)", text, re.M | re.S)
    return m.group(1) if m else None


def main():
    if len(sys.argv) < 2 or sys.argv[1].startswith("-"):
        sys.stderr.write(__doc__)
        return 2
    task = sys.argv[1].rstrip("/")
    rows = findings(task)
    if not rows:
        print("Реестра находок нет: проверять нечего.")
        return 0
    errors, notes = [], []
    ids = [i for i, _ in rows]
    for i in sorted(set(x for x in ids if ids.count(x) > 1)):
        errors.append("00k-knowledge.md: номер %s повторяется" % i)
    if len(rows) > MAX_ROWS:
        errors.append("00k-knowledge.md: находок %d, допустимо не больше %d" % (len(rows), MAX_ROWS))
    for i, c in rows:
        if len(c) < 3 or not c[0]:
            errors.append("00k-knowledge.md, %s: в строке меньше трёх ячеек после номера или пустая находка" % i)
            continue
        if not re.search(r"«[^«»]{3,}»[\s|—–:,;()]{0,8}\[F-\d{3,}\]", c[1]):
            errors.append("00k-knowledge.md, %s: в ячейке «Опора» нет дословного фрагмента с id источника" % i)
        if not c[2]:
            errors.append("00k-knowledge.md, %s: не сказано, чем находка ключевая" % i)
    known = set(ids)

    audit = read(os.path.join(task, "00a-audit.md"))
    status = {}
    if audit:
        for m in AUDIT_RE.finditer(audit):
            i, st, rest = m.group(1), m.group(2).lower().replace("ё", "е"), m.group(3).strip()
            if i not in known:
                errors.append("00a-audit.md: %s нет в реестре находок" % i)
                continue
            if st not in STATUSES:
                errors.append("00a-audit.md, %s: статус «%s», допустимо: %s" % (i, st, ", ".join(STATUSES)))
                continue
            if len(rest) < 10:
                errors.append("00a-audit.md, %s: нет основания статуса" % i)
            if st == "исправлена" and "→" not in rest:
                errors.append("00a-audit.md, %s: у исправленной находки нет «было → стало»" % i)
            status[i] = st
        for i in ids:
            if i not in status and not any(e.startswith("00a-audit.md, %s:" % i) for e in errors):
                errors.append("00a-audit.md: у находки %s нет строки со статусом" % i)
        notes.append("аудит: выжило %d, исправлено %d, снято %d" % tuple(
            sum(1 for s in status.values() if s == k) for k in STATUSES))

    hyp = read(os.path.join(task, "02-hypotheses.md"))
    if audit and hyp:
        slots = STAND_RE.findall(hyp)
        if not slots:
            errors.append("02-hypotheses.md: ни у одной гипотезы нет слота «Стоит на:»")
        for s in slots:
            refs = ID_RE.findall(s)
            if not refs and "вне находок" not in s.lower():
                errors.append("02-hypotheses.md: слот «Стоит на: %s» — ни номера находки, ни «вне находок»" % s.strip()[:60])
            for r in refs:
                if r not in known:
                    errors.append("02-hypotheses.md: гипотеза стоит на %s, такой находки нет в реестре" % r)
                elif status.get(r) == "снята":
                    errors.append("02-hypotheses.md: гипотеза стоит на находке %s, снятой аудитом" % r)
        notes.append("гипотез со слотом «Стоит на» — %d" % len(slots))

    hand = read(os.path.join(task, "08-handoff.md"))
    if not hand:
        notes.append("судьба находок: сдачи ещё нет, не проверялась")
    else:
        sec = section(read(os.path.join(task, "08-service.md")), "Судьба находок")
        if sec is None:
            errors.append("08-service.md: нет раздела «Судьба находок» при %d находках в реестре" % len(rows))
        else:
            fate, hn = {}, norm(hand)
            for m in ROW_RE.finditer(sec):
                i, c = m.group(1), cells(m.group(2))
                if i not in known:
                    errors.append("08-service.md, судьба находок: %s нет в реестре" % i)
                    continue
                kind = norm(c[0]) if c else ""
                where = c[1] if len(c) > 1 else ""
                fate[i] = kind
                if kind == "в сдаче":
                    qs = QUOTE_RE.findall(where)
                    if not qs:
                        errors.append("08-service.md, %s: «в сдаче» без дословной фразы из 08-handoff.md в ёлочках" % i)
                    elif not any(norm(q) in hn for q in qs):
                        errors.append("08-service.md, %s: фразы «%s» нет в 08-handoff.md" % (i, qs[0][:60]))
                elif kind == "снята":
                    if len(where) < 15:
                        errors.append("08-service.md, %s: снята без причины" % i)
                else:
                    errors.append("08-service.md, %s: судьба «%s», допустимо: в сдаче, снята" % (i, c[0] if c else ""))
            for i in ids:
                if i not in fate:
                    errors.append("08-service.md, судьба находок: нет строки для %s" % i)
            notes.append("судьба: в сдаче %d, снято %d из %d" % (
                sum(1 for v in fate.values() if v == "в сдаче"), sum(1 for v in fate.values() if v == "снята"), len(rows)))

    out = ["# Реестр находок: " + os.path.basename(task), "", "Находок: %d." % len(rows)]
    out += ["- " + n for n in notes]
    out += ["- ОШИБКА " + e for e in errors]
    out += ["", "Итог: ошибок нет." if not errors else "Итог: ошибок %d." % len(errors)]
    report = "\n".join(out) + "\n"
    os.makedirs(os.path.join(task, "checks"), exist_ok=True)
    with open(os.path.join(task, "checks", "carry.md"), "w", encoding="utf-8") as f:
        f.write(report)
    sys.stdout.write(report)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
