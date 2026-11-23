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
9. Только в `--tz`: контекста «много», а уровень «лёгкий» (выбран человеком или назван в запросе) — в ЧТО ПОЛУЧИШЬ
   есть предупреждение, что на лёгком ключевые находки из материалов могут не дойти до сдачи (слова «лёгк» и «находк»).
10–11 действуют до строки СОГЛАСОВАНО: это правила показа ТЗ человеку, согласованное ТЗ оркестратор не меняет.
10. Только в `--tz`, типы «гипотезы», «план проверки», «ТЗ на доработку»: строка ЁМКОСТЬ с числом; если ЗАПРОС просит
   предложить, придумать, найти лучшие или новые идеи, варианты, ходы, практики или исследовать — в РЕЖИМ
   «генерация: ширина» и «новые идеи: да», либо в ДОПУЩЕНИЯ строка «ширина не нужна: <причина>».
11. Только в `--tz`: после ЗАПРОСА идёт ЦЕЛЬ, сразу за ней — ЧТО ПОЛУЧИШЬ (нет ЦЕЛИ — сразу после ЗАПРОСА); её первая строка — словами человека, без слов системы;
   тип выхода ей не противоречит: «изменения», «что поменять», «как проверить» — не исследование; «без выбора»,
   «только обзор», «без ставок» — не гипотезы и не план проверки.

12. Только в `--tz`, до СОГЛАСОВАНО, тип «карта направлений»: ЗАПРОС спрашивает, какие ещё бывают варианты или чего мы не
   знаем, — в РЕЖИМ «разведка поля: да» и «новые идеи: да», либо в ДОПУЩЕНИЯХ «разведка поля не нужна: <причина>».

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


def check_decision(tz, errors):
    """Для типов «гипотезы», «план проверки», «ТЗ на доработку» в ТЗ отдельной строкой стоит РЕШЕНИЕ с вариантами:
    по нему консультант расставляет путь, а проверка пути сверяет покрытие вариантов."""
    kind = re.search(r"^\**ТИП ВЫХОДА\**:?\**[ \t]*(.*)$", tz, re.M)
    if kind and re.search(r"гипотез|план проверки|ТЗ на доработку", kind.group(1), re.I) \
            and not re.search(r"^\**РЕШЕНИЕ\**:", tz, re.M):
        errors.append("нет строки РЕШЕНИЕ с вариантами — консультант и проверка пути ждут её (при сокращении ТЗ она остаётся)")


def check_price(tz, errors):
    m = re.search(r"^\**ЦЕНА\**:?\**[ \t]*(.*)$", tz, re.M)
    if not m:
        errors.append("нет строки ЦЕНА — человек согласует ТЗ, не видя цены маршрута (scripts/cost_estimate.py)")
    elif not all(re.search(p, m.group(1)) for p in (r"~\d+", r"резерв \d+", r"потолок \d+")):
        errors.append("в строке ЦЕНА нет числа вызовов, резерва или потолка — она не из scripts/cost_estimate.py")


def check_light(tz, errors):
    """Много материалов и лёгкий уровень: человек видит, что ключевые находки могут не дойти до сдачи."""
    ctx = re.search(r"^\**КОНТЕКСТ\**:?\**[ \t]*(.*)$", tz, re.M)
    load = re.search(r"^\**НАГРУЗКА\**:?\**[ \t]*(.*)$", tz, re.M)
    if not (ctx and load and re.search(r"объём:\s*много", ctx.group(1), re.I)
            and re.search(r"уровень:\s*л[её]гкий", load.group(1), re.I)):
        return
    got = re.search(r"^\**ЧТО ПОЛУЧИШЬ\**:?\**[ \t]*(.*(?:\n[ \t]+\S.*)*)", tz, re.M)
    if not (got and re.search(r"л[её]гк", got.group(1), re.I) and re.search(r"находк", got.group(1), re.I)):
        errors.append("контекста «много», уровень «лёгкий», а в ЧТО ПОЛУЧИШЬ нет предупреждения, что ключевые находки "
                      "из материалов на лёгком могут не дойти до сдачи")


WIDTH_ASK = re.compile(r"предлож|придума|лучш|нов\w* иде|иде[ийя]\b|вариант|какие (?:ходы|подходы|бывают)|"
                       r"практик|исследу|исследован|как (?:это )?делают", re.I)


def check_width(tz, errors):
    """Ёмкость режет запускаемое, а не то, что показать: запрос «предложи / лучшие / исследуй» требует ширины."""
    kind = re.search(r"^\**ТИП ВЫХОДА\**:?\**[ \t]*(.*)$", tz, re.M)
    if not (kind and re.search(r"гипотез|план проверки|ТЗ на доработку", kind.group(1), re.I)):
        return
    cap = re.search(r"^\**ЁМКОСТЬ\**:?\**[ \t]*(.*)$", tz, re.M)
    if not (cap and re.search(r"\d", cap.group(1))):
        errors.append("нет строки ЁМКОСТЬ с числом проверок за 2 недели")
    ask = re.search(r"^\**ЗАПРОС\**:?\**[ \t]*(.*)$", tz, re.M)
    if not (ask and WIDTH_ASK.search(ask.group(1))):
        return
    mode = re.search(r"^\**РЕЖИМ\**:?\**[ \t]*(.*)$", tz, re.M)
    mode = mode.group(1) if mode else ""
    wide = re.search(r"генерация:\s*ширина", mode, re.I) and re.search(r"новые идеи:\s*да", mode, re.I)
    if not wide and not re.search(r"ширина не нужна\s*:\s*\S", tz, re.I):
        errors.append("ЗАПРОС просит предложить или найти идеи, а в РЕЖИМ нет ширины и новых идей, и в ДОПУЩЕНИЯХ нет "
                      "причины, почему ширина не нужна (правило — диспетчер, «Ширина и новые идеи»)")


UNKNOWN_ASK = re.compile(r"как(?:ие|ой|ая|ое|их)\s+ещ[её]|ещ[её]\s+(?:есть|бывают|можно|сценари|вариант)|"
                         r"не\s+знаем|мы\s+не\s+знаем|неизвестн|что\s+упускаем|что\s+ещ[её]", re.I)


def check_unknown(tz, errors):
    """Карта направлений на вопрос «какие ещё есть / чего мы не знаем»: нужны разведка поля и новые идеи.
    Иначе карта пересказывает то, что уже лежит в материалах."""
    kind = re.search(r"^\**ТИП ВЫХОДА\**:?\**[ \t]*(.*)$", tz, re.M)
    if not (kind and re.search(r"карта направлений", kind.group(1), re.I)):
        return
    ask = re.search(r"^\**ЗАПРОС\**:?\**[ \t]*(.*)$", tz, re.M)
    if not (ask and UNKNOWN_ASK.search(ask.group(1))):
        return
    mode = re.search(r"^\**РЕЖИМ\**:?\**[ \t]*(.*)$", tz, re.M)
    mode = mode.group(1) if mode else ""
    ok = re.search(r"разведка поля:\s*да", mode, re.I) and re.search(r"новые идеи:\s*да", mode, re.I)
    if not ok and not re.search(r"(?:ширина|разведка поля)\s+не\s+нужн\w*\s*:\s*\S", tz, re.I):
        errors.append("ЗАПРОС про то, какие ещё бывают варианты, тип «карта направлений», а в РЕЖИМ нет «разведка поля: да» "
                      "и «новые идеи: да», и в ДОПУЩЕНИЯХ нет записи с причиной, почему разведка поля не нужна")


FIELD_LINE = re.compile(r"^\**([А-ЯЁ][А-ЯЁ ]{2,}?)\**:", re.M)
SYSTEM_WORDS = re.compile(r"гипотез|вердикт|тип\w* выход|\bGAP\b|бэклог|валидац|разведк|маршрут|\bполе\b|поля\b|"
                          r"оркестратор|диспетчер|исполнител|нострадамус|линз", re.I)
ACTION_WORDS = re.compile(r"изменени|что помен|что менять|как провер|что делать|первый тест|предложени", re.I)
NO_CHOICE = re.compile(r"без выбора|только обзор|без ставок", re.I)


def check_result(tz, errors):
    """Что человек получит на руки — сразу после ЦЕЛИ, его словами, и тип выхода ему не противоречит."""
    fields = [m.group(1).strip() for m in FIELD_LINE.finditer(tz)]
    if "ЗАПРОС" in fields:
        i = fields.index("ЗАПРОС")
        if "ЦЕЛЬ" in fields:
            if fields[i + 1:i + 2] != ["ЦЕЛЬ"]:
                errors.append("ЦЕЛЬ не сразу после ЗАПРОСА")
            i = fields.index("ЦЕЛЬ")
        if i + 1 >= len(fields) or fields[i + 1] != "ЧТО ПОЛУЧИШЬ":
            errors.append("нет ЧТО ПОЛУЧИШЬ сразу после ЦЕЛИ (или ЗАПРОСА, если ЦЕЛИ нет) — порядок: ЗАПРОС, ЦЕЛЬ, ЧТО ПОЛУЧИШЬ")
    got = re.search(r"^\**ЧТО ПОЛУЧИШЬ\**:?\**[ \t]*(.*)$", tz, re.M)
    first = re.sub(r"\((?:ответ|черновик)\)", "", got.group(1)).strip() if got else ""
    if got and not first.strip(" —-–."):
        errors.append("первая строка ЧТО ПОЛУЧИШЬ пустая")
    words = sorted({w.group(0).lower() for w in SYSTEM_WORDS.finditer(first)})
    if words:
        errors.append("в первой строке ЧТО ПОЛУЧИШЬ слова системы: %s" % ", ".join(words))
    kind = re.search(r"^\**ТИП ВЫХОДА\**:?\**[ \t]*(.*)$", tz, re.M)
    kind = kind.group(1).lower() if kind else ""
    if first and kind.startswith("исследование") and ACTION_WORDS.search(first) and not NO_CHOICE.search(first):
        errors.append("ЧТО ПОЛУЧИШЬ обещает, что менять или как проверить, а тип выхода — «исследование»")
    if first and re.match(r"(гипотез|план проверки)", kind) and NO_CHOICE.search(first):
        errors.append("ЧТО ПОЛУЧИШЬ — без выбора, а тип выхода предполагает, что менять")


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
        check_decision(tz, errors)
        check_light(tz, errors)
        if not re.search(r"^\W*СОГЛАСОВАНО", tz, re.M):
            # ширина и «ЧТО ПОЛУЧИШЬ» — правила показа ТЗ человеку; согласованное ТЗ оркестратор не меняет (R-011)
            check_width(tz, errors)
            check_unknown(tz, errors)
            check_result(tz, errors)
        for e in errors:
            print("ТЗ: " + e)
        if not errors:
            print("ТЗ: пунктов GAP %d, у каждого есть пометка, где ответ; ВЕБ согласован; ЦЕНА есть." % len(gap_numbers(tz)))
        return 1 if errors else 0
    review = read(os.path.join(task, "01-review.md"))
    review = re.sub(r"\*\*|__", "", review)  # жирный шрифт («**Закрывает GAP:** 1») — не повод перезапрашивать консультанта
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
