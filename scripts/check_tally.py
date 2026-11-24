#!/usr/bin/env python3
"""Учёт срабатываний проверок по задачам: сколько раз каждая проверка запускалась, срабатывала и чем это кончилось.

  python3 scripts/check_tally.py [tasks/ | tasks/<папка> …]      # по умолчанию — все задачи в tasks/

Источники — то, что уже пишут скрипты, а не лог оркестратора:
- `state.json` (route.py): строка «Проверки:» каждого шага, ошибки периметра, `recheck` (правка оркестратора и прежняя
  строка проверок), `waived` (принято с оговоркой), перезапрос — более поздний шаг с тем же артефактом, сданный успешно;
- `checks/gate.jsonl` (хук step_gate.py): проверки, с которыми артефакт один раз вернули исполнителю до закрытия шага;
- `checks/orchestrator-writes.jsonl` (хук guard_writes.py): правки оркестратора во время шага — не ошибки периметра.

Столбцы: запусков (строк «Проверки:», включая перепроверки); вернул хук (исполнитель исправлял сам); сработала на
закрытии шага; дальше — исход срабатывания: перепроверка после правки оркестратора, перезапрос исполнителя, принято
с оговоркой, осталось (шаг с ошибкой не снят). «Предупреждения» профиля в срабатывания не входят.

Исход — признак, а не вердикт: «принято с оговоркой» и «перепроверка» часто значат ложное срабатывание, «перезапрос» —
настоящее, но решает человек по причинам, которые скрипт печатает под таблицей. Скрипт ничего не пишет.
"""
import glob
import json
import os
import re
import sys
from collections import defaultdict

CHECK = re.compile(r"(check_\w+)(?: [\w.*?-]+)? — (ок|ОШИБКИ|предупреждения)")
COLS = ("запусков", "вернул хук", "сработала", "перепроверка", "перезапрос", "принято с оговоркой", "осталось")


def task_dirs(args):
    out = []
    for a in args or ["tasks"]:
        a = a.rstrip("/")
        if os.path.exists(os.path.join(a, "state.json")):
            out.append(a)
        else:
            out += sorted(os.path.dirname(p) for p in glob.glob(os.path.join(a, "*", "state.json")))
    return out


def statuses(line):
    """{проверка: статус} из строки «Проверки:»; у проверки по нескольким файлам худший статус."""
    out = {}
    for name, st in CHECK.findall(line or ""):
        if out.get(name) != "ОШИБКИ":
            out[name] = st
    return out


def read_jsonl(path):
    try:
        with open(path, encoding="utf-8") as f:
            return [json.loads(l) for l in f if l.strip()]
    except (OSError, ValueError):
        return []


def tally(dirs):
    rows = defaultdict(lambda: dict.fromkeys(COLS, 0))
    reasons = defaultdict(list)
    for task in dirs:
        try:
            st = json.load(open(os.path.join(task, "state.json"), encoding="utf-8"))
        except (OSError, ValueError):
            continue
        steps = st.get("steps", [])
        name = os.path.basename(task)
        for s in steps:
            lines = [r.get("checks_before", "") for r in s.get("recheck", [])] + [s.get("checks", "")]
            for line in lines:
                for chk in statuses(line):
                    rows[chk]["запусков"] += 1
            first = statuses(lines[0])
            fired = [c for c, v in first.items() if v == "ОШИБКИ"]
            if s.get("errors"):
                fired.append("периметр")
            if not fired:
                continue
            retried = any(x["n"] > s["n"] and x.get("status") == "done" and x.get("artifact") == s.get("artifact")
                          for x in steps)
            if s.get("recheck"):
                outcome, why = "перепроверка", s["recheck"][0].get("fixed", "")
            elif s.get("waived"):
                outcome, why = "принято с оговоркой", s["waived"]
            elif retried:
                outcome, why = "перезапрос", ""
            else:
                outcome, why = "осталось", ""
            for chk in fired:
                rows[chk]["сработала"] += 1
                rows[chk][outcome] += 1
                if why:
                    reasons[chk].append("%s, шаг %d (%s): %s" % (name, s["n"], outcome, why[:160]))
        for rec in read_jsonl(os.path.join(task, "checks", "gate.jsonl")):
            for chk in rec.get("checks", []):
                rows[chk]["вернул хук"] += 1
        orch = read_jsonl(os.path.join(task, "checks", "orchestrator-writes.jsonl"))
        if orch:
            reasons["периметр"].append("%s: правок оркестратора во время шагов %d (не ошибки)" % (name, len(orch)))
    return rows, reasons


def main():
    dirs = task_dirs(sys.argv[1:])
    if not dirs:
        print("Задач с state.json нет: считать нечего.")
        return 0
    rows, reasons = tally(dirs)
    order = sorted(rows, key=lambda c: (-rows[c]["сработала"], -rows[c]["вернул хук"], c))
    print("# Учёт срабатываний проверок\n\nЗадач: %d.\n" % len(dirs))
    print("| Проверка | " + " | ".join(COLS) + " |")
    print("|---" * (len(COLS) + 1) + "|")
    for c in order:
        print("| %s | %s |" % (c, " | ".join(str(rows[c][k]) for k in COLS)))
    if reasons:
        print("\n## Причины перепроверок и оговорок\n")
        for c in order:
            for r in reasons.get(c, []):
                print("- %s — %s" % (c, r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
