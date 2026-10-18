#!/usr/bin/env python3
"""Проверяет форму выхода Нострадамуса: «мало данных» не принимается как ответ.

  python3 scripts/check_forecast.py tasks/<папка>

Сверяет `02f-forecast.md` с ТЗ:
1. Есть блок РАМКА с полями «Вопрос человека», «Нужная форма ответа», «Совпадает: да / нет». При «нет» —
   непустой «Черновик ответа нужной формы».
2. Раздел «## GAP k» есть по каждому пункту GAP с пометкой [ключевой] и по GAP 1. В каждом непустые
   «Лучшая версия» (с пометкой «оценка» в строке), «Уверенность», «Альтернативы» (хотя бы один пункт),
   «Что различит», «Следующий шаг», «Если версия неверна».
3. Лучшая версия — не отказ от ответа: «нет данных», «недостаточно информации», «требуется исследование»,
   «невозможно определить» в её начале — ошибка. Это строка для «Что различит», а не версия.
4. В разделе «НОВЫЕ ИДЕИ» не меньше пяти пунктов, и у каждого непустые «не повторяет: …» (чем отличается от проверенного),
   «уточнит: …» (какие данные или наблюдение уточнят идею), «первый шаг: …» и «на чём: …» — поле или признак из источника
   дословно с id («…» [F-id]; что слово действительно есть в источнике, сверяет check_quotes.py) или «новый сбор: …».
   Идея без следствия — пожелание; шаг по полю, которого нет в источнике, — невыполним.
5. Первая строка «РЕЖИМ:» — «только версии» или «версии и новые идеи» — и она совпадает с условием: новые идеи нужны,
   если в ТЗ РЕЖИМ «новые идеи: да» или все итоговые вердикты «сузить / не держится» (check_effort.ideas_required).
   В режиме «только версии» раздела «НОВЫЕ ИДЕИ» нет, и пункт 4 не проверяется.

Цитаты в файле проверяет `check_quotes.py`, как в любом артефакте. Ошибка — код возврата 1.
Отчёт: tasks/<папка>/checks/forecast.md. Нет `02f-forecast.md` — проверять нечего (код 0); есть ли он на финише,
сверяет чек-лист готовности.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_path import gap_items  # noqa: E402
from check_effort import all_narrowed, ideas_ordered  # noqa: E402

FIELDS = ("Лучшая версия", "Уверенность", "На чём стоит", "Альтернативы", "Что различит", "Следующий шаг",
          "Если версия неверна")
REQUIRED = ("Лучшая версия", "Уверенность", "Альтернативы", "Что различит", "Следующий шаг", "Если версия неверна")
FRAME_FIELDS = ("Вопрос человека", "Нужная форма ответа", "Что построено", "Совпадает", "Черновик ответа нужной формы")
REFUSAL = re.compile(r"^\W*(нет данных|данных нет|данных недостаточно|недостаточно (данных|информации|опор)|"
                     r"невозможно|нельзя (сказать|определить|выбрать)|не определ\w*|требует\w* (исследован|данн)|"
                     r"нужн[ыо]? (данные|исследование|выгрузк)|зависит от|пока неясно|неизвестно)", re.I)


def read(path):
    return open(path, encoding="utf-8").read() if os.path.exists(path) else ""


def key_gaps(tz):
    """Номера ключевых пунктов GAP и всегда GAP 1 — вопрос человека."""
    items = gap_items(tz)
    keys = {n for n, t in items.items() if "[ключевой]" in t}
    if 1 in items:
        keys.add(1)
    return keys


def fields(block, names):
    """{поле: (строка-заголовок, значение)} — значение до следующего поля из names или заголовка раздела."""
    label = re.compile(r"^\s*(%s)\b([^:\n]*):[ \t]*(.*)$" % "|".join(re.escape(n) for n in names), re.I | re.M)
    out, marks = {}, list(label.finditer(block))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(block)
        nxt = re.search(r"^#{1,3}\s|^[А-ЯЁ][А-ЯЁ ]{4,}$", block[m.end():end], re.M)
        if nxt:
            end = m.end() + nxt.start()
        value = (m.group(3) + "\n" + block[m.end():end]).strip()
        name = next(n for n in names if n.lower() == m.group(1).lower())
        out.setdefault(name, (m.group(0), value))
    return out


def meaningful(v):
    return len(re.sub(r"[\s\-—–.:;,()<>]+", "", v)) >= 3


def gap_sections(text):
    """{номер: текст раздела «## GAP k»}."""
    heads = list(re.finditer(r"^#{1,3}\s*GAP\s+(\d+)\b.*$", text, re.M))
    out = {}
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        tail = re.search(r"^#{1,3}\s*НОВЫЕ ИДЕИ|^#{0,3}\s*РАМКА\b", text[m.end():end], re.M | re.I)
        if tail:
            end = m.end() + tail.start()
        out.setdefault(int(m.group(1)), text[m.end():end])
    return out


def check(task):
    fc = read(os.path.join(task, "02f-forecast.md"))
    if not fc:
        return None, [], 0
    errors = []

    m = re.search(r"^#{0,3}\s*РАМКА\b", fc, re.M)
    if not m:
        errors.append("нет блока «РАМКА»: не сверено, в той ли форме ответ на вопрос человека")
    else:
        stop = re.search(r"^#{1,3}\s*GAP\s+\d+", fc[m.end():], re.M)
        frame = fields(fc[m.end():m.end() + stop.start()] if stop else fc[m.end():], FRAME_FIELDS)
        for f in ("Вопрос человека", "Нужная форма ответа", "Совпадает"):
            if f not in frame or not meaningful(frame[f][1]):
                errors.append("РАМКА: пустое поле «%s»" % f)
        same = frame.get("Совпадает", ("", ""))[1].lower()
        if re.match(r"\W*нет\b", same):
            draft = frame.get("Черновик ответа нужной формы", ("", ""))[1]
            if len(draft) < 40:
                errors.append("РАМКА: форма не совпала, а черновика ответа нужной формы нет — его и ждёт человек")
        elif same and not re.match(r"\W*да\b", same):
            errors.append("РАМКА: в «Совпадает» нет ни «да», ни «нет»")

    sections = gap_sections(fc)
    keys = sorted(key_gaps(read(os.path.join(task, "00-tz.md"))))
    for n in keys:
        if n not in sections:
            errors.append("GAP %d: нет раздела — ключевой вопрос остался без лучшей версии" % n)
            continue
        got = fields(sections[n], FIELDS)
        for f in REQUIRED:
            if f not in got or not meaningful(got[f][1]):
                errors.append("GAP %d: пустое поле «%s»" % (n, f))
        if "Лучшая версия" in got:
            line, value = got["Лучшая версия"]
            if "оценк" not in line.lower() and "оценк" not in value[:200].lower():
                errors.append("GAP %d: лучшая версия без пометки «оценка»" % n)
            if REFUSAL.match(re.sub(r"\[оценка\]", "", value, flags=re.I)):
                errors.append("GAP %d: вместо лучшей версии — отказ («%s…»); нехватка данных идёт в «Что различит», "
                              "версия всё равно нужна" % (n, value[:40].strip()))
        if "Альтернативы" in got and not re.search(r"^\s*[-—•*]\s*\S|^\s*\d+[.)]\s*\S", got["Альтернативы"][1], re.M):
            if len(got["Альтернативы"][1]) < 20:
                errors.append("GAP %d: в «Альтернативы» нет ни одной версии" % n)

    more = re.search(r"^#{0,3}\s*НОВЫЕ ИДЕИ\b.*$", fc, re.M | re.I)
    moves = 0
    mode = re.search(r"^\s*РЕЖИМ\s*:\s*(.*)$", fc, re.M)
    with_ideas = bool(mode) and "иде" in mode.group(1).lower()
    tz = read(os.path.join(task, "00-tz.md"))
    need = ideas_ordered(tz) or all_narrowed(task)
    if not mode:
        errors.append("нет строки «РЕЖИМ:» — «только версии» или «версии и новые идеи»")
    elif with_ideas and not need:
        errors.append("РЕЖИМ: новые идеи не заказаны в ТЗ, а итоговые вердикты не все «сузить / не держится»")
    elif not with_ideas and need:
        errors.append("РЕЖИМ: «только версии», а новые идеи нужны — %s" % (
            "заказаны в ТЗ" if ideas_ordered(tz) else "все итоговые вердикты «сузить / не держится»"))
    if not with_ideas:
        if more:
            errors.append("раздел «НОВЫЕ ИДЕИ» в режиме «только версии»")
    elif not more:
        errors.append("нет раздела «НОВЫЕ ИДЕИ» — главного выхода режима с новыми идеями")
    else:
        body = fc[more.end():]
        stop = re.search(r"^#{1,3}\s|^РАМКА\b", body, re.M)
        body = body[:stop.start()] if stop else body
        starts = list(re.finditer(r"^(\d+)[.)]\s*\S", body, re.M))
        moves = len(starts)
        if moves < 5:
            errors.append("«НОВЫЕ ИДЕИ»: идей %d, нужно не меньше пяти" % moves)
        need = (("не повтор", "не повторяет", "чем отличается от проверенного"),
                ("уточн", "уточнит", "какие данные или наблюдение уточнят идею"),
                ("первый шаг", "первый шаг", "что сделать на этой неделе"))
        for i, m in enumerate(starts):
            item = body[m.start():starts[i + 1].start() if i + 1 < len(starts) else len(body)]
            for stem, label, why in need:
                fm = re.search(r"%s\w*\s*:\s*(.*)" % stem, item, re.I)
                if not fm or not meaningful(fm.group(1)):
                    errors.append("«НОВЫЕ ИДЕИ», идея %s: нет «%s:» — %s" % (m.group(1), label, why))
            on = re.search(r"на\s+ч[её]м\s*:\s*(.*)", item, re.I)
            if not on or not meaningful(on.group(1)):
                errors.append("«НОВЫЕ ИДЕИ», идея %s: нет «На чём:» — на каком поле источника или новом сборе делается "
                              "первый шаг" % m.group(1))
            elif not re.search(r"«[^»]+»\s*\[F-\d+\]", on.group(1)) and not re.search(r"новый\s+сбор", on.group(1), re.I):
                errors.append("«НОВЫЕ ИДЕИ», идея %s: первый шаг не опирается ни на поле источника, ни на новый сбор"
                              % m.group(1))
    return keys, errors, moves


def main():
    if len(sys.argv) < 2:
        sys.stderr.write(__doc__)
        return 2
    task = sys.argv[1].rstrip("/")
    keys, errors, moves = check(task)
    if keys is None:
        print("Прогноза Нострадамуса нет: проверять нечего.")
        return 0
    os.makedirs(os.path.join(task, "checks"), exist_ok=True)
    out = ["# Нострадамус: " + os.path.basename(task), "",
           "Ключевых вопросов: %d (%s), новых идей: %d" % (len(keys), ", ".join("GAP %d" % k for k in keys) or "—", moves),
           "", "## Ошибки"] + (["- " + e for e in errors] or ["- нет"])
    open(os.path.join(task, "checks", "forecast.md"), "w", encoding="utf-8").write("\n".join(out) + "\n")
    for e in errors:
        print("нострадамус: " + e)
    if not errors:
        print("Нострадамус: ключевых вопросов %d, новых идей %d, ошибок нет." % (len(keys), moves))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
