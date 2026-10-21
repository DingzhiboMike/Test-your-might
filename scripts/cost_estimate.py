#!/usr/bin/env python3
"""Цена маршрута до запуска и остаток по ходу: сколько вызовов исполнителей и токенов уйдёт на задачу.

  python3 scripts/cost_estimate.py tasks/<папка>            # строка ЦЕНА для ТЗ (диспетчер)
  python3 scripts/cost_estimate.py tasks/<папка> --detail   # из чего сложилась оценка
  python3 scripts/cost_estimate.py tasks/<папка> --left     # сколько потрачено и сколько свободных вызовов осталось
  python3 scripts/cost_estimate.py tasks/<папка> --levels   # четыре уровня нагрузки: вызовы, токены, время, что утверждать
  python3 scripts/cost_estimate.py tasks/<папка> --level light   # строка ЦЕНА для выбранного уровня (до route.py profile)

Профиль прогона (state.json, `route.py profile`, либо --level, либо поле НАГРУЗКА в ТЗ) меняет оценку: линзы по
числу lenses, Нострадамус и отсев идей по forecast, проверка смысла и аудит только при validation=full. Нет профиля —
оценка v1.

Бюджет — все вызовы маршрута, категории «вне бюджета» нет. Он делится на две части:
- свободная часть — шаги по тиру (Tier 1 — 8, Tier 2 — 6): консультант, звенья цепочки, источники данных;
- резерв — обязательные вызовы, которые оркестратор не выбирает: картография и углубление документов, модель
  предмета или разбор материалов, разборы интервью сверх одного шага, дополнительные шаги маршрута типа
  выхода, проверка смысла с исправлением, выборочный аудит, Нострадамус (и отсев идей, если в РЕЖИМЕ «новые идеи: да»). Резерв нельзя потратить на источники.
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
import profile_lib as pl  # noqa: E402

TYPES = ["разбор", "гипотезы", "план проверки", "вердикты по проверке", "валидация", "исследование",
         "ТЗ на доработку"]
TIER_STEPS = {1: 8, 2: 6}
DEEPEN_CAP = {1: 12, 2: 8}
MAP_BATCH = 7
MAP_BATCH_EST = 9   # документов на одного картографа по факту прогонов
MAP_MIN_DOCS = 8    # с такого числа документов строится карта документов
DEEPEN_BATCH = 3    # документов углубления на одного агента (оркестратор берёт 3–4)
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
        "ideas": bool(re.search(r"новые идеи:\s*да", v, re.I)),
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


def structure(kind, tier, docs, interviews, modes, mapped, prof=None):
    """Список (что, вызовов, часть) — часть «свободная» или «резерв». С профилем — оценка по нагрузке."""
    if prof is not None and kind in ("гипотезы", "план проверки", "ТЗ на доработку"):
        return profile_structure(kind, docs, interviews, modes, mapped, prof)
    free = TIER_STEPS.get(tier, 6)
    if kind == "разбор":
        free = 1
    elif kind == "вердикты по проверке":
        free = 3
    items = [("шаги по тиру", free, "свободная")]
    if docs and kind != "вердикты по проверке":
        if mapped:
            items.append(("картография документов", math.ceil(docs / MAP_BATCH), "резерв"))
            items.append(("углубление документов", math.ceil(min(DEEPEN_CAP.get(tier, 8), docs) / DEEPEN_BATCH), "резерв"))
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
    if kind in reviews:
        items.append(("выборочный аудит итоговых артефактов", 1, "резерв"))
    if kind in ("гипотезы", "план проверки", "ТЗ на доработку", "исследование"):
        if modes.get("ideas"):
            items.append(("Нострадамус с новыми идеями и отсев идей", 2, "резерв"))
        else:
            items.append(("Нострадамус: лучшие версии (отсев — ещё вызов, если все вердикты «сузить / не держится»)",
                          1, "резерв"))
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


def fresh_per_call(root, exclude=None):
    """Новые токены на вызов (без чтения кэша) по трассам прошлых задач."""
    vals = []
    for tr in glob.glob(os.path.join(root, "tasks", "*", "trace.jsonl")):
        task = os.path.dirname(tr)
        if exclude and os.path.abspath(task) == os.path.abspath(exclude):
            continue
        vals += [tl.fresh(r) for r in tl.load_trace(task) if tl.fresh(r) > 0]
    return vals


def median(xs):
    xs = sorted(xs)
    if not xs:
        return None
    m = len(xs) // 2
    return xs[m] if len(xs) % 2 else (xs[m - 1] + xs[m]) / 2


def quantile(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, max(0, int(round(q * (len(xs) - 1)))))]


def profile_structure(kind, docs, interviews, modes, mapped, prof):
    """Оценка вызовов по профилю: что реально входит в маршрут при этой нагрузке."""
    lenses = int(prof["lenses"]) if prof["generation"] != "narrow" else 0
    items = [("консультант", 1, "свободная")]
    if lenses:
        items.append(("линзы: ходы к источникам за сырьём", lenses, "свободная"))
    items.append(("генератор" + (" (длинный список и глубина)" if prof["generation"] == "wide" else ""),
                  2 if prof["generation"] == "wide" else 1, "свободная"))
    if prof["validation"] != "none":
        items.append(("проверка по сути", 1, "свободная"))
    if docs >= MAP_MIN_DOCS and prof.get("level") == "strict":
        # модель предмета только на строгом уровне: картограф пачками, углубление пачками по DEEPEN_BATCH, модель
        items.append(("картография документов", math.ceil(docs / MAP_BATCH_EST), "резерв"))
        items.append(("углубление документов", math.ceil(min(DEEPEN_CAP.get(2, 8), docs) / DEEPEN_BATCH), "резерв"))
        items.append(("модель предмета", 1, "резерв"))
    elif docs:
        items.append(("разбор материалов", 1, "резерв"))
    if prof["validation"] == "full":
        items.append(("проверка смысла и исправление", 2, "резерв"))
        items.append(("выборочный аудит", 1, "резерв"))
    if prof["forecast"] == "on" and prof["generation"] != "narrow":
        items.append(("Нострадамус и отсев идей", 2, "резерв"))
    items.append(("итоговая позиция и бэклог", 2, "резерв"))
    items.append(("перезапрос по ошибкам проверок", 1, "резерв"))
    return items


def estimate(task, level=None):
    root = os.path.dirname(os.path.dirname(os.path.abspath(task)))
    tz = read(os.path.join(task, "00-tz.md"))
    kind, tier = tz_type(tz), tz_tier(tz)
    docs, interviews = context_docs(task)
    mapped = os.path.exists(os.path.join(task, "00d-map.md")) or os.path.isdir(os.path.join(task, "map"))
    prof = chosen_profile(task, tz, level)
    items = structure(kind, tier, docs, interviews, tz_modes(tz), mapped, prof)
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


def chosen_profile(task, tz, level=None):
    """Профиль для оценки: явный уровень → state.json → поле НАГРУЗКА в ТЗ → None (оценка v1)."""
    if level:
        prof = dict(pl.DEFAULT)
        prof.update(pl.preset(level))
        prof["level"] = level
        return prof
    if pl.has_profile(task):
        return pl.load(task)
    m = re.search(r"уровень:\s*(быстро|лёгкий|легкий|рабочий|строгий)", tz_field(tz, "НАГРУЗКА"), re.I)
    if m:
        key = {"быстро": "fast", "лёгкий": "light", "легкий": "light", "рабочий": "work",
               "строгий": "strict"}[m.group(1).lower()]
        prof = dict(pl.DEFAULT)
        prof.update(pl.preset(key))
        prof["level"] = key
        return prof
    return None


LEVEL_TEXT = {
    "fast": ("Быстро", "готовый ответ и несколько идей, без исполнителей",
             "идеи и рассуждение; выводы про рынок и факты не проверяются"),
    "light": ("Лёгкий (К5–К4)", "пул гипотез с дешёвыми тестами и порогами «убьёт»; проверка по методологии",
              "подтверждения источниками: выводы остаются гипотезами"),
    "work": ("Рабочий (баланс)", "то же, плюс сверка внешних фактов в вебе и лучшие версии ответов по ключевым вопросам",
             "дословной проверки цитат и независимого аудита"),
    "strict": ("Строгий (Т4–Т5)", "то же с цитатами, проверенными по тексту источников, независимой проверкой смысла и аудитом",
               "широты: идей будет меньше, работа идёт осторожнее"),
}
WHEN = {  # «подойдёт, если»: как человеку выбрать уровень по своей ситуации
    "fast": "нужен ответ сейчас, исследовать нечего или решение мелкое",
    "light": "материалов у вас мало или нет, цена ошибки низкая, нужны идеи и дешёвые тесты",
    "work": "нужно опереться на факты из сети, материалы есть, решение средней важности",
    "strict": "материалов много, или результат увидят другие, или решение трудно отменить",
}
MIN_PER_CALL = 4  # только для внутренней калибровки; человеку минуты не показываются


SHORT = {"картография документов": "карта ваших документов", "углубление документов": "углубление ключевых документов",
         "модель предмета": "модель предмета", "перезапрос по ошибкам проверок": "запас на перезапрос",
         "консультант": "консультант", "линзы: ходы к источникам за сырьём": "линзы", "проверка по сути": "проверка по сути",
         "разбор материалов": "разбор ваших материалов", "проверка смысла и исправление": "проверка смысла",
         "выборочный аудит": "аудит", "Нострадамус и отсев идей": "версии и новые идеи",
         "итоговая позиция и бэклог": "позиция и бэклог"}


def includes(items):
    """Что входит в уровень — словами, без чисел вызовов."""
    out = []
    for what, n, _ in items:
        label = SHORT.get(what) or ("генератор: длинный список и глубина" if what.startswith("генератор (") else what)
        if what.startswith("линзы"):
            label = "линз: %d" % n
        out.append(label)
    return ", ".join(out)


def levels_table(task):
    """Таблица для вопроса про нагрузку: что будет сделано, что получите, чего не будет, прогон (словами)."""
    tz = read(os.path.join(task, "00-tz.md"))
    kind, tier = tz_type(tz), tz_tier(tz) or 2
    docs, interviews = context_docs(task)
    root = os.path.dirname(os.path.dirname(os.path.abspath(task)))
    _, _, _, ratios_level, _ = history_levels(root, exclude=task)
    out = ["| Уровень | Подойдёт, если | Что будет сделано | Что получите | Чего не будет | Прогон |",
           "|---|---|---|---|---|---|"]
    for key in ("fast", "light", "work", "strict"):
        name, got, nope = LEVEL_TEXT[key]
        if key == "fast":
            out.append("| %s | %s | ответ без исполнителей | %s | %s | очень короткий |" % (name, WHEN[key], got, nope))
            continue
        prof = dict(pl.DEFAULT)
        prof.update(pl.preset(key))
        items = structure(kind or "гипотезы", tier, docs, interviews, tz_modes(tz), False, prof)
        calls = sum(n for _, n, _ in items)
        r = median(ratios_level.get(key, [])) if len(ratios_level.get(key, [])) >= 2 else None
        if r:
            calls = max(1, round(calls * r))
        out.append("| %s | %s | %s | %s | %s | %s |" % (name, WHEN[key], includes(items), got, nope,
                                                      duration_word(calls)))
    return "\n".join(out)


def history_levels(root, exclude=None):
    """Поправка «факт / оценка» по уровням из tasks/*/checks/cost.json (поле level, пишет trace_summary --save)."""
    by_level = {}
    for cj in glob.glob(os.path.join(root, "tasks", "*", "checks", "cost.json")):
        if exclude and os.path.abspath(os.path.dirname(os.path.dirname(cj))) == os.path.abspath(exclude):
            continue
        try:
            c = json.load(open(cj, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if c.get("level") and c.get("estimate_calls") and c.get("calls"):
            by_level.setdefault(c["level"], []).append(c["calls"] / c["estimate_calls"])
    return None, None, None, by_level, None


def price_line(e):
    """Строка ЦЕНА для ТЗ: вызовы, потолок и продолжительность словами; ни минут, ни токенов не обещаем. Токены — в --detail."""
    return ("ЦЕНА:       ~%s исполнителей (свободная часть %d, резерв %d, потолок %d); прогон %s; "
            "время и токены не обещаем" % (calls_word(e["calls"]), e["free"], e["reserve"], e["ceiling"],
                                          duration_word(e["calls"])))


def duration_word(calls):
    """Продолжительность прогона словами (по числу шагов уровня), без минут: ожидание, а не обещание."""
    if calls <= 3:
        return "очень короткий"
    if calls <= 8:
        return "короткий"
    if calls <= 11:
        return "средний"
    return "долгий"


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
    argv = sys.argv[1:]
    skip = {argv[i + 1] for i, a in enumerate(argv) if a == "--level" and i + 1 < len(argv)}
    args = [a for a in argv if not a.startswith("--") and a not in skip]
    if not args:
        sys.stderr.write(__doc__)
        return 2
    task = args[0].rstrip("/")
    if "--left" in sys.argv:
        return left(task)
    if "--levels" in sys.argv:
        print(levels_table(task))
        return 0
    level = sys.argv[sys.argv.index("--level") + 1] if "--level" in sys.argv else None
    if level is not None and level not in pl.LEVELS:
        print("Уровень: допустимо %s" % ", ".join(pl.LEVELS))
        return 2
    e = estimate(task, level)
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
