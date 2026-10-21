#!/usr/bin/env python3
"""Все проверки после шага одной командой и одной строкой для лога.

  python3 scripts/check_step.py tasks/<папка> <артефакт> --since <время> [ключи check_artifact]

Запускает по очереди:
- check_artifact.py — с теми же аргументами (--since, --allow, --review, --contains; маска для пачки);
- check_quotes.py — по каждому файлу артефакта (маска раскрывается);
- check_fresh.py — старые веб-источники в артефакте стоят с годом в тексте;
- check_private.py — по задаче;
- check_numbers.py — по задаче, если есть numbers.csv;
- trace_summary.py --since — строка «Расход: …» за шаг из трассы (хук scripts/hooks/trace.py).

Печатает строку «Проверки: …» — её и пиши в лог. У check_quotes в строке счётчики: цитат, без id, источников,
независимых корней — по ним видно, на скольких независимых опорах стоит артефакт. Ниже — полный вывод только тех
проверок, где есть ошибки.
Код возврата 1, если хоть одна проверка нашла ошибку: дальше — перезапрос по правилам оркестратора.
Ничего нового не проверяет: только запускает существующие скрипты.
"""
import glob
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import profile_lib  # noqa: E402
SOFT = ("check_quotes", "check_fresh", "check_numbers")  # не блокируют при evidence: none|links


def run(name, args):
    r = subprocess.run([sys.executable, os.path.join(HERE, name)] + args, capture_output=True, text=True)
    out = (r.stdout + r.stderr).strip()
    last = next((l.strip() for l in reversed(out.splitlines()) if l.strip()), "")
    return r.returncode, last, out


def quote_counts(out):
    """Сводит счётчики из отчёта check_quotes по всем разделам артефактов."""
    n = sum(int(x) for x in re.findall(r"цитат проверено: (\d+)", out))
    loose = sum(int(x) for x in re.findall(r"цитат без id источника — (\d+)", out))
    src = sum(int(x) for x in re.findall(r"- источников: (\d+)", out))
    roots = sum(int(x) for x in re.findall(r"независимых корней: (\d+)", out))
    return "цитат %d, без id %d, источников %d, корней %d" % (n, loose, src, roots)


def soft_n(n, task):
    return n.startswith(SOFT) and not profile_lib.strict_evidence(task)


def main():
    if len(sys.argv) < 3:
        sys.stderr.write(__doc__)
        return 2
    task, artifact, rest = sys.argv[1].rstrip("/"), sys.argv[2], sys.argv[3:]
    files = sorted(os.path.basename(p) for p in glob.glob(os.path.join(task, artifact))) or [artifact]
    checks = [("check_artifact", run("check_artifact.py", [task, artifact] + rest))]
    for f in files:
        checks.append(("check_quotes " + f if len(files) > 1 else "check_quotes", run("check_quotes.py", [task, f])))
    checks.append(("check_fresh", run("check_fresh.py", [task, artifact])))
    checks.append(("check_private", run("check_private.py", [task])))
    if os.path.exists(os.path.join(task, "numbers.csv")):
        checks.append(("check_numbers", run("check_numbers.py", [task])))

    parts = []
    for n, (code, last, out) in checks:
        part = "%s — %s" % (n, "ок" if code == 0 else ("предупреждения (профиль: опоры не строгие)" if soft_n(n, task) else "ОШИБКИ"))
        detail = [quote_counts(out)] if n.startswith("check_quotes") else []
        if code != 0:
            detail.append(last)
        parts.append(part + (" (%s)" % "; ".join(detail) if detail else ""))
    print("Проверки: " + "; ".join(parts))
    if os.path.exists(os.path.join(task, "trace.jsonl")) and "--since" in rest:
        since = rest[rest.index("--since") + 1]
        print(run("trace_summary.py", [task, "--since", since])[1])
    elif "--since" in rest:
        art_kb = sum(os.path.getsize(f) for f in glob.glob(os.path.join(task, artifact)) if os.path.isfile(f)) // 1024
        task_kb = sum(os.path.getsize(os.path.join(b, n)) for b, _, fs in os.walk(task) for n in fs
                      if n not in ("state.json", ".DS_Store") and "sources" not in b.split(os.sep)
                      and "map" not in b.split(os.sep)) // 1024
        print("Расход: трассы нет — оценка по объёму: артефакт %d КБ, файлы задачи без источников и карты %d КБ. "
              "Хук трассы не сработал: открой Claude Code в корне проекта (там .claude/settings.json), проверь `python3 scripts/check_env.py`"
              % (art_kb, task_kb))
    soft = not profile_lib.strict_evidence(task)
    failed = [(n, out) for n, (code, _, out) in checks if code != 0 and not (soft and n.startswith(SOFT))]
    for n, out in failed:
        print("\n== %s\n%s" % (n, out))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
