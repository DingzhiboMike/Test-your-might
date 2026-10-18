#!/usr/bin/env python3
"""Хук остановки подагента: исполнитель не сдаёт артефакт с ошибками проверок, пока не попробовал их исправить.

SubagentStop. Если в задаче заведён маршрут (state.json) и идёт шаг этой роли (или единственный идущий шаг),
прогоняет по артефакту шага check_artifact (без периметра — его сверяет route.py done по хэшам), check_quotes и
check_fresh. Есть ошибки — один раз не даёт подагенту закончить и показывает их: исправить в том же контексте
дешевле, чем перезапрос. Второй раз подряд (stop_hook_active) не блокирует: дальше решает route.py done.
Пачки (артефакт — маска) не проверяются: в пачке файлы соседей ещё пишутся. С .polygon-dev хук молчит.
"""
import json
import os
import subprocess
import sys

SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPTS)
import trace_lib as tl  # noqa: E402


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    try:
        if data.get("hook_event_name") != "SubagentStop" or data.get("stop_hook_active"):
            return 0
        root = next((c for c in (data.get("cwd"), os.environ.get("CLAUDE_PROJECT_DIR", ""))
                     if c and os.path.exists(os.path.join(c, "AGENTS.md"))), None)
        if not root or os.path.exists(os.path.join(root, ".polygon-dev")):
            return 0
        path = data.get("agent_transcript_path") or ""
        text = tl.usage(path).get("first_text", "") if os.path.isfile(path) else ""
        task = tl.detect_task(text, root)
        if task is None:
            return 0
        st = json.load(open(os.path.join(task, "state.json"), encoding="utf-8"))
        run_ = [s for s in st.get("steps", []) if s.get("status") == "running"]
        role = data.get("agent_type") or ""
        mine = [s for s in run_ if s.get("role") == role] or (run_ if len(run_) == 1 else [])
        if len(mine) != 1 or "*" in mine[0]["artifact"] or "?" in mine[0]["artifact"]:
            return 0
        art = mine[0]["artifact"]
        out = []
        for script, args in (("check_artifact.py", ["--since", str(mine[0]["started"]), "--allow", "*"]),
                             ("check_quotes.py", []), ("check_fresh.py", [])):
            r = subprocess.run([sys.executable, os.path.join(SCRIPTS, script), task, art] + args,
                               capture_output=True, text=True)
            if r.returncode:
                out.append("== %s\n%s" % (script, r.stdout.strip()[-1500:]))
        if out:
            sys.stderr.write("Артефакт %s не прошёл проверки — исправь его и закончи снова:\n\n%s\n" % (art, "\n\n".join(out)))
            return 2
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
