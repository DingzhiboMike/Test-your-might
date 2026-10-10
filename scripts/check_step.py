#!/usr/bin/env python3
"""Все проверки после шага одной командой и одной строкой для лога.

  python3 scripts/check_step.py tasks/<папка> <артефакт> --since <время> [ключи check_artifact]

Запускает по очереди:
- check_artifact.py — с теми же аргументами (--since, --allow, --review, --contains; маска для пачки);
- check_quotes.py — по каждому файлу артефакта (маска раскрывается);
- check_private.py — по задаче;
- check_numbers.py — по задаче, если есть numbers.csv.

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


def main():
    if len(sys.argv) < 3:
        sys.stderr.write(__doc__)
        return 2
    task, artifact, rest = sys.argv[1].rstrip("/"), sys.argv[2], sys.argv[3:]
    files = sorted(os.path.basename(p) for p in glob.glob(os.path.join(task, artifact))) or [artifact]
    checks = [("check_artifact", run("check_artifact.py", [task, artifact] + rest))]
    for f in files:
        checks.append(("check_quotes " + f if len(files) > 1 else "check_quotes", run("check_quotes.py", [task, f])))
    checks.append(("check_private", run("check_private.py", [task])))
    if os.path.exists(os.path.join(task, "numbers.csv")):
        checks.append(("check_numbers", run("check_numbers.py", [task])))

    parts = []
    for n, (code, last, out) in checks:
        part = "%s — %s" % (n, "ок" if code == 0 else "ОШИБКИ")
        detail = [quote_counts(out)] if n.startswith("check_quotes") else []
        if code != 0:
            detail.append(last)
        parts.append(part + (" (%s)" % "; ".join(detail) if detail else ""))
    print("Проверки: " + "; ".join(parts))
    failed = [(n, out) for n, (code, _, out) in checks if code != 0]
    for n, out in failed:
        print("\n== %s\n%s" % (n, out))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
