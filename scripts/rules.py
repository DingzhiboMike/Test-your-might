#!/usr/bin/env python3
"""Реестр правил системы: у каждого правила id, откуда оно, чем проверяется и срабатывает ли.

  python3 scripts/rules.py --assign   # новым правилам — id [R-NNN] в тексте и строка в methodology/rules.csv
  python3 scripts/rules.py --check    # id в тексте и реестр совпадают; у новых правил есть прогон и регрессия
  python3 scripts/rules.py --usage    # сколько раз правило меняло решение по логам задач; кандидаты на удаление

Правило — пункт разделов «Принципы», «Правила» и «Правило непрерывного маршрута» в AGENTS.md и абзац или пункт
с жирным заголовком, кончающимся точкой («**Без повтора на том же входе.** …»), в ядре и маршрутах оркестратора.
id ставится сразу после жирного заголовка или маркера списка и потом не меняется.

Реестр methodology/rules.csv: id, где, правило, добавлено, коммит, прогон (запись system-notes.md, из которой
правило родилось), регрессия (тест selftest, сценарий полигона или «только прогон»), статус (активно / удалено).
У правил до реестра (SINCE) прогон и регрессия — «—»: их происхождение не восстановить честно. Правило, добавленное
позже, без прогона и регрессии не проходит --check — и CI.

Срабатывание — строка лога «Правило: R-NNN — что изменилось», которую пишет оркестратор, когда правило поменяло его
решение. Правило без срабатываний за MIN_RUNS прогонов своих типов выхода — кандидат на удаление; удаляет человек:
строка остаётся в реестре со статусом «удалено» и причиной, id из текста убирается.
"""
import csv
import datetime
import glob
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REG = os.path.join("methodology", "rules.csv")
FIELDS = ["id", "где", "правило", "добавлено", "коммит", "прогон", "регрессия", "статус"]
SINCE = "2026-10-18"
MIN_RUNS = 5
ID = re.compile(r"\[R-(\d{3,})\]")
BOLD_RULE = re.compile(r"^(\s*(?:[-*]|\d+\.)?\s*\*\*[^*\n]{3,160}?\.\*\*)(\s+)(?!\[R-)(\S.*)$")
AGENTS_SECTIONS = ("## Принципы", "## Правила", "## Правило непрерывного маршрута")
# Типы выхода, которых касается файл маршрута; ядро и AGENTS.md — всех.
SCOPE = {
    "routes/hypotheses.md": ("гипотезы", "план проверки", "ТЗ на доработку"),
    "routes/forecast.md": ("гипотезы", "план проверки", "ТЗ на доработку", "исследование"),
    "routes/validation.md": ("валидация",), "routes/research.md": ("исследование",),
    "routes/results.md": ("вердикты по проверке",), "routes/review.md": ("разбор",),
}


def files(root):
    o = os.path.join(root, ".claude", "skills", "orchestrator")
    return ["AGENTS.md", os.path.relpath(os.path.join(o, "SKILL.md"), root)] + sorted(
        os.path.relpath(p, root) for p in glob.glob(os.path.join(o, "routes", "*.md")))


def load(root):
    try:
        with open(os.path.join(root, REG), encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))
    except OSError:
        return []


def save(root, rows):
    with open(os.path.join(root, REG), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def candidates(path, text):
    """[(номер строки, правка строки или None)] — строки-правила без id; правка — строка с местом под id."""
    out, fence, section = [], False, None
    for i, line in enumerate(text.split("\n")):
        if line.strip().startswith("```"):
            fence = not fence
            continue
        if fence or line.lstrip().startswith("|"):
            continue
        if path == "AGENTS.md":
            if line.startswith("## "):
                section = line.strip() if line.strip().startswith(AGENTS_SECTIONS) else None
                continue
            if section and line.startswith("- ") and not ID.search(line):
                m = re.match(r"^(- \*\*[^*\n]+?\*\*)(\s+)(.*)$", line)
                out.append((i, (m.group(1) + " %s " + m.group(3)) if m else ("- %s " + line[2:])))
            continue
        m = BOLD_RULE.match(line)
        if m:
            out.append((i, m.group(1) + " %s " + m.group(3)))
    return out


def lead(line):
    m = re.search(r"\*\*([^*]+)\*\*", line)
    t = m.group(1) if m else re.sub(ID, "", line).lstrip("- ").strip()
    return re.sub(r"\s+", " ", t)[:120]


def blame(root, path, lineno):
    try:
        out = subprocess.run(["git", "-C", root, "blame", "-L", "%d,%d" % (lineno + 1, lineno + 1), "--porcelain",
                              "--", path], capture_output=True, text=True, timeout=10).stdout
        h = out.split()[0][:7] if out else ""
        t = re.search(r"^committer-time (\d+)", out, re.M)
        if h and not h.startswith("0000000") and t:
            return datetime.date.fromtimestamp(int(t.group(1))).isoformat(), h
    except Exception:
        pass
    return datetime.date.today().isoformat(), "не закоммичено"


def assign(root):
    rows = load(root)
    nxt = max([int(r["id"][2:]) for r in rows] + [0]) + 1
    added = 0
    for path in files(root):
        p = os.path.join(root, path)
        lines = open(p, encoding="utf-8").read().split("\n")
        for i, tmpl in candidates(path, "\n".join(lines)):
            rid = "R-%03d" % nxt
            date, commit = blame(root, path, i)
            if date >= SINCE and commit == "не закоммичено":
                date = datetime.date.today().isoformat()
            lines[i] = tmpl % ("[%s]" % rid)
            rows.append({"id": rid, "где": path.replace(".claude/skills/orchestrator/", "orchestrator/"),
                         "правило": lead(lines[i]), "добавлено": date if date < SINCE else SINCE, "коммит": commit,
                         "прогон": "—", "регрессия": "—", "статус": "активно"})
            nxt += 1
            added += 1
        open(p, "w", encoding="utf-8").write("\n".join(lines))
    save(root, rows)
    print("Новых правил с id: %d; всего в реестре: %d." % (added, len(rows)))
    return 0


def ids_in_text(root):
    found = {}
    for path in files(root):
        for m in ID.finditer(open(os.path.join(root, path), encoding="utf-8").read()):
            found.setdefault("R-" + m.group(1), []).append(path)
    return found


def check(root):
    rows, errors = load(root), []
    found = ids_in_text(root)
    byid = {}
    for r in rows:
        if r["id"] in byid:
            errors.append("%s: дважды в реестре" % r["id"])
        byid[r["id"]] = r
        if r["статус"] == "активно" and r["id"] not in found:
            errors.append("%s: в реестре активно, а в тексте его нет — удалено без записи «удалено»" % r["id"])
        if r["статус"] == "удалено" and r["id"] in found:
            errors.append("%s: в реестре удалено, а в тексте осталось" % r["id"])
        if r["статус"] == "активно" and r["добавлено"] > SINCE:
            for f in ("прогон", "регрессия"):
                if r.get(f, "—").strip() in ("", "—", "-"):
                    errors.append("%s: новое правило без поля «%s» — из какого прогона и чем проверяется" % (r["id"], f))
    for rid, where in found.items():
        if rid not in byid:
            errors.append("%s: в тексте (%s), а в реестре нет — python3 scripts/rules.py --assign" % (rid, where[0]))
        if len(where) > 1:
            errors.append("%s: id в тексте дважды (%s)" % (rid, ", ".join(where)))
    for path in files(root):
        n = len(candidates(path, open(os.path.join(root, path), encoding="utf-8").read()))
        if n:
            errors.append("%s: правил без id — %d (python3 scripts/rules.py --assign)" % (path, n))
    return errors


def usage(root):
    rows = [r for r in load(root) if r["статус"] == "активно"]
    fired, runs = {}, {}
    for log in glob.glob(os.path.join(root, "tasks", "*", "log.md")):
        task = os.path.dirname(log)
        tz = open(os.path.join(task, "00-tz.md"), encoding="utf-8").read() if os.path.exists(
            os.path.join(task, "00-tz.md")) else ""
        m = re.search(r"ТИП ВЫХОДА:\s*([^\n]+)", tz)
        kind = (m.group(1).strip().lower() if m else "")
        runs[kind] = runs.get(kind, 0) + 1
        for m in re.finditer(r"Правило:\s*\[?(R-\d{3,})", open(log, encoding="utf-8").read()):
            fired[m.group(1)] = fired.get(m.group(1), 0) + 1
    print("| id | правило | где | срабатываний | прогонов своих типов |\n| --- | --- | --- | --- | --- |")
    cand = []
    for r in rows:
        scope = SCOPE.get(r["где"].replace("orchestrator/", ""), None)
        n_runs = sum(v for k, v in runs.items() if scope is None or any(t.lower() in k for t in scope))
        f = fired.get(r["id"], 0)
        print("| %s | %s | %s | %d | %d |" % (r["id"], r["правило"][:60], r["где"], f, n_runs))
        if f == 0 and n_runs >= MIN_RUNS:
            cand.append(r["id"])
    print("\nКандидаты на удаление (0 срабатываний за %d+ прогонов своих типов): %s" % (MIN_RUNS, ", ".join(cand) or "нет"))
    return 0


def main():
    root = ROOT
    if "--root" in sys.argv:
        root = sys.argv[sys.argv.index("--root") + 1]
    if "--assign" in sys.argv:
        return assign(root)
    if "--check" in sys.argv:
        errors = check(root)
        for e in errors:
            print("правила: " + e)
        if not errors:
            print("Правила: id в тексте и реестр совпадают (%d)." % len(load(root)))
        return 1 if errors else 0
    if "--usage" in sys.argv:
        return usage(root)
    sys.stderr.write(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
