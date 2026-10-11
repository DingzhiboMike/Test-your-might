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

Нет `01-review.md` — проверять нечего. Есть разбор, но в логе нет раздела «ПУТЬ — ИСХОДЫ» — ошибка: его пишут
перед сдачей. Код возврата 1 — есть ошибки. Отчёт: tasks/<папка>/checks/path.md.
"""
import os
import re
import sys

OUTCOMES = re.compile(r"закрыт|проверк\w* по сути|запрос\w* данных|D-\d+|жив\w* проверк|снят", re.I)
ITEM = re.compile(r"(?<![\w-])([ПУ])-(\d+)\b")


def read(path):
    return open(path, encoding="utf-8").read() if os.path.exists(path) else ""


def gap_numbers(tz):
    """Номера пунктов GAP из ТЗ: строки «  1. …» после «GAP:» до следующего поля в верхнем регистре."""
    m = re.search(r"^\**GAP\b[^\n]*?:\**[ \t]*", tz, re.M)
    if not m:
        return set()
    rest = tz[m.end():]
    stop = re.search(r"^\**[А-ЯЁA-Z][А-ЯЁA-Z\- ]{2,}\**:", rest, re.M)
    block = rest[:stop.start()] if stop else rest
    return {int(n) for n in re.findall(r"^\s*(\d+)\.", block, re.M)}


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
    tz = read(os.path.join(task, "00-tz.md"))
    check_plan(tz, review, errors)
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
