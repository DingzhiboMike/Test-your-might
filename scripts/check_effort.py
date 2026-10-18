#!/usr/bin/env python3
"""«Мало данных» — не выход из маршрута: ключевой пункт не сдаётся без попытки, а выход соразмерен ёмкости.

  python3 scripts/check_effort.py tasks/<папка>

Перед сдачей типов «гипотезы», «план проверки», «ТЗ на доработку», «исследование»:
1. Каждый ключевой пункт GAP (и GAP 1), у которого в ТЗ ответ помечен «веб», при «ВЕБ: да» получил хотя бы один
   ход к источнику данных — шаг в логе со строкой «Пункт GAP: GAP k …». Иначе нужна строка лога
   «Без хода: GAP k — <причина>». «Нет данных», «мало данных», «данных не хватает», «экономия», «бюджет», «шагов»
   причиной не считаются — кроме случая, когда свободных вызовов не осталось (по трассе и строке ЦЕНА или по строке
   «свободных вызовов нет» в логе): тогда пропуск — предупреждение, а не ошибка.
2. Если итоговые вердикты (последний из 02d-validation2.md, 02c-validation.md) все «сузить» или «не держится»,
   часть сдачи для человека (08-handoff.md до «## Служебное») начинается с раздела «Что нужно, чтобы двигаться
   дальше» — запросы данных и дешёвые замены идут первыми, а не после новых идей.
3. В разделе «А ещё есть идеи» сдачи — не больше ЁМКОСТЬ + 1 идей (строки-пункты); остальные — одной строкой
   «В очереди: …».

Тип «разбор», «валидация» и «вердикты по проверке» не проверяются: в валидации на каждое утверждение в веб ходит
сама проверка по сути. Ошибка — код возврата 1. Отчёт: tasks/<папка>/checks/effort.md.

Функции capacity, ideas_ordered, final_verdicts, all_narrowed, ideas_required берут check_forecast.py,
check_readable.py и cost_estimate.py.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from check_path import gap_answers, gap_items, web_field  # noqa: E402
from check_log_sources import SOURCES, STEP, field  # noqa: E402

CHECKED = ("гипотезы", "план проверки", "ТЗ на доработку", "исследование")
VERDICT = re.compile(r"^\s*Вердикт\s*:\s*(держится на бумаге|сузить|не держится)", re.M | re.I)
BAD_REASON = re.compile(r"нет данных|данных нет|мало данных|данных не хват|недостаточно данных|эконом|бюджет|шаг",
                        re.I)
NEXT = "Что нужно, чтобы двигаться дальше"
MORE = "А ещё есть идеи"


def read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def tz_field(tz, name):
    m = re.search(r"^\**%s\**:?\**[ \t]*(.*(?:\n[ \t]+\S.*)*)" % re.escape(name), tz, re.M)
    return m.group(1).strip() if m else ""


def capacity(tz):
    """ЁМКОСТЬ: N проверок за 2 недели → N; поля нет — None."""
    m = re.search(r"(\d+)", tz_field(tz, "ЁМКОСТЬ"))
    return int(m.group(1)) if m else None


def ideas_ordered(tz):
    """Человек заказал новые идеи: РЕЖИМ … «новые идеи: да»."""
    return bool(re.search(r"новые идеи:\s*да", tz_field(tz, "РЕЖИМ"), re.I))


def final_verdicts(task):
    """Вердикты последнего прохода проверки по сути: второй проход, если был, иначе первый."""
    for name in ("02d-validation2.md", "02c-validation.md"):
        text = read(os.path.join(task, name))
        if text:
            return [v.lower() for v in VERDICT.findall(text)]
    return []


def all_narrowed(task):
    v = final_verdicts(task)
    return bool(v) and all(x in ("сузить", "не держится") for x in v)


def ideas_required(task):
    """Новые идеи у Нострадамуса: по заказу человека или когда все вердикты «сузить / не держится»."""
    return ideas_ordered(read(os.path.join(task, "00-tz.md"))) or all_narrowed(task)


def output_type(tz):
    v = tz_field(tz, "ТИП ВЫХОДА").lower()
    found = [t for t in CHECKED + ("разбор", "валидация", "вердикты по проверке") if t.lower() in v]
    return found[0] if len(found) == 1 else None


def free_exhausted(task, log):
    if re.search(r"свободных вызовов нет", log):
        return True
    try:
        import cost_estimate as ce
        tz = read(os.path.join(task, "00-tz.md"))
        line = ce.tz_field(tz, "ЦЕНА")
        res, ceil = re.search(r"резерв (\d+)", line), re.search(r"потолок (\d+)", line)
        if not (res and ceil) or not os.path.exists(os.path.join(task, "trace.jsonl")):
            return False
        n, _, done = ce.spent(task)
        return int(ceil.group(1)) - n - max(0, int(res.group(1)) - done) <= 0
    except Exception:
        return False


def key_gaps(tz):
    items = gap_items(tz)
    keys = {n for n, t in items.items() if "[ключевой]" in t}
    if 1 in items:
        keys.add(1)
    return sorted(keys)


def attempted(log):
    """Номера пунктов GAP, по которым был ход к источнику данных."""
    heads = list(STEP.finditer(log))
    got = set()
    for i, m in enumerate(heads):
        if m.group(2) not in SOURCES:
            continue
        block = log[m.end():heads[i + 1].start() if i + 1 < len(heads) else len(log)]
        got.update(int(n) for n in re.findall(r"GAP\s*(\d+)", field(block, "Пункт GAP") or ""))
    return got


def human_part(text):
    m = re.search(r"^#+\s*Служебное", text, re.M)
    return text[:m.start()] if m else text


def section(text, title):
    m = re.search(r"^#+\s*%s\b.*$" % re.escape(title), text, re.M | re.I)
    if not m:
        return None
    rest = text[m.end():]
    stop = re.search(r"^#+\s", rest, re.M)
    return rest[:stop.start()] if stop else rest


def check(task):
    tz = read(os.path.join(task, "00-tz.md"))
    kind = output_type(tz)
    if kind not in CHECKED:
        return None, [], []
    log = read(os.path.join(task, "log.md"))
    errors, warns = [], []

    if web_field(tz).startswith("да"):
        answers, tried = gap_answers(tz), attempted(log)
        skipped = {int(n): r.strip() for n, r in
                   re.findall(r"^\s*Без хода:\s*GAP\s*(\d+)\s*[—-]\s*(.*)$", log, re.M)}
        exhausted = free_exhausted(task, log)
        for n in key_gaps(tz):
            if not (answers.get(n) and "веб" in answers[n]) or n in tried:
                continue
            reason = skipped.get(n, "")
            if reason and len(reason) >= 10 and not BAD_REASON.search(reason):
                continue
            msg = ("GAP %d [ключевой]: ответ помечен «веб», а хода к источнику нет%s" %
                   (n, " и причина «%s» не принимается" % reason[:50] if reason else ""))
            (warns if exhausted else errors).append(msg + ("; свободных вызовов не осталось" if exhausted else ""))

    handoff = human_part(read(os.path.join(task, "08-handoff.md")))
    if handoff:
        if all_narrowed(task):
            first = re.search(r"^#{2,}\s*(.+)$", handoff, re.M)  # заголовок документа «# …» не раздел
            if not first or NEXT.lower() not in first.group(1).lower():
                errors.append("все вердикты «сузить / не держится», а сдача начинается не с раздела «%s»" % NEXT)
        cap = capacity(tz)
        more = section(handoff, MORE)
        if cap is not None and more is not None:
            n = len(re.findall(r"^\s*(?:\d+[.)]|[-—•*])\s+\S", more, re.M))
            if n > cap + 1:
                errors.append("«%s»: %d идей при ёмкости %d — не больше %d, остальные — строкой «В очереди»"
                              % (MORE, n, cap, cap + 1))
    return kind, errors, warns


def main():
    if len(sys.argv) < 2:
        sys.stderr.write(__doc__)
        return 2
    task = sys.argv[1].rstrip("/")
    kind, errors, warns = check(task)
    if kind is None:
        print("Тип выхода не из проверяемых: проверять нечего.")
        return 0
    os.makedirs(os.path.join(task, "checks"), exist_ok=True)
    out = ["# Мало данных — не выход: " + os.path.basename(task), "", "## Ошибки"]
    out += ["- " + e for e in errors] or ["- нет"]
    out += ["", "## Предупреждения"] + (["- " + w for w in warns] or ["- нет"])
    with open(os.path.join(task, "checks", "effort.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    for e in errors:
        print("усилие: " + e)
    for w in warns:
        print("усилие (предупреждение): " + w)
    if not errors:
        print("Усилие: ключевые пункты с ответом в вебе пройдены, сдача соразмерна ёмкости.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
