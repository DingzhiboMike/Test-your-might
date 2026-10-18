#!/usr/bin/env python3
"""Проверяет единый учёт задачи: путь консультанта покрывает ТЗ, и у каждого пункта пути есть исход.

  python3 scripts/check_path.py tasks/<папка>

Что сверяется:
1. Каждый пункт GAP из `00-tz.md` упомянут в `01-review.md` — в строке «Закрывает GAP: …» у пункта пути, в пометке
   «(GAP k)» у утверждения карты или в строке «Вне пути: GAP k — причина». Пункт GAP, которого нет нигде, — ошибка.
2. У каждого пункта пути из `01-review.md` (П-1…, в валидации — У-1…) в `log.md` под заголовком «ПУТЬ — ИСХОДЫ»
   есть строка с исходом: закрыт / проверкой по сути / запрос данных / живая проверка / снят. Строка без исхода
   или пункт без строки — ошибка.

С ключом `--plan` (сразу после консультанта, до первого хода) проверяется план, а не исходы:
3. Каждый вариант из поля РЕШЕНИЕ в ТЗ («варианты: А — …; Б — …») назван хотя бы в одной строке «Сдвигает: …»
   пункта пути. Решения нет («решения нет») — пункт не проверяется.
4. У каждого пункта пути П-k есть непустые строки «Сдвигает:» и «Чего не хватает в карте:».
5. Хотя бы один пункт помечен «[проверка допущения]» — он может опровергнуть главное допущение консультанта.
В валидации (пункты У-k) проверки 3–5 не применяются: путь там — карта утверждений.

С ключом `--tz` (диспетчер, до показа ТЗ человеку) проверяется только ТЗ:
6. У каждого пункта GAP есть пометка, где ответ: `{ответ: контекст, данные, веб, живая}` — одно или несколько.
7. Строка ВЕБ согласована с пометками: «да» — хотя бы у одного пункта есть «веб»; «нет» — ни у одного.
Эти же проверки идут и в `--plan`.
8. Только в `--tz`: есть строка ЦЕНА с числом вызовов, резервом и потолком (её печатает scripts/cost_estimate.py).

Нет `01-review.md` — проверять нечего. Есть разбор, но в логе нет раздела «ПУТЬ — ИСХОДЫ» — ошибка: его пишут
перед сдачей. Код возврата 1 — есть ошибки. Отчёт: tasks/<папка>/checks/path.md.
"""
import os
import re
import sys

OUTCOMES = re.compile(r"закрыт|проверк\w* по сути|запрос\w* данных|D-\d+|жив\w* проверк|снят", re.I)
ITEM = re.compile(r"(?<![\w-])([ПУ])-(\d+)\b")
ANSWER = re.compile(r"\{\s*ответ\s*:\s*([^}]*)\}", re.I)
CHANNELS = ("контекст", "данные", "веб", "живая")


def read(path):
    return open(path, encoding="utf-8").read() if os.path.exists(path) else ""


def gap_block(tz):
    m = re.search(r"^\**GAP\b[^\n]*?:\**[ \t]*", tz, re.M)
    if not m:
        return ""
    rest = tz[m.end():]
    stop = re.search(r"^\**[А-ЯЁA-Z][А-ЯЁA-Z\- ]{2,}\**:", rest, re.M)
    return rest[:stop.start()] if stop else rest


def gap_numbers(tz):
    """Номера пунктов GAP из ТЗ: строки «  1. …» после «GAP:» до следующего поля в верхнем регистре."""
    return {int(n) for n in re.findall(r"^\s*(\d+)\.", gap_block(tz), re.M)}


def gap_items(tz):
    """Пункты GAP с текстом: {номер: текст}. Строки продолжения (с отступом, без номера) приклеиваются к пункту."""
    items, cur = {}, None
    for line in gap_block(tz).splitlines():
        m = re.match(r"^\s*(\d+)\.\s*(.*)$", line)
        if m:
            cur = int(m.group(1))
            items[cur] = m.group(2).strip()
        elif cur is not None and line.strip():
            items[cur] += " " + line.strip()
    return items


def gap_answers(tz):
    """Где ответ по каждому пункту GAP: {номер: множество каналов} или None, если пометки нет."""
    out = {}
    for n, text in gap_items(tz).items():
        m = ANSWER.search(text)
        out[n] = {c for c in CHANNELS if m and c in m.group(1).lower()} if m else None
    return out


def web_field(tz):
    m = re.search(r"^\**ВЕБ\**:?\**[ \t]*(\S+)", tz, re.M)
    return m.group(1).lower().strip(".,;—-") if m else ""


def check_tz(tz, errors):
    answers = gap_answers(tz)
    for n, chans in sorted(answers.items()):
        if chans is None:
            errors.append("GAP %d: нет пометки, где ответ — {ответ: контекст / данные / веб / живая}" % n)
        elif not chans:
            errors.append("GAP %d: в пометке «ответ» нет ни одного из каналов: %s" % (n, ", ".join(CHANNELS)))
    web_items = [n for n, c in answers.items() if c and "веб" in c]
    web = web_field(tz)
    if web.startswith("да") and answers and not web_items:
        errors.append("ВЕБ: да, но ни у одного пункта GAP нет «веб» в пометке, где ответ")
    if web.startswith("нет") and web_items:
        errors.append("ВЕБ: нет, но у пунктов GAP %s ответ помечен «веб»" % ", ".join(map(str, web_items)))


def check_price(tz, errors):
    m = re.search(r"^\**ЦЕНА\**:?\**[ \t]*(.*)$", tz, re.M)
    if not m:
        errors.append("нет строки ЦЕНА — человек согласует ТЗ, не видя цены маршрута (scripts/cost_estimate.py)")
    elif not all(re.search(p, m.group(1)) for p in (r"~\d+", r"резерв \d+", r"потолок \d+")):
        errors.append("в строке ЦЕНА нет числа вызовов, резерва или потолка — она не из scripts/cost_estimate.py")


def gap_refs(review):
    refs = set()
    for m in re.finditer(r"GAP\s*:?\s*((?:\d+\s*(?:,|и)?\s*)+)", review):
        refs.update(int(n) for n in re.findall(r"\d+", m.group(1)))
    return refs


def decision_variants(tz):
    """Буквы вариантов из поля РЕШЕНИЕ: «варианты: А — …; Б — …». Нет поля или «решения нет» — пусто."""
    m = re.search(r"^\**РЕШЕНИЕ\**:?\**(.*(?:\n[ \t]+.*)*)", tz, re.M)
    if not m or re.search(r"решения нет", m.group(1), re.I):
        return []
    v = re.search(r"вариант\w*:?(.*)", m.group(1), re.I | re.S)
    if not v:
        return []
    return sorted(set(re.findall(r"(?:^|[;,\s])([А-ЯЁA-Z])\s*[—–-]", v.group(1))))


def item_blocks(review):
    """Текст каждого пункта П-k: от его строки до следующего пункта или пустой строки после блока."""
    blocks, cur = {}, None
    for line in review.splitlines():
        m = re.match(r"^\s*(?:[-*]\s*)?\**(П)-(\d+)\b", line)
        if m:
            cur = "П-%s" % m.group(2)
            blocks[cur] = [line]
        elif cur and line.strip():
            blocks[cur].append(line)
        elif cur and not line.strip():
            cur = None
    return {k: "\n".join(v) for k, v in blocks.items()}


def check_plan(tz, review, errors):
    blocks = item_blocks(review)
    if not blocks:
        return
    for key, text in blocks.items():
        for field in ("Сдвигает", "Чего не хватает в карте"):
            m = re.search(r"%s:[ \t]*(.*)" % field, text)
            if not m or not m.group(1).strip(" —-–"):
                errors.append("%s: нет строки «%s:» или она пустая" % (key, field))
    moved = set()
    for text in blocks.values():
        m = re.search(r"Сдвигает:[ \t]*(.*)", text)
        if m:
            moved.update(re.findall(r"\b([А-ЯЁA-Z])\b", m.group(1)))
    for v in decision_variants(tz):
        if v not in moved:
            errors.append("вариант решения «%s» не сдвигает ни один пункт пути" % v)
    if not any("[проверка допущения]" in t for t in blocks.values()):
        errors.append("нет пункта пути с пометкой «[проверка допущения]»")


def path_items(review):
    """Пункты пути — те, что определены в начале строки: «П-1. …», «- У-3 …»."""
    items = []
    for line in review.splitlines():
        m = re.match(r"^\s*(?:[-*]\s*)?\**([ПУ])-(\d+)\b", line)
        if m:
            key = "%s-%s" % (m.group(1), m.group(2))
            if key not in items:
                items.append(key)
    return items


def outcomes(log):
    m = re.search(r"^#*\s*ПУТЬ\s*[—-]\s*ИСХОДЫ\s*$", log, re.M)
    if not m:
        return None
    rest = log[m.end():]
    stop = re.search(r"^(#+ |ШАГ\s+\d|ПОРУЧЕНИЕ|СДАЧА)", rest, re.M)
    block = rest[:stop.start()] if stop else rest
    found = {}
    for line in block.splitlines():
        for m2 in ITEM.finditer(line):
            key = "%s-%s" % (m2.group(1), m2.group(2))
            if line.lstrip("|-* ").startswith(key):
                found[key] = bool(OUTCOMES.search(line[line.index(key) + len(key):]))
    return found


def main():
    if len(sys.argv) < 2:
        sys.stderr.write(__doc__)
        return 2
    task = [a for a in sys.argv[1:] if not a.startswith("--")][0].rstrip("/")
    tz = read(os.path.join(task, "00-tz.md"))
    if "--tz" in sys.argv:
        errors = []
        check_tz(tz, errors)
        check_price(tz, errors)
        for e in errors:
            print("ТЗ: " + e)
        if not errors:
            print("ТЗ: пунктов GAP %d, у каждого есть пометка, где ответ; ВЕБ согласован; ЦЕНА есть." % len(gap_numbers(tz)))
        return 1 if errors else 0
    review = read(os.path.join(task, "01-review.md"))
    if not review:
        print("Разбора консультанта нет: проверять нечего.")
        return 0
    errors = []
    gaps = gap_numbers(read(os.path.join(task, "00-tz.md")))
    missing = sorted(gaps - gap_refs(review))
    for n in missing:
        errors.append("GAP %d не привязан к пути: нет ни в «Закрывает GAP», ни в «(GAP k)», ни в «Вне пути»" % n)
    items = path_items(review)
    if not items:
        errors.append("в 01-review.md нет пунктов пути (П-1… или У-1…)")
    check_plan(tz, review, errors)
    if "--plan" in sys.argv:
        check_tz(tz, errors)
    found = {} if "--plan" in sys.argv else outcomes(read(os.path.join(task, "log.md")))
    if found is None:
        errors.append("в log.md нет раздела «ПУТЬ — ИСХОДЫ»: его пишут перед сдачей")
    elif "--plan" not in sys.argv:
        for key in items:
            if key not in found:
                errors.append("%s: нет строки в «ПУТЬ — ИСХОДЫ»" % key)
            elif not found[key]:
                errors.append("%s: в строке нет исхода (закрыт / проверкой по сути / запрос данных / живая проверка / снят)" % key)

    os.makedirs(os.path.join(task, "checks"), exist_ok=True)
    out = ["# Путь и исходы: " + os.path.basename(task), "",
           "Пунктов GAP: %d, пунктов пути: %d" % (len(gaps), len(items)), "", "## Ошибки"]
    out += ["- " + e for e in errors] or ["- нет"]
    open(os.path.join(task, "checks", "path.md"), "w", encoding="utf-8").write("\n".join(out) + "\n")
    for e in errors:
        print("путь: " + e)
    if not errors:
        print("Путь: пунктов GAP %d, пунктов пути %d, ошибок нет." % (len(gaps), len(items)))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
