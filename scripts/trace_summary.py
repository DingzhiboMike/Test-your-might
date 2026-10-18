#!/usr/bin/env python3
"""Сводка расхода задачи по трассе: вызовы, токены и время по ролям и всего.

  python3 scripts/trace_summary.py tasks/<папка>                # таблица по ролям
  python3 scripts/trace_summary.py tasks/<папка> --since <время> # одна строка «Расход: …» за шаг
  python3 scripts/trace_summary.py tasks/<папка> --save         # при сдаче: checks/cost.json и сверка с ЦЕНА
  python3 scripts/trace_summary.py --version                    # строка «Система: <хэш>» для шапки лога

Трассу пишет хук scripts/hooks/trace.py: tasks/<папка>/trace.jsonl (исполнители) и trace-main.json
(основная сессия). Числа — из транскриптов, а не со слов модели. «Новых» — без чтения из кэша.
"""
import json
import os
import re
import sys
from collections import OrderedDict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import trace_lib as tl  # noqa: E402
import cost_estimate as ce  # noqa: E402


def step_line(rows):
    if not rows:
        return "Расход: за шаг трассы нет (исполнитель шёл в основной сессии или хук SubagentStop не сработал)"
    models = sorted({r.get("model") for r in rows if r.get("model")})
    return "Расход: %s, %s токенов (новых %s), %d мин; модель %s" % (
        ce.calls_word(len(rows)), tl.k(sum(tl.total(r) for r in rows)), tl.k(sum(tl.fresh(r) for r in rows)),
        round(max(r.get("sec", 0) for r in rows) / 60), ", ".join(models) or "неизвестна")


def table(task):
    rows = tl.load_trace(task)
    main = tl.load_main(task)
    if not rows and not main:
        print("Трассы нет: хук scripts/hooks/trace.py не подключён или задача шла без подагентов.")
        return 1
    by = OrderedDict()
    for r in rows:
        key = r.get("role", "?") + (" · " + r["mode"] if r.get("mode") else "")
        b = by.setdefault(key, {"n": 0, "tot": 0, "fresh": 0, "sec": 0, "models": set()})
        b["n"] += 1
        b["tot"] += tl.total(r)
        b["fresh"] += tl.fresh(r)
        b["sec"] += r.get("sec", 0)
        if r.get("model"):
            b["models"].add(r["model"])
    print("| Роль | Вызовов | Токенов | Новых | Минут | Модель |")
    print("| --- | --- | --- | --- | --- | --- |")
    for key, b in by.items():
        print("| %s | %d | %s | %s | %d | %s |" % (key, b["n"], tl.k(b["tot"]), tl.k(b["fresh"]),
                                                 round(b["sec"] / 60), ", ".join(sorted(b["models"]))))
    mt = sum(tl.total(v) for v in main.values())
    if main:
        print("| основная сессия | — | %s | %s | %d | %s |" % (
            tl.k(mt), tl.k(sum(tl.fresh(v) for v in main.values())),
            round(sum(v.get("sec", 0) for v in main.values()) / 60),
            ", ".join(sorted({v.get("model") for v in main.values() if v.get("model")}))))
    tot = sum(tl.total(r) for r in rows) + mt
    print("\nВсего: %s исполнителей, %s токенов вместе с основной сессией." % (ce.calls_word(len(rows)), tl.k(tot)))
    versions = sorted({r.get("system") for r in rows if r.get("system")} |
                      {v.get("system") for v in main.values() if v.get("system")})
    if len(versions) > 1:
        print("Внимание: задача шла на разных версиях системы — %s." % ", ".join(versions))
    return 0


def save(task):
    rows = tl.load_trace(task)
    main = tl.load_main(task)
    e = ce.estimate(task)
    tz = ce.read(os.path.join(task, "00-tz.md"))
    line = ce.tz_field(tz, "ЦЕНА")
    m = re.search(r"~(\d+)", line)
    est_calls = int(m.group(1)) if m else e["calls"]
    out = {
        "type": e["type"], "tier": e["tier"], "docs": e["docs"], "interviews": e["interviews"],
        "estimate_calls": est_calls, "calls": len(rows),
        "tokens": sum(tl.total(r) for r in rows), "fresh": sum(tl.fresh(r) for r in rows),
        "main_tokens": sum(tl.total(v) for v in main.values()),
        "system": sorted({r.get("system") for r in rows if r.get("system")}),
    }
    os.makedirs(os.path.join(task, "checks"), exist_ok=True)
    with open(os.path.join(task, "checks", "cost.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    over = (len(rows) - est_calls) / est_calls if est_calls else 0
    msg = "Расход задачи: %s исполнителей из ~%d по ЦЕНА, %s токенов (основная сессия — ещё %s)" % (
        ce.calls_word(len(rows)), est_calls, tl.k(out["tokens"]), tl.k(out["main_tokens"]))
    if over > 0.3:
        msg += "; перерасход %d%% — причину назвать в сдаче" % round(over * 100)
    print(msg)
    return 0


def main():
    if "--version" in sys.argv:
        print("Система: " + tl.system_version(os.path.dirname(HERE)))
        return 0
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.stderr.write(__doc__)
        return 2
    task = args[0].rstrip("/")
    if "--since" in sys.argv:
        i = sys.argv.index("--since")
        since = float(sys.argv[i + 1])
        print(step_line([r for r in tl.load_trace(task) if r.get("ts", 0) >= since]))
        return 0
    if "--save" in sys.argv:
        return save(task)
    return table(task)


if __name__ == "__main__":
    sys.exit(main())
