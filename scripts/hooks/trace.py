#!/usr/bin/env python3
"""Хук трассы Claude Code: расход каждого исполнителя и основной сессии — со слов транскрипта, а не модели.

SubagentStop — подагент закончил: по его транскрипту (agent_transcript_path) считает токены, фактическую
модель и время и пишет строку в tasks/<задача>/trace.jsonl. Задача — первая папка tasks/<имя>/, названная
в вызове подагента; не названа — задача, где за последние 12 часов менялся log.md. Повторное событие того же
агента (его продолжили) заменяет строку, а не добавляет вторую.

Stop — основная сессия закончила ответ: для задач с log.md за последние 12 часов считает расход основной
сессии с первого упоминания папки задачи в транскрипте и пишет tasks/<задача>/trace-main.json (по сессиям).
Если в одной сессии шли две задачи подряд, расход первой включает начало второй.

Ничего не блокирует и ничего не печатает: ошибка разбора — молча выход 0.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import trace_lib as tl  # noqa: E402

WINDOW = 12 * 3600


def project_root(data):
    for c in (data.get("cwd"), os.environ.get("CLAUDE_PROJECT_DIR", ""), os.getcwd()):
        if c and os.path.exists(os.path.join(c, "AGENTS.md")):
            return c
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return here


def recent_tasks(root):
    d = os.path.join(root, "tasks")
    now, out = time.time(), []
    try:
        names = sorted(os.listdir(d))
    except OSError:
        return []
    for name in names:
        log = os.path.join(d, name, "log.md")
        if os.path.isfile(log) and now - os.path.getmtime(log) < WINDOW:
            out.append((os.path.getmtime(log), os.path.join(d, name)))
    return [t for _, t in sorted(out, reverse=True)]


def write_jsonl(path, rows):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def on_subagent(data, root):
    path = data.get("agent_transcript_path") or ""
    if not path or not os.path.isfile(path):
        return
    u = tl.usage(path)
    text = u.pop("first_text", "")
    task = tl.detect_task(text, root)
    if task is None:
        recent = recent_tasks(root)
        task = recent[0] if recent else None
    if task is None:
        return
    rec = {
        "ts": round(time.time()),
        "agent_id": data.get("agent_id", ""),
        "role": tl.detect_role(text, data.get("agent_type", ""), tl.skill_names(root)),
        "mode": tl.detect_mode(text),
        "system": tl.system_version(root),
    }
    rec.update(u)
    rows = [r for r in tl.load_trace(task) if not (rec["agent_id"] and r.get("agent_id") == rec["agent_id"])]
    rows.append(rec)
    write_jsonl(os.path.join(task, "trace.jsonl"), rows)


def first_mention(path, needle):
    for d in tl.read_jsonl(path):
        if needle in json.dumps(d.get("message") or {}, ensure_ascii=False):
            return tl.parse_ts(d.get("timestamp"))
    return None


def on_stop(data, root):
    path = data.get("transcript_path") or ""
    sid = data.get("session_id") or os.path.basename(path)
    if not path or not os.path.isfile(path):
        return
    for task in recent_tasks(root):
        start = first_mention(path, "tasks/" + os.path.basename(task))
        if start is None:
            continue
        u = tl.usage(path, since=start, main_only=True)
        u.pop("first_text", None)
        u["start"] = round(start)
        u["ts"] = round(time.time())
        u["system"] = tl.system_version(root)
        main = tl.load_main(task)
        main[sid] = u
        tmp = os.path.join(task, "trace-main.json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(main, f, ensure_ascii=False, indent=1)
        os.replace(tmp, os.path.join(task, "trace-main.json"))


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    try:
        root = project_root(data)
        ev = data.get("hook_event_name", "")
        if ev == "SubagentStop":
            on_subagent(data, root)
        elif ev == "Stop":
            on_stop(data, root)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
