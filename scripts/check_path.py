#!/usr/bin/env python3
"""Проверяет единый учёт задачи: путь консультанта покрывает ТЗ, и у каждого пункта пути есть исход.

  python3 scripts/check_path.py tasks/<папка>

Что сверяется:
1. Каждый пункт GAP из `00-tz.md` упомянут в `01-review.md` — в строке «Закрывает GAP: …» у пункта пути, в пометке
   «(GAP k)» у утверждения карты или в строке «Вне пути: GAP k — причина». Пункт GAP, которого нет нигде, — ошибка.
2. У каждого пункта пути из `01-review.md` (П-1…, в валидации — У-1…) в `log.md` под заголовком «ПУТЬ — ИСХОДЫ»
   есть строка с исходом: закрыт / проверкой по сути / запрос данных / живая проверка / снят. Строка без исхода
   или пункт без строки — ошибка.

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
    task = sys.argv[1].rstrip("/")
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
    found = outcomes(read(os.path.join(task, "log.md")))
    if found is None:
        errors.append("в log.md нет раздела «ПУТЬ — ИСХОДЫ»: его пишут перед сдачей")
    else:
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
