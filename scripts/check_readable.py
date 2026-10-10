#!/usr/bin/env python3
"""Проверяет, что документы для людей читаются людьми, а не только системой.

  python3 scripts/check_readable.py tasks/<папка>

Файлы для людей: 07a-analyst.md, 07b-editor.md, 07c-decisions.md (писатель брифа) и 02e-position.md
(итоговая позиция консультанта) и 06-validation.md (документ валидации), если они есть. Служебный файл 07d-trace.md
не проверяется. В 06-validation.md ссылки на источники [F-id] и [N-id] разрешены — документ должен оставаться
проверяемым, — а слова «гипотеза» и «вердикт» допустимы: это слова человека. Запрещены номера гипотез системы,
коды запросов данных (D-1), имена файлов, ссылки на модули курса («M1 ·») и остальные слова системы.

В файлах для людей не должно быть:
- номеров гипотез (Г-3, H-2), id источников и чисел ([F-007], [N-012]), имён файлов системы (src-*, 02c-…);
- слов системы: гипотеза, вердикт, слот, развилка, механизм, гигиена, выводимость, GAP, валидатор.

Лимиты: 07a — до 1600 слов и до 10 задач, 07b — до 1600 слов, 07c — до 500 слов и до 10 пунктов,
02e — до 450 слов, 06-validation — до 5000 слов.
Каждая цитата «…» длиннее 20 знаков в 07b должна дословно стоять в 07d-trace.md (там её проверяет check_quotes).

Отчёт: tasks/<папка>/checks/readable.md. Код возврата 1 — есть ошибки. Нет ни одного файла — код 0.
"""
import os
import re
import sys

FILES = ("07a-analyst.md", "07b-editor.md", "07c-decisions.md")
POSITION = "02e-position.md"
VALIDATION = "06-validation.md"
JARGON_VALIDATION = re.compile(r"слот\w*|развилк|гигиен|выводимост|\bGAP\b|валидатор|\bM\d{1,2}\s*·|\bD-\d+\b|рамк[аиуе]\b", re.I)
LIMITS = {"07a-analyst.md": 1600, "07b-editor.md": 1600, "07c-decisions.md": 500, POSITION: 450, VALIDATION: 5000}
ID_PATTERNS = [
    ("номер гипотезы", re.compile(r"(?<![А-Яа-яA-Za-z])[ГгHh]-\d+[a-zа-я]?\b")),
    ("id источника или числа", re.compile(r"\[(?:F|N)-\d+\]")),
    ("имя файла системы", re.compile(r"\b(?:src-[\w-]+|0\d[a-z]?-[\w-]+\.md|00r-[\w-]+|sources\.csv|numbers\.csv)\b")),
]
JARGON = re.compile(r"гипотез|вердикт|слот\w*|развилк|механизм|гигиен|выводимост|\bGAP\b|валидатор", re.I)


def norm(s):
    return re.sub(r"\s+", " ", s.replace("ё", "е").replace("Ё", "Е")).strip().lower()


def read(path):
    return open(path, encoding="utf-8").read() if os.path.exists(path) else ""


def main():
    if len(sys.argv) < 2:
        sys.stderr.write(__doc__)
        return 2
    task = sys.argv[1].rstrip("/")
    present = [f for f in FILES if os.path.exists(os.path.join(task, f))]
    errors = []
    briefs_needed = bool(present)
    if not present:
        tz = read(os.path.join(task, "00-tz.md"))
        brief_type = re.search(r"ТИП ВЫХОДА\W*ТЗ на доработку", tz, re.I)
        other = sorted(f for f in os.listdir(task) if re.match(r"07.*\.md$", f) and f != "07d-trace.md")
        briefs_needed = bool(brief_type or other)
        if other:
            errors.append("брифы лежат под чужим именем (%s): нужны 07a-analyst.md, 07b-editor.md, 07c-decisions.md, 07d-trace.md" % ", ".join(other))
    has_position = os.path.exists(os.path.join(task, POSITION))
    has_validation = os.path.exists(os.path.join(task, VALIDATION))
    if not briefs_needed and not has_position and not has_validation:
        print("Документов для людей нет: проверять нечего.")
        return 0
    trace = ""
    if briefs_needed:
        for f in FILES:
            if f not in present:
                errors.append("%s: файла нет" % f)
        trace = norm(read(os.path.join(task, "07d-trace.md")))
        if not trace:
            errors.append("07d-trace.md: служебного файла нет, цитаты не сверить")
    for f in present + ([POSITION] if has_position else []) + ([VALIDATION] if has_validation else []):
        text = read(os.path.join(task, f))
        for i, line in enumerate(text.splitlines(), 1):
            for label, rx in ID_PATTERNS:
                if f == VALIDATION and label == "id источника или числа":
                    continue
                if rx.search(line):
                    errors.append("%s:%d — %s" % (f, i, label))
            m = (JARGON_VALIDATION if f == VALIDATION else JARGON).search(line)
            if m:
                errors.append("%s:%d — слово системы «%s»" % (f, i, m.group(0).lower()))
        words = len(re.findall(r"\w+", text))
        if words > LIMITS[f]:
            errors.append("%s: %d слов при лимите %d — сократи" % (f, words, LIMITS[f]))
        items = len(re.findall(r"^(?:##\s+\d+\.|\d+\.\s)", text, re.M))
        if f in ("07a-analyst.md", "07c-decisions.md") and items > 10:
            errors.append("%s: %d пунктов при лимите 10" % (f, items))
        if f == "07b-editor.md":
            for q in re.findall(r"«([^»]{20,})»", text):
                if norm(q) not in trace:
                    errors.append("07b-editor.md: цитаты нет в 07d-trace.md дословно: «%s…»" % q[:40])

    os.makedirs(os.path.join(task, "checks"), exist_ok=True)
    out = ["# Читаемость документов для людей: " + os.path.basename(task), "", "## Ошибки"]
    out += ["- " + e for e in errors] or ["- нет"]
    open(os.path.join(task, "checks", "readable.md"), "w", encoding="utf-8").write("\n".join(out) + "\n")
    for e in errors:
        print("читаемость: " + e)
    if not errors:
        print("Читаемость: ошибок нет.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
