#!/usr/bin/env python3
"""Проверяет, что документы для людей читаются людьми, а не только системой.

  python3 scripts/check_readable.py tasks/<папка>[/<файл>]

Файлы для людей: 07a-analyst.md, 07b-editor.md, 07c-decisions.md (писатель брифа) и 02e-position.md
(итоговая позиция консультанта) и 06-validation.md (документ валидации), если они есть. Служебный файл 07d-trace.md
не проверяется. В 06-validation.md ссылки на источники [F-id] и [N-id] разрешены — документ должен оставаться
проверяемым, — а слова «гипотеза» и «вердикт» допустимы: это слова человека. Запрещены номера гипотез системы,
коды запросов данных (D-1), имена файлов, ссылки на модули методологии («M1 ·») и остальные слова системы.

В файлах для людей не должно быть:
- номеров гипотез (Г-3, H-2), id источников и чисел ([F-007], [N-012]), имён файлов системы (src-*, 02c-…);
- слов системы: гипотеза, вердикт, слот, развилка, механизм, гигиена, выводимость, GAP, валидатор.

Ещё два документа для людей — с теми же правилами, что 06-validation (слова «гипотеза» и «вердикт» можно, id [F-…]
нельзя), и без внутренних номеров пунктов пути, утверждений, запросов данных и замечаний (П-1, У-2, D-4, С-03):
- 03-backlog.md — бэклог тестов (финиш типа «гипотезы»): в таблице у каждой строки заполнены все девять колонок —
  № (он же приоритет), кому и как найти в данных, что говорим, где и кто, метрика, успех, отсечение, срок и цена,
  что решит;
- 08-handoff.md — сдача для человека, целиком: без слов системы и номеров; раздел «## Что лежит в папке задачи» (таблица
  файлов из handoff_index.py) допускает имена файлов и не входит в число слов. Служебная часть лежит в 08-service.md,
  на языке системы, и не проверяется; раздел «Служебное» внутри 08-handoff.md — ошибка. Лимит слов — по уровню нагрузки
  (быстро, лёгкий 450, рабочий 650, строгий 900; без профиля 900).
Если тип выхода «гипотезы» и есть 02e-position.md, а 03-backlog.md нет — ошибка.

Лимиты: 07a — до 1600 слов и до 10 задач, 07b — до 1600 слов, 07c — до 500 слов и до 10 пунктов,
02e — до 450 слов, 06-validation — до 5000 слов, 03-backlog — до 1500 слов и до ЁМКОСТЬ + 1 тестов (строка ЁМКОСТЬ в ТЗ; нет строки — до 12), 08-handoff (часть для
человека) — до 900 слов.
Каждая цитата «…» длиннее 20 знаков в 07b должна дословно стоять в 07d-trace.md (там её проверяет check_quotes).

Отчёт: tasks/<папка>/checks/readable.md. Код возврата 1 — есть ошибки. Нет ни одного файла — код 0.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_effort import capacity  # noqa: E402

FILES = ("07a-analyst.md", "07b-editor.md", "07c-decisions.md")
POSITION = "02e-position.md"
VALIDATION = "06-validation.md"
BACKLOG = "03-backlog.md"
HANDOFF = "08-handoff.md"
LIGHT = (VALIDATION, BACKLOG, HANDOFF)
INTERNAL = re.compile(r"(?<![А-Яа-яA-Za-z])[ПУСD]-\d+\b")
JARGON_VALIDATION = re.compile(r"слот\w*|развилк|гигиен|выводимост|\bGAP\b|валидатор|\bM\d{1,2}\s*·|\bD-\d+\b|рамк[аиуе]\b", re.I)
LIMITS = {"07a-analyst.md": 1600, "07b-editor.md": 1600, "07c-decisions.md": 500, POSITION: 450, VALIDATION: 5000,
          BACKLOG: 1500, HANDOFF: 900}
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


INDEX_HEAD = re.compile(r"^##\s+Что лежит в папке задачи\s*$", re.M)
LEVEL_LIMITS = {"light": 450, "work": 650, "strict": 900}  # слов в сдаче для человека по уровню нагрузки


def strip_index(text):
    """Раздел «Что лежит в папке задачи» не проверяется на имена файлов и не входит в число слов."""
    m = INDEX_HEAD.search(text)
    if not m:
        return text
    rest = text[m.end():]
    nxt = re.search(r"^##\s+", rest, re.M)
    return text[:m.start()] + (rest[nxt.start():] if nxt else "")


def handoff_limit(task):
    try:
        import profile_lib
        if profile_lib.has_profile(task):
            return LEVEL_LIMITS.get(profile_lib.load(task)["level"], LIMITS[HANDOFF])
    except ImportError:
        pass
    return LIMITS[HANDOFF]


def human_part(f, text):
    if f != HANDOFF:
        return text
    m = re.search(r"^#+\s*Служебное", text, re.M)
    return strip_index(text[:m.start()] if m else text)


def backlog_rows(text):
    rows = []
    for line in text.splitlines():
        if not line.strip().startswith("|") or re.match(r"^\|[\s:|-]+\|?$", line.strip()):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells and re.match(r"^\d+$", cells[0]):
            rows.append(cells)
    return rows


def main():
    if len(sys.argv) < 2:
        sys.stderr.write(__doc__)
        return 2
    arg = sys.argv[1].rstrip("/")
    only = None  # проверка одного файла: check_readable.py tasks/<папка>/08-handoff.md
    if os.path.isfile(arg):
        only, arg = os.path.basename(arg), os.path.dirname(arg) or "."
    task = arg
    present = [f for f in FILES if os.path.exists(os.path.join(task, f)) and (only is None or f == only)]
    errors = []
    briefs_needed = bool(present)
    if not present:
        tz = read(os.path.join(task, "00-tz.md"))
        brief_type = re.search(r"ТИП ВЫХОДА\W*ТЗ на доработку", tz, re.I)
        other = sorted(f for f in os.listdir(task) if re.match(r"07.*\.md$", f) and f != "07d-trace.md")
        briefs_needed = bool(brief_type or other)
        if other:
            errors.append("брифы лежат под чужим именем (%s): нужны 07a-analyst.md, 07b-editor.md, 07c-decisions.md, 07d-trace.md" % ", ".join(other))
    has_position = os.path.exists(os.path.join(task, POSITION)) and only in (None, POSITION)
    has_validation = os.path.exists(os.path.join(task, VALIDATION)) and only in (None, VALIDATION)
    extra = [f for f in (BACKLOG, HANDOFF) if os.path.exists(os.path.join(task, f)) and only in (None, f)]
    tz_text = read(os.path.join(task, "00-tz.md"))
    if has_position and BACKLOG not in extra and re.search(r"ТИП ВЫХОДА\W*гипотезы", tz_text, re.I):
        errors.append("%s: файла нет — финиш типа «гипотезы» без бэклога тестов" % BACKLOG)
    if not briefs_needed and not has_position and not has_validation and not extra:
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
    if HANDOFF in extra:
        hand_raw = read(os.path.join(task, HANDOFF))
        if re.search(r"^#+\s*Служебное", hand_raw, re.M):
            errors.append("%s: служебная часть сдачи лежит в отдельном файле 08-service.md, а не в этом файле" % HANDOFF)
        if not INDEX_HEAD.search(hand_raw):
            errors.append("%s: нет раздела «Что лежит в папке задачи» со списком файлов (scripts/handoff_index.py)" % HANDOFF)
        if not os.path.exists(os.path.join(task, "08-service.md")):
            errors.append("%s: нет файла 08-service.md — служебная часть сдачи (путь, чек-лист, расход, замечания)" % HANDOFF)
    for f in present + ([POSITION] if has_position else []) + ([VALIDATION] if has_validation else []) + extra:
        text = human_part(f, read(os.path.join(task, f)))
        for i, line in enumerate(text.splitlines(), 1):
            for label, rx in ID_PATTERNS:
                if f == VALIDATION and label == "id источника или числа":
                    continue
                if rx.search(line):
                    errors.append("%s:%d — %s" % (f, i, label))
            if f in (BACKLOG, HANDOFF) and INTERNAL.search(line):
                errors.append("%s:%d — внутренний номер «%s»: назови словами" % (f, i, INTERNAL.search(line).group(0)))
            m = (JARGON_VALIDATION if f in LIGHT else JARGON).search(line)
            if m:
                errors.append("%s:%d — слово системы «%s»" % (f, i, m.group(0).lower()))
        words = len(re.findall(r"\w+", text))
        limit_f = handoff_limit(task) if f == HANDOFF else LIMITS[f]
        if words > limit_f:
            errors.append("%s: %d слов при лимите %d — сократи не менее чем на %d" % (f, words, limit_f, words - limit_f))
        items = len(re.findall(r"^(?:##\s+\d+\.|\d+\.\s)", text, re.M))
        if f in ("07a-analyst.md", "07c-decisions.md") and items > 10:
            errors.append("%s: %d пунктов при лимите 10" % (f, items))
        if f == BACKLOG:
            rows = backlog_rows(text)
            if not rows:
                errors.append("%s: нет таблицы тестов (строки, начинающиеся с номера)" % f)
            cap = capacity(open(os.path.join(task, "00-tz.md"), encoding="utf-8").read()
                           if os.path.exists(os.path.join(task, "00-tz.md")) else "")
            limit = 12 if cap is None else cap + 1
            if len(rows) > limit:
                errors.append("%s: %d тестов при лимите %d%s — остальные кандидаты одной строкой «В очереди»" % (
                    f, len(rows), limit, "" if cap is None else " (ёмкость %d + 1)" % cap))
            for r in rows:
                if len(r) < 9 or any(not c.strip(" —-–") for c in r[:9]):
                    errors.append("%s: тест %s — не заполнены все колонки (кому, что говорим, где, метрика, "
                                  "успех, отсечение, срок и цена, что решит)" % (f, r[0]))
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
