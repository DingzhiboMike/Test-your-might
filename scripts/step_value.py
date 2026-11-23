#!/usr/bin/env python3
"""Шаг маршрута против вывода: сколько шаг стоил и дошло ли его до сдачи.

  python3 scripts/step_value.py tasks/<папка>            # таблица по шагам одной задачи
  python3 scripts/step_value.py tasks/<папка> --final F  # сдача — другой файл (по умолчанию последний артефакт маршрута кроме проверки смысла и аудита)
  python3 scripts/step_value.py --all                    # по ролям, по всем задачам с трассой и маршрутом

Что считается. Идентификаторы в артефакте шага (F-012 — источник, Н-03 — находка, У-2 — утверждение, П-1 — пункт пути,
Г-4, Д-1, М-1) и сколько из них стоит в сдаче. «Только отсюда» — идентификаторы, которые стоят в сдаче и ни в одном
другом артефакте маршрута: без этого шага в сдаче не было бы ни их, ни того, что на них держится. «Сдвиг» — слова в
строке «Результат:» лога шага (опровергается, частично, исправлено, не держит, расхождение): шаг нашёл, что до него
было неверно. Расход — новые токены по трассе (trace.jsonl) за время шага.

Это прокси, а не причинность. Шаг без «только отсюда» и без сдвига — кандидат на разбор, а не на удаление: проверка
смысла и аудит ничего не вводят, их вклад — сдвиг. Причинность даёт только парный прогон без шага; эта сводка
говорит, какие шаги в него брать первыми. Скрипт ничего не оценивает словами и не пишет в задачу.
"""
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import trace_lib as tl  # noqa: E402

ID = re.compile(r"(?<![A-Za-zА-Яа-я0-9])([FНУПГДМ]-\d{1,3})(?![0-9])")
SHIFT = re.compile(r"опроверг|частично|исправ|не держит|расхожд|не совпал|сузить|не подтвержд|перекос", re.I)
SLACK = 90  # секунд: трасса пишется при остановке исполнителя, чуть позже отметки шага


def read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def steps_of(task):
    try:
        with open(os.path.join(task, "state.json"), encoding="utf-8") as f:
            return [s for s in json.load(f).get("steps", []) if s.get("status") == "done"]
    except (OSError, ValueError):
        return []


def results_by_step(task):
    """{номер шага: строка «Результат:»} из log.md."""
    out, cur = {}, None
    for line in read(os.path.join(task, "log.md")).split("\n"):
        m = re.match(r"^ШАГ\s+(\d+)\b", line)
        if m:
            cur = int(m.group(1))
        elif cur and line.startswith("Результат:") and cur not in out:
            out[cur] = line
    return out


def final_of(task, steps, forced=None):
    """Сдача для счёта — последний артефакт маршрута, который не проверка и не аудит. 08-handoff.md не берётся:
    он написан простым языком без идентификаторов, по ним в нём ничего не проследить."""
    if forced:
        return forced
    arts = [s["artifact"] for s in steps if not s["artifact"].startswith(("review-", "audit"))]
    return arts[-1] if arts else None


def analyse(task, forced_final=None):
    """Строки по шагам или None, если у задачи нет маршрута или сдачи."""
    steps = steps_of(task)
    final = final_of(task, steps, forced_final)
    if not steps or not final or not os.path.exists(os.path.join(task, final)):
        return None
    fin = set(ID.findall(read(os.path.join(task, final))))
    ids = {s["n"]: set(ID.findall(read(os.path.join(task, s["artifact"])))) for s in steps if s["artifact"] != final}
    trace = tl.load_trace(task)
    res = results_by_step(task)
    rows = []
    for s in steps:
        if s["artifact"] == final:
            continue
        mine = ids[s["n"]]
        others = set().union(*[v for n, v in ids.items() if n != s["n"]]) if len(ids) > 1 else set()
        spent = [r for r in trace if r.get("role") == s["role"] and
                 (s.get("started") or 0) - SLACK <= r.get("ts", 0) <= (s.get("finished") or 0) + SLACK]
        rows.append({
            "n": s["n"], "role": s["role"], "artifact": s["artifact"],
            "fresh": sum(tl.fresh(r) for r in spent) if spent else None,
            "ids": len(mine), "carried": len(mine & fin), "unique": len((mine & fin) - others),
            "shift": bool(SHIFT.search(res.get(s["n"], ""))), "own_ids": sorted((mine & fin) - others),
        })
    return {"final": final, "rows": rows}


def verdict(r):
    if r["unique"] or r["shift"]:
        return "держит сдачу"
    return "разбор" if r["ids"] or r["fresh"] else "—"


def table(task, forced_final=None):
    a = analyse(task, forced_final)
    if not a:
        print("Шаг и вывод: у задачи нет выполненных шагов в state.json или файла сдачи.")
        return 1
    print("Сдача: %s. Прокси «дошло до сдачи», не причинность.\n" % a["final"])
    print("| Шаг | Роль | Новых токенов | Ид. в артефакте | Дошло до сдачи | Только отсюда | Сдвиг | Итог |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in a["rows"]:
        print("| %d | %s | %s | %d | %d | %d | %s | %s |" % (
            r["n"], r["role"], tl.k(r["fresh"]) if r["fresh"] is not None else "нет трассы", r["ids"], r["carried"],
            r["unique"], "да" if r["shift"] else "нет", verdict(r)))
    return 0


def all_tasks(root):
    by = {}
    for d in sorted(glob.glob(os.path.join(root, "tasks", "*"))):
        a = analyse(d)
        if not a:
            continue
        for r in a["rows"]:
            b = by.setdefault(r["role"], {"tasks": 0, "fresh": 0, "unique": 0, "shift": 0, "idle": 0})
            b["tasks"] += 1
            b["fresh"] += r["fresh"] or 0
            b["unique"] += r["unique"]
            b["shift"] += 1 if r["shift"] else 0
            b["idle"] += 1 if verdict(r) == "разбор" else 0
    if not by:
        print("Шаг и вывод: нет задач с маршрутом и сдачей.")
        return 1
    print("| Роль | Задач | Новых токенов | Только отсюда (сумма) | Задач со сдвигом | Задач «на разбор» |")
    print("| --- | --- | --- | --- | --- | --- |")
    for role, b in sorted(by.items(), key=lambda kv: -kv[1]["fresh"]):
        print("| %s | %d | %s | %d | %d | %d |" % (role, b["tasks"], tl.k(b["fresh"]), b["unique"], b["shift"], b["idle"]))
    print("\nПрокси по идентификаторам и строке «Результат:»; «на разбор» — шаг ничего своего не передал в сдачу и ничего не "
          "сдвинул. Решение — парным прогоном без шага.")
    return 0


def main():
    if "--all" in sys.argv:
        return all_tasks(os.path.dirname(HERE))
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    forced = None
    if "--final" in sys.argv:
        forced = sys.argv[sys.argv.index("--final") + 1]
        args = [a for a in args if a != forced]
    if not args:
        sys.stderr.write(__doc__)
        return 2
    return table(args[0].rstrip("/"), forced)


if __name__ == "__main__":
    sys.exit(main())
