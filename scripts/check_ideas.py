#!/usr/bin/env python3
"""Проверяет отсев новых идей Нострадамуса: каждая идея прошла проверку на убийство и ушла в следующий раунд с данными.

  python3 scripts/check_ideas.py tasks/<папка>

Сверяет `02g-ideas-check.md` с разделом «НОВЫЕ ИДЕИ» в `02f-forecast.md`:
1. По каждой идее N из `02f-forecast.md` есть блок «Идея N» с вердиктом: «кажется валидной», «переделать первый шаг»
   или «снять».
2. У каждой идеи заполнены «Убивает:» — фрагмент или «нет» — и «Возражения:» — что ослабляет идею, не убивая, с
   фрагментами, или «не найдено — искал: …». Возражение считается найденным по полю «Возражения», а не по «Убивает».
   У живой идеи — «Первый шаг выполним:»; «нет» допустимо только при вердикте «переделать первый шаг».
3. У «кажется валидной» и «переделать первый шаг» — непустые «Данные для следующего раунда:»; у «переделать» ещё
   «Первый шаг различает:» с тем, каким должен быть шаг.
4. «Снять» — только с причиной: фрагмент «…» [F-id] в «Убивает» или «Новая: нет». «Нет опор» причиной не считается:
   отсев проверяет на убийство, а не на доказательство.
5. Предупреждение, если сняты все идеи, ни у одной не нашлось возражения или у живой идеи в «Убивает» стоит фрагмент.

Ошибка — код возврата 1. Отчёт: tasks/<папка>/checks/ideas.md. Нет `02g-ideas-check.md` — проверять нечего (код 0).
"""
import os
import re
import sys

VERDICT = re.compile(r"кажется валидной|переделать первый шаг|снять", re.I)


def read(path):
    return open(path, encoding="utf-8").read() if os.path.exists(path) else ""


def idea_numbers(forecast):
    m = re.search(r"^#{0,3}\s*НОВЫЕ ИДЕИ\b.*$", forecast, re.M | re.I)
    if not m:
        return []
    body = forecast[m.end():]
    stop = re.search(r"^#{1,3}\s|^РАМКА\b", body, re.M)
    body = body[:stop.start()] if stop else body
    return [int(n) for n in re.findall(r"^(\d+)[.)]\s*\S", body, re.M)]


def blocks(check):
    heads = list(re.finditer(r"^\W*Идея\s+(\d+)\b.*$", check, re.M))
    out = {}
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(check)
        out.setdefault(int(m.group(1)), check[m.start():end])
    return out


def field(block, name):
    m = re.search(r"^\s*%s\s*:\s*(.*(?:\n(?!\s*[А-ЯЁ][а-яё ]{3,40}:).*)*)" % name, block, re.M | re.I)
    return m.group(1).strip() if m else ""


def meaningful(v):
    return len(re.sub(r"[\s\-—–.:;,()<>«»]+", "", v)) >= 3


def main():
    if len(sys.argv) < 2:
        sys.stderr.write(__doc__)
        return 2
    task = sys.argv[1].rstrip("/")
    check = read(os.path.join(task, "02g-ideas-check.md"))
    if not check:
        print("Отсева идей нет: проверять нечего.")
        return 0
    errors, warns, counts = [], [], {}
    ideas = idea_numbers(read(os.path.join(task, "02f-forecast.md")))
    if not ideas:
        errors.append("в 02f-forecast.md нет раздела «НОВЫЕ ИДЕИ» — отсеивать нечего")
    got = blocks(check)
    objections = 0
    for n in ideas:
        b = got.get(n)
        if not b:
            errors.append("идея %d: нет вердикта отсева" % n)
            continue
        vm = VERDICT.search(field(b, "Вердикт"))
        if not vm:
            errors.append("идея %d: вердикт не «кажется валидной», «переделать первый шаг» или «снять»" % n)
            continue
        v = vm.group(0).lower()
        counts[v] = counts.get(v, 0) + 1
        kills = field(b, "Убивает")
        if not meaningful(kills):
            errors.append("идея %d: пустое «Убивает» — фрагмент, который убивает идею, или «нет»" % n)
        objs = field(b, "Возражения")
        if not meaningful(objs):
            errors.append("идея %d: нет «Возражения:» — что ослабляет идею, с фрагментами, или «не найдено — искал: …»" % n)
        elif not re.match(r"\W*не найден", objs, re.I):
            objections += 1
        elif not re.search(r"искал", objs, re.I):
            errors.append("идея %d: «Возражения: не найдено» без того, где искал" % n)
        killing = re.search(r"«[^»]{8,}»\s*\[F-\d+\]", kills)
        if v != "снять" and killing:
            warns.append("идея %d: в «Убивает» стоит фрагмент, а вердикт не «снять» — если он не убивает, перенеси его в "
                         "«Возражения»" % n)
        if v != "снять":
            doable = field(b, "Первый шаг выполним")
            if not meaningful(doable):
                errors.append("идея %d: нет «Первый шаг выполним:» — да, на каком поле, или нет, чего не хватает" % n)
            elif re.match(r"\W*нет\b", doable, re.I) and v != "переделать первый шаг":
                errors.append("идея %d: первый шаг невыполним, а вердикт «%s» — должен быть «переделать первый шаг»" % (n, v))
        if v != "снять" and not meaningful(field(b, "Данные для следующего раунда")):
            errors.append("идея %d: нет «Данные для следующего раунда» — без них идею не взять в следующий раунд" % n)
        if v == "переделать первый шаг" and not meaningful(field(b, "Первый шаг различает")):
            errors.append("идея %d: «переделать первый шаг», но не сказано, каким он должен быть" % n)
        if v == "снять":
            repeat = re.match(r"\W*нет\b", field(b, "Новая"), re.I)
            if not killing and not repeat:
                errors.append("идея %d: снята без причины — нужен фрагмент «…» [F-id] в «Убивает» или «Новая: нет»; "
                              "«нет опор» в отсеве не причина" % n)
    extra = sorted(set(got) - set(ideas))
    if extra and ideas:
        warns.append("вердикты по идеям, которых нет в 02f-forecast.md: %s" % ", ".join(map(str, extra)))
    if ideas and counts.get("снять", 0) == len(ideas):
        warns.append("сняты все идеи — проверь, не сняты ли они за отсутствие опор")
    if ideas and objections == 0:
        warns.append("ни у одной идеи не найдено возражения — проверь, где искал")

    summary = ", ".join("%s — %d" % (k, v) for k, v in sorted(counts.items())) or "вердиктов нет"
    os.makedirs(os.path.join(task, "checks"), exist_ok=True)
    out = ["# Отсев идей: " + os.path.basename(task), "", "Идей: %d (%s)" % (len(ideas), summary), "",
           "## Ошибки"] + (["- " + e for e in errors] or ["- нет"]) + ["", "## Предупреждения"] + (["- " + w for w in warns] or ["- нет"])
    open(os.path.join(task, "checks", "ideas.md"), "w", encoding="utf-8").write("\n".join(out) + "\n")
    for e in errors:
        print("отсев идей: " + e)
    for w in warns:
        print("отсев идей (внимание): " + w)
    if not errors:
        print("Отсев идей: идей %d (%s), ошибок нет." % (len(ideas), summary))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
