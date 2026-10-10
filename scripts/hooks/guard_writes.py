#!/usr/bin/env python3
"""PreToolUse-хук Claude Code: не даёт агенту по ходу задачи править систему и реестр источников.

Блокирует Write / Edit / MultiEdit / NotebookEdit в:
- .claude/, methodology/, scripts/, AGENTS.md, CLAUDE.md — «скиллы, реестр и указатель по ходу задачи не правятся»;
- context/, кроме context/from-tasks/, — если пишет подагент: контекст кладёт человек (сам или попросив
  основную сессию), исполнители его только читают;
- tasks/*/sources/, tasks/*/sources.csv, tasks/*/checks/ — реестр пишется только scripts/add_source.py,
  отчёты проверок — только скриптами;
- tasks/*/log.md и tasks/*/00-tz.md — если вызов пришёл от подагента (поле agent_id во входе хука;
  если среда его не передаёт, это правило не срабатывает, и периметр ловит scripts/check_artifact.py).

Чтобы править саму систему, создай в корне пустой файл .polygon-dev (в git не попадает) и удали после.
"""
import json
import os
import sys

TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    if data.get("tool_name") not in TOOLS:
        return 0
    root = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd()
    if os.path.exists(os.path.join(root, ".polygon-dev")):
        return 0
    ti = data.get("tool_input") or {}
    target = ti.get("file_path") or ti.get("notebook_path") or ""
    if not target:
        return 0
    rel = os.path.relpath(os.path.abspath(os.path.join(root, target)), os.path.abspath(root))
    if rel.startswith(".."):
        return 0
    parts = rel.split(os.sep)
    reason = None

    if parts[0] in (".claude", "methodology", "scripts") or rel in ("AGENTS.md", "CLAUDE.md"):
        reason = "система по ходу задачи не правится (AGENTS.md, «Правила»). Замечание — в блок «Замечания к системе» сдачи"
    elif parts[0] == "context" and data.get("agent_id") and not (len(parts) > 1 and parts[1] == "from-tasks"):
        reason = "исполнители context/ только читают; материалы задач переносит оркестратор в context/from-tasks/"
    elif parts[0] == "tasks" and len(parts) >= 3:
        sub = parts[2]
        if sub in ("sources", "checks") or sub == "sources.csv":
            reason = "реестр источников пишется только через scripts/add_source.py, отчёты проверок — только скриптами"
        elif sub in ("log.md", "00-tz.md") and data.get("agent_id"):
            reason = "log.md ведёт только оркестратор, 00-tz.md — диспетчер; исполнитель пишет только свой артефакт"

    if reason:
        sys.stderr.write("Запись в {} заблокирована: {}.\n".format(rel, reason))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
