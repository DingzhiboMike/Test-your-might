#!/usr/bin/env python3
"""Цена маршрута до запуска и остаток по ходу: сколько вызовов исполнителей и токенов уйдёт на задачу.

  python3 scripts/cost_estimate.py tasks/<папка>            # строка ЦЕНА для ТЗ (диспетчер)
  python3 scripts/cost_estimate.py tasks/<папка> --detail   # из чего сложилась оценка
  python3 scripts/cost_estimate.py tasks/<папка> --left     # сколько потрачено и сколько свободных вызовов осталось

Бюджет — все вызовы маршрута, категории «вне бюджета» нет. Он делится на две части:
- свободная часть — шаги по тиру (Tier 1 — 8, Tier 2 — 6): консультант, звенья цепочки, источники данных;
- резерв — обязательные вызовы, которые оркестратор не выбирает: картография и углубление документов, модель
  предмета или разбор материалов, разборы интервью сверх одного шага, дополнительные шаги маршрута типа
  выхода, проверка смысла с исправлением, Нострадамус и отсев идей. Резерв нельзя потратить на источники.
Потолок — оценка вызовов × 1,3; дошёл — остановка по правилу оркестратора.

Токены на вызов — медиана по трассам прошлых задач в tasks/*/trace.jsonl. Трасс нет — 85 тыс. на вызов
(замер 13.10 на средней модели: 77–86 тыс. на шаг) с пометкой «без прогонов». Если по этому типу выхода
сдано два прогона и больше (tasks/*/checks/cost.json), число вызовов поправляется на медиану «факт / оценка».
"""
import csv
import glob
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import trace_lib as tl  # noqa: E402

TYPES = ["разбор", "гипотезы", "план проверки", "вердикты по проверке", "валидация", "исследование",
         "ТЗ на доработку"]
TIER_STEPS = {1: 8, 2: 6}
DEEPEN_CAP = {1: 12, 2: 8}
MAP_BATCH = 7
PRIOR_PER_CALL = 85000
CEILING = 1.3

RESERVE_ROLES = {"document-mapper", "document-deepener", "subject-model", "context-reader", "meaning-review",
                 "nostradamus", "brief-writer", "research-report"}
RESERVE_MODES = ("отсев", "итогов", "бэклог", "усилен", "пробн", "исправлен")


def plural(n, one, few, many):
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def calls_word(n):
    return "%d %s" % (n, plural(n, "вызов", "вызова", "вызовов"))


def read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def tz_field(tz, name):
    """Значение поля ТЗ вместе со строками продолжения (с отступом)."""
    m = re.search(r"^\**%s\**:?\**[ \t]*(.*(?:\n[ \t]+\S.*)*)" % re.escape(name), tz, re.M)
    return m.group(1).strip() if m else ""


def tz_type(tz):
    v = tz_field(tz, "ТИП ВЫХОДА")
    found = [t for t in TYPES if t.lower() in v.lower()]
    return found[0] if len(found) == 1 else None


def tz_tier(tz):
    tiers = set(re.findall(r"Tier\s*([12])", tz_field(tz, "ТИР")))
    return int(tiers.pop()) if len(tiers) == 1 else None


def tz_modes(tz):
    v = tz_field(tz, "РЕЖИМ")
    return {
        "rehearsal": bool(re.search(r"пробный прогон:\s*да", v)),
        "width": bool(re.search(r"генерация:\s*ширина", v)),
    }


def context_docs(task):
    """Документы контекста в реестре: всего и интервью."""
    docs = interviews = 0
    try:
        with open(os.path.join(task, "sources.csv"), encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                if r.get("kind") in ("context", "interview", "from-tasks"):
                    docs += 1
                    interviews += r.get("kind") == "interview"
    except OSError:
        pass
    return docs, interviews


def structure(kind, tier, docs, interviews, modes, mapped):
    """Список (что, вызовов, часть) — часть «свободная» или «резерв»."""
    free = TIER_STEPS.get(tier, 6)
    if kind == "разбор":
        free = 1
    elif kind == "вердикты по проверке":
        free = 3
    items = [("шаги по тиру", free, "свободная")]
    if docs and kind != "вердикты по проверке":
        if mapped:
            items.append(("картография документов", math.ceil(docs / MAP_BATCH), "резерв"))
            items.append(("углубление документов", min(DEEPEN_CAP.get(tier, 8), docs), "резерв"))
            items.append(("модель предмета", 1, "резерв"))
        else:
            items.append(("разбор материалов", 1, "резерв"))
        if interviews > 1:
            items.append(("разборы интервью сверх одного шага", interviews - 1, "резерв"))
    if kind in ("гипотезы", "план проверки", "ТЗ на доработку"):
        items.append(("линзы: ещё два вызова в том же шаге", 2, "свободная"))
    plus = {"гипотезы": ("итоговая позиция и бэклог", 2), "ТЗ на доработку": ("итоговая позиция и бриф", 2),
            "валидация": ("усиление, методы, сборка документа", 3)}
    if kind in plus:
        items.append((plus[kind][0], plus[kind][1], "резерв"))
    if modes.get("width") and kind in ("гипотезы", "план проверки", "ТЗ на доработку"):
        items.append(("длинный список", 1, "резерв"))
    if modes.get("rehearsal") and kind in ("гипотезы", "план проверки"):
        items.append(("пробный прогон и исправление по нему", 2, "резерв"))
    reviews = {"гипотезы": 1, "план проверки": 1, "ТЗ на доработку": 1, "исследование": 1, "валидация": 2}
    if kind in reviews:
        n = reviews[kind] + (1 if tier == 1 else 0)
        items.append(("проверка смысла с исправлением", 2 * n, "резерв"))
    if kind in ("гипотезы", "план проверки", "ТЗ на доработку", "исследование"):
        items.append(("Нострадамус и отсев идей", 2, "резерв"))
    return items


def history(root, exclude=None):
    """Токены на вызов, основная сессия и поправка «факт / оценка» по прошлым задачам."""
    per_call, mains, ratios, tasks = [], [], {}, set()
    for tr in glob.glob(os.path.join(root, "tasks", "*", "trace.jsonl")):
        task = os.path.dirname(tr)
        if exclude and os.path.abspath(task) == os.path.abspath(exclude):
            continue
        rows = tl.load_trace(task)
        if rows:
            tasks.add(task)
            per_call += [tl.total(r) for r in rows if tl.total(r) > 0]
        main = tl.load_main(task)
        if main:
            mains.append(sum(tl.total(v) for v in main.values()))
    for cj in glob.glob(os.path.join(root, "tasks", "*", "checks", "cost.json")):
        if exclude and os.path.abspath(os.path.dirname(os.path.dirname(cj))) == os.path.abspath(exclude):
            continue
        try:
            c = json.load(open(cj, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if c.get("type") and c.get("estimate_calls") and c.get("calls"):
            ratios.setdefault(c["type"], []).append(c["calls"] / c["estimate_calls"])
    return per_call, mains, ratios, len(tasks)


def median(xs):
    xs = sorted(xs)
    if not xs:
        return None
    m = len(xs) // 2
    return xs[m] if len(xs) % 2 else (xs[m - 1] + xs[m]) / 2


def quantile(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, max(0, int(round(q * (len(xs) - 1)))))]


def estimate(task):
    root = os.path.dirname(os.path.dirname(os.path.abspath(task)))
    tz = read(os.path.join(task, "00-tz.md"))
    kind, tier = tz_type(tz), tz_tier(tz)
    docs, interviews = context_docs(task)
    mapped = os.path.exists(os.path.join(task, "00d-map.md")) or os.path.isdir(os.path.join(task, "map"))
    items = structure(kind, tier, docs, interviews, tz_modes(tz), mapped)
    calls = sum(n for _, n, _ in items)
    reserve = sum(n for _, n, p in items if p == "резерв")
    per_call, mains, ratios, runs = history(root, exclude=task)
    ratio = median(ratios.get(kind, [])) if len(ratios.get(kind, [])) >= 2 else None
    if ratio:
        calls = max(calls, round(calls * ratio))
    if per_call:
        mid, lo, hi = median(per_call), quantile(per_call, 0.25), quantile(per_call, 0.75)
        basis = "по %d %s с трассой, медиана %s на вызов" % (runs, plural(runs, "прогону", "прогонам", "прогонам"),
                                                            tl.k(mid))
    else:
        mid, lo, hi = PRIOR_PER_CALL, PRIOR_PER_CALL * 0.8, PRIOR_PER_CALL * 1.3
        basis = "без прогонов с трассой: %s на вызов по замеру 13.10" % tl.k(PRIOR_PER_CALL)
    if ratio:
        basis += ", число вызовов поправлено на факт прошлых прогонов ×%s" % ("%.2f" % ratio).replace(".", ",")
    return {
        "type": kind, "tier": tier, "docs": docs, "interviews": interviews, "items": items,
        "calls": calls, "free": calls - reserve, "reserve": reserve, "ceiling": math.ceil(calls * CEILING),
        "tokens": calls * mid, "tokens_lo": calls * lo, "tokens_hi": calls * hi,
        "main": median(mains), "basis": basis,
    }


def price_line(e):
    main = ("; основная сессия — ещё ~%s" % tl.k(e["main"])) if e["main"] else \
        "; основная сессия не оценена: нет прогонов с трассой"
    return ("ЦЕНА:       ~%s исполнителей (свободная часть %d, резерв %d, потолок %d), ~%s токенов "
            "(диапазон %s–%s)%s; оценка %s" % (
                calls_word(e["calls"]), e["free"], e["reserve"], e["ceiling"], tl.k(e["tokens"]),
                tl.k(e["tokens_lo"]), tl.k(e["tokens_hi"]), main, e["basis"]))


def spent(task):
    rows = tl.load_trace(task)
    res, interviews = 0, 0
    for r in rows:
        role, mode = r.get("role", ""), r.get("mode", "").lower()
        if role == "interview-analyst":
            interviews += 1
            res += interviews > 1
        elif role in RESERVE_ROLES or any(m in mode for m in RESERVE_MODES):
            res += 1
    return len(rows), sum(tl.total(r) for r in rows), res


def left(task):
    tz = read(os.path.join(task, "00-tz.md"))
    line = tz_field(tz, "ЦЕНА")
    m_calls, m_res, m_ceil = (re.search(p, line) for p in (r"~(\d+)", r"резерв (\d+)", r"потолок (\d+)"))
    n, tokens, res_done = spent(task)
    if not (m_calls and m_res and m_ceil):
        print("Потрачено: %s, %s токенов; в ТЗ нет строки ЦЕНА с резервом и потолком — остаток не посчитать"
              % (calls_word(n), tl.k(tokens)))
        return 1
    est, res, ceil = int(m_calls.group(1)), int(m_res.group(1)), int(m_ceil.group(1))
    res_left = max(0, res - res_done)
    free_left = ceil - n - res_left
    msg = "Потрачено: %s, %s токенов; по ЦЕНА ~%d, потолок %d; резерв впереди %d" % (
        calls_word(n), tl.k(tokens), est, ceil, res_left)
    if free_left <= 0:
        print(msg + " — свободных вызовов нет: дальше только резерв и финиш")
    else:
        print(msg + " — свободных вызовов до потолка %d" % free_left)
    return 0


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.stderr.write(__doc__)
        return 2
    task = args[0].rstrip("/")
    if "--left" in sys.argv:
        return left(task)
    e = estimate(task)
    if e["type"] is None or e["tier"] is None:
        print("В ТЗ не выбран %s — цену не посчитать." % ("ТИП ВЫХОДА" if e["type"] is None else "ТИР"))
        return 1
    print(price_line(e))
    if "--detail" in sys.argv:
        print("\nТип выхода: %s, Tier %d, документов %d (интервью %d)" % (e["type"], e["tier"], e["docs"],
                                                                     e["interviews"]))
        for what, n, part in e["items"]:
            print("- %s: %d (%s)" % (what, n, part))
    return 0


if __name__ == "__main__":
    sys.exit(main())
