#!/usr/bin/env python3
"""Выборочный аудит итоговых артефактов: три случайных места на артефакт сверяет отдельный проверяющий.

  python3 scripts/audit_sample.py tasks/<папка>           # план аудита: audit-plan.md (места и seed)
  python3 scripts/audit_sample.py tasks/<папка> --check   # audit.md закрывает каждое место плана; строка для сдачи

Скрипты гарантируют форму: цитата есть в источнике, поле заполнено. Держит ли цитата вывод и не подогнано ли поле
под проверку («возражений не найдено — искал: везде»), скрипт не видит. Поэтому после проверок формы — выборка:
по PER_ARTIFACT мест на каждый итоговый артефакт (ARTIFACTS), выбранных случайно, но воспроизводимо (seed — от
имени задачи и хэшей артефактов, записан в плане). Место — строка с опорой («…» [F-id] или [A]) или с вердиктом.

Аудит делает meaning-review в режиме «аудит» в отдельном контексте: файл audit.md с блоком данных «аудит»
(data_block.py) — по каждому месту оценка «держит», «не держит» или «подогнано» и почему. Те же места идут
в служебную часть сдачи: человек может проверить их сам.
"""
import hashlib
import os
import random
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import data_block  # noqa: E402

ARTIFACTS = ("02c-validation.md", "02g-ideas-check.md", "03-backlog.md", "06-research.md", "06-validation.md")
PER_ARTIFACT = 3
PLACE = re.compile(r"«[^»]{8,}»\s*\[(?:F-\d+|A)|^\s*Вердикт\s*:|^\|\s*\d+\s*\|", re.M)
PLAN = "audit-plan.md"
REPORT = "audit.md"


def read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def places(text):
    out, fence = [], False
    for i, line in enumerate(text.split("\n"), 1):
        if line.strip().startswith("```"):
            fence = not fence
            continue
        if not fence and PLACE.search(line):
            out.append((i, line.strip()))
    return out


def plan(task):
    present = [a for a in ARTIFACTS if os.path.exists(os.path.join(task, a))]
    h = hashlib.sha256(os.path.basename(task).encode())
    for a in present:
        h.update(read(os.path.join(task, a)).encode())
    seed = int(h.hexdigest()[:12], 16)
    rnd = random.Random(seed)
    chosen = []
    for a in present:
        cand = places(read(os.path.join(task, a)))
        for n, line in sorted(rnd.sample(cand, min(PER_ARTIFACT, len(cand)))):
            chosen.append({"артефакт": a, "строка": n, "текст": line[:400]})
    return seed, present, chosen


def write_plan(task):
    seed, present, chosen = plan(task)
    out = ["# План аудита: " + os.path.basename(task), "", "seed: %d" % seed,
           "Артефакты: " + (", ".join(present) or "нет"), "",
           "По каждому месту: держит ли фрагмент утверждение и не подогнано ли поле под проверку. Ответ — audit.md с "
           "блоком данных «аудит»: артефакт, строка, оценка (держит / не держит / подогнано), почему.", ""]
    for c in chosen:
        out.append("- %s, строка %d: %s" % (c["артефакт"], c["строка"], c["текст"]))
    with open(os.path.join(task, PLAN), "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    print("Аудит: мест %d в %d артефактах, seed %d — %s" % (len(chosen), len(present), seed, PLAN))
    return 0


def planned(task):
    """Места из audit-plan.md: план фиксируется в момент выборки и не уезжает, если артефакт потом поправили."""
    out = []
    for m in re.finditer(r"^- (\S+), строка (\d+):", read(os.path.join(task, PLAN)), re.M):
        out.append({"артефакт": m.group(1), "строка": int(m.group(2))})
    return out


def check(task):
    if not os.path.exists(os.path.join(task, PLAN)):
        print("аудит: нет %s — сначала python3 scripts/audit_sample.py %s" % (PLAN, task))
        return 1
    chosen = planned(task)
    if not chosen:
        print("Аудит: итоговых артефактов с опорами нет — проверять нечего.")
        return 0
    value, errors = data_block.find(read(os.path.join(task, REPORT)), "аудит")
    got = {(v.get("артефакт"), v.get("строка")): v for v in value or [] if isinstance(v, dict)}
    if value is None and not errors:
        errors.append("нет %s с блоком данных «аудит»" % REPORT)
    for c in chosen:
        if value is not None and (c["артефакт"], c["строка"]) not in got:
            errors.append("место %s:%d из плана не оценено" % (c["артефакт"], c["строка"]))
    counts = {}
    for v in got.values():
        counts[v.get("оценка", "?")] = counts.get(v.get("оценка", "?"), 0) + 1
    for e in errors:
        print("аудит: " + e)
    summary = ", ".join("%s %d" % (k, n) for k, n in sorted(counts.items())) or "оценок нет"
    print("Аудит: мест %d — %s." % (len(chosen), summary))
    return 1 if errors else 0


def main():
    if len(sys.argv) < 2:
        sys.stderr.write(__doc__)
        return 2
    task = sys.argv[1].rstrip("/")
    return check(task) if "--check" in sys.argv else write_plan(task)


if __name__ == "__main__":
    sys.exit(main())
