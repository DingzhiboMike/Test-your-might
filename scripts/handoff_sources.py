#!/usr/bin/env python3
"""Источники сдачи: id в текстах для человека — короткими именами, ссылки и счёт веба — в `08-sources.md`.

  python3 scripts/handoff_sources.py tasks/<папка>

Исполнители и оркестратор пишут опору как обычно: «дословный фрагмент» [F-007] (R-024, check_quotes.py). На финише
скрипт (его зовёт handoff_service.py):
1. в `08-handoff.md`, `02e-position.md`, `03-backlog.md` заменяет [F-007] на короткое имя источника в скобках —
   сайт для веба, тип материала для контекста и интервью (имена файлов могут содержать закрытое, R-017);
2. пишет `08-sources.md`: имя, ссылка (только веб), уровень по web-protocol.md, полнота чтения, где источник стоит
   в выводах; ниже — счёт веба: сколько найдено, сколько дошло до сдачи, где остановились остальные.
Какие id стояли в текстах для человека, скрипт помнит в `checks/sources-used.json`: повторный запуск безопасен.
Перед заменой цитаты сверяются (`check_quotes.py` по задаче): после замены id их уже не сверить. Есть ошибки —
id не трогаются, код возврата 1: сначала исправить цитаты.
"""
import csv
import json
import os
import re
import subprocess
import sys
from urllib.parse import urlparse

HUMAN = ("08-handoff.md", "02e-position.md", "03-backlog.md")
SKIP = ("log.md", "08-service.md", "08-sources.md") + HUMAN
REF = re.compile(r"\s*\[(F-\d+(?:\s*[,;]\s*F-\d+)*)\]")
LEVEL = {"1": "прямая речь", "2": "следы поведения", "3": "отраслевые данные", "4": "вендор"}
READ = {"full": "целиком", "partial": "частично", "snippet": "фрагмент выдачи", "not-read": "не прочитан"}
CTX = {"claim": "утверждение команды", "voice": "прямая речь клиента", "data": "данные проекта",
       "result": "результат живой проверки", "system": "материал прошлой задачи", "other": "материал проекта"}


def read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def registry(task):
    try:
        with open(os.path.join(task, "sources.csv"), encoding="utf-8", newline="") as f:
            return {r["id"]: r for r in csv.DictReader(f)}
    except (OSError, KeyError):
        return {}


def name(row):
    kind = row.get("kind", "")
    if kind == "web":
        host = urlparse(row.get("location", "")).netloc.lower()
        return host[4:] if host.startswith("www.") else host or "веб"
    if kind == "interview":
        return "интервью"
    return CTX.get(row.get("ctx_type", ""), "материал проекта")


def ids_in(text):
    return [i for m in REF.finditer(text) for i in re.findall(r"F-\d+", m.group(1))]


def main():
    if len(sys.argv) < 2:
        sys.stderr.write(__doc__)
        return 2
    task = sys.argv[1].rstrip("/")
    reg = registry(task)
    memo_path = os.path.join(task, "checks", "sources-used.json")
    try:
        used = {k: set(v) for k, v in json.loads(read(memo_path) or "{}").items()}
    except ValueError:
        used = {}

    if any(ids_in(read(os.path.join(task, f))) for f in HUMAN):
        q = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "check_quotes.py"),
                            task], capture_output=True, text=True)
        if q.returncode != 0:
            print("источники: цитаты не сверились (checks/quotes.md) — id в текстах для человека не заменены")
            return 1

    for f in HUMAN:
        path = os.path.join(task, f)
        text = read(path)
        if not text:
            continue
        for i in ids_in(text):
            used.setdefault(i, set()).add(f)

        def repl(m):
            names = []
            for i in re.findall(r"F-\d+", m.group(1)):
                n = name(reg[i]) if i in reg else "источник не в реестре"
                if n not in names:
                    names.append(n)
            return " (%s)" % ", ".join(names)
        new = REF.sub(repl, text)
        if new != text:
            open(path, "w", encoding="utf-8").write(new)

    inner = {}
    for f in sorted(os.listdir(task)):
        if f.endswith(".md") and f not in SKIP and not f.startswith("review-"):
            for i in set(ids_in(read(os.path.join(task, f)))):
                inner.setdefault(i, set()).add(f)

    os.makedirs(os.path.join(task, "checks"), exist_ok=True)
    with open(memo_path, "w", encoding="utf-8") as fh:
        json.dump({k: sorted(v) for k, v in sorted(used.items())}, fh, ensure_ascii=False, indent=1)

    out = ["# Источники сдачи", "",
           "Опоры выводов: имя — как в тексте сдачи, ссылка, насколько источнику верить и прочитан ли он целиком.", "",
           "| Источник | Ссылка | Что это | Прочитан | Где в выводах |", "|---|---|---|---|---|"]
    shown = sorted(set(used) | set(inner), key=lambda i: int(i[2:]))
    for i in shown:
        r = reg.get(i, {})
        link = r.get("location", "") if r.get("kind") == "web" else ""
        what = LEVEL.get(r.get("level", ""), "") if r.get("kind") == "web" else name(r) if r else ""
        where = "сдача" if i in used else "только разбор: " + ", ".join(sorted(inner.get(i, ())))
        out.append("| %s (%s) | %s | %s | %s | %s |" % (name(r) if r else "не в реестре", i, link or "—", what or "—",
                                                       READ.get(r.get("read", ""), "—"), where))
    if not shown:
        out.append("| — | — | — | — | опор с id в выводах нет |")

    web = [i for i, r in reg.items() if r.get("kind") == "web"]
    reached = [i for i in web if i in used]
    stuck = [i for i in web if i not in used and i in inner]
    lost = [i for i in web if i not in used and i not in inner]
    label = lambda ids: ", ".join("%s (%s)" % (name(reg[i]), i) for i in ids) or "—"
    out += ["", "## Веб: что дошло до выводов", "",
            "Найдено в вебе: %d. Дошло до сдачи: %d. Осталось в разборе: %d. Нигде не использовано: %d."
            % (len(web), len(reached), len(stuck), len(lost))]
    if stuck:
        out.append("Осталось в разборе: %s." % label(stuck))
    if lost:
        out.append("Нигде не использовано: %s." % label(lost))
    weak = [i for i in web if reg[i].get("read") in ("snippet", "not-read") or reg[i].get("level") == "4"]
    if weak:
        out.append("Слабые (фрагмент выдачи, не прочитан или вендор): %s." % label(weak))
    open(os.path.join(task, "08-sources.md"), "w", encoding="utf-8").write("\n".join(out) + "\n")
    print("08-sources.md: опор в выводах %d; веб — найдено %d, дошло до сдачи %d" % (len(shown), len(web), len(reached)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
