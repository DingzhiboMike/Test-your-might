#!/usr/bin/env python3
"""Stop-хук Claude Code: перед тем как агент закончит ответ, сам прогоняет проверку цитат, чисел и персональных данных.

Проверка не зависит от того, вспомнил ли о ней оркестратор. Для каждой задачи, в которой за последние
12 часов что-то менялось и есть реестр источников, хук запускает scripts/check_quotes.py по всем
артефактам. Отчёт обновляется в tasks/<задача>/checks/quotes.md.

Есть ошибки — хук один раз не даёт закончить ответ и показывает агенту, что не так: исправить,
или перечислить ошибки в сдаче как незакрытое (строка «опоры»). Второй раз подряд не блокирует
(stop_hook_active), чтобы не было петли: решение, что делать с оставшимися ошибками, за человеком.

С файлом .polygon-dev в корне хук молчит.
"""
import json
import os
import subprocess
import sys
import time

WINDOW = 12 * 3600


def recent_tasks(root):
    tasks_dir = os.path.join(root, "tasks")
    if not os.path.isdir(tasks_dir):
        return []
    now, out = time.time(), []
    for name in sorted(os.listdir(tasks_dir)):
        task = os.path.join(tasks_dir, name)
        if not os.path.isfile(os.path.join(task, "sources.csv")):
            continue
        newest = max((os.path.getmtime(os.path.join(task, f)) for f in os.listdir(task) if f.endswith(".md")), default=0)
        if now - newest < WINDOW:
            out.append(task)
    return out


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}
    root = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd()
    if os.path.exists(os.path.join(root, ".polygon-dev")):
        return 0
    if data.get("stop_hook_active"):
        return 0
    script = os.path.join(root, "scripts", "check_quotes.py")
    nscript = os.path.join(root, "scripts", "check_numbers.py")
    if not os.path.exists(script):
        return 0

    problems = []
    for task in recent_tasks(root):
        lines = []
        r = subprocess.run([sys.executable, script, task], capture_output=True, text=True, cwd=root)
        if r.returncode == 1:
            lines += [l for l in r.stdout.splitlines() if l.startswith("- ОШИБКА") or l.startswith("## ")]
        if os.path.exists(nscript) and os.path.exists(os.path.join(task, "numbers.csv")):
            r2 = subprocess.run([sys.executable, nscript, task], capture_output=True, text=True, cwd=root)
            if r2.returncode == 1:
                body = r2.stdout.split("## Ошибки", 1)[1].split("##", 1)[0] if "## Ошибки" in r2.stdout else ""
                lines += ["числа:" + l[1:] for l in body.splitlines() if l.startswith("- ") and "нет" != l[2:].strip()]
        pscript = os.path.join(root, "scripts", "check_private.py")
        if os.path.exists(pscript):
            r3 = subprocess.run([sys.executable, pscript, task], capture_output=True, text=True, cwd=root)
            if r3.returncode == 1:
                body = r3.stdout.split("## Ошибки", 1)[1].split("##", 1)[0] if "## Ошибки" in r3.stdout else ""
                lines += ["персональные данные:" + l[1:] for l in body.splitlines() if l.startswith("- ") and l[2:].strip() != "нет"]
        if lines:
            problems.append((os.path.relpath(task, root), lines))

    if not problems:
        return 0
    msg = ["Проверка цитат, чисел и персональных данных перед окончанием ответа нашла ошибки (scripts/check_quotes.py, check_numbers.py, check_private.py):"]
    for task, lines in problems:
        msg.append("")
        msg.append(task + " — отчёты в " + os.path.join(task, "checks"))
        msg += lines[:20]
        if len(lines) > 20:
            msg.append("… и ещё {}".format(len(lines) - 20))
    msg += ["",
            "Если маршрут ещё идёт — исправь: найди верный фрагмент, сними утверждение или пометь «первоисточник не прочитан».",
            "Персональные данные: замени имена на «Интервью N, сегмент», сократи цитату через «…» так, чтобы личное не попало; "
            "в запросах в веб личного нет вообще.",
            "Если это сдача или остановка — перечисли эти ошибки в сдаче как незакрытое, в строке «опоры».",
            "Объявлять их ложными срабатываниями нельзя."]
    sys.stderr.write("\n".join(msg) + "\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
