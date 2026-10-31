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

Для подагентов (во входе хука есть agent_id) ещё два правила, по таблице ролей scripts/roles.py:
- Bash — только скрипты системы (python3 scripts/…) и команды чтения; запись в файл перенаправлением, sed -i,
  find -delete/-exec, python3 -c запрещены; curl и trafilatura — только ролям с сетью;
- WebSearch и WebFetch — не для известных ролей без сети (agent_type из таблицы). Подагент общего типа
  (agent_type не из таблицы) сеть не теряет: роль хук не знает.

Если в задаче заведён маршрут (tasks/<задача>/state.json, его пишет scripts/route.py), подагент пишет в папку задачи
только артефакт идущего шага и маски --allow этого шага; шага нет — запись блокируется: route.py start перед вызовом.

Для всех, включая основную сессию и режим правки системы: WebSearch, WebFetch и curl/trafilatura в Bash не уходят,
если в запросе, адресе или команде есть e-mail, телефон, ИНН, паспорт или термин из private.txt / closed-web.txt
любой задачи (scripts/check_private.py, web_leaks) — проверка до отправки, а не по логу после.

Чтобы править саму систему, создай в корне пустой файл .polygon-dev (в git не попадает) и удали после.
"""
import json
import os
import sys

TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
WEB_TOOLS = {"WebSearch", "WebFetch"}

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    import roles as _roles
except Exception:  # хук не должен падать, если таблицы нет
    _roles = None


def known_role(agent_type):
    return _roles is not None and agent_type in _roles.roles()


def web_leak_reason(root, tool, ti):
    """Закрытое во внешнем запросе (scripts/check_private.py, web_leaks) или None. Действует для всех, включая
    основную сессию и режим правки системы: утечка одинакова, кто бы ни отправил."""
    import re
    try:
        import check_private
    except Exception:
        return None
    if tool == "WebSearch":
        query, urls = ti.get("query", ""), list(ti.get("allowed_domains") or []) + list(ti.get("blocked_domains") or [])
    elif tool == "WebFetch":
        query, urls = ti.get("prompt", ""), [ti.get("url", "")]
    else:
        cmd = ti.get("command", "")
        heads = []
        for seg in re.split(r"&&|\|\||[;|\n]|\$\(", cmd):
            words = seg.replace("(", " ").split()
            while words and re.match(r"^[A-Z_][A-Z0-9_]*=", words[0]):
                words = words[1:]
            if words:
                heads.append(os.path.basename(words[0]))
                if heads[-1] in ("python3", "python") and "trafilatura" in words[1:4]:
                    heads.append("trafilatura")
        if not set(heads) & {"curl", "wget", "trafilatura"}:
            return None
        query, urls = "", [cmd]
    found = check_private.web_leaks(root, query, urls)
    if not found:
        return None
    return ("в запросе закрытое ({}). Замени описанием: «<категория> без названия», респондент — «Интервью N, "
            "сегмент» (methodology/web-protocol.md, п. 2)").format("; ".join(found))


def web_allowed(agent_type):
    return not known_role(agent_type) or agent_type in _roles.WEB


def bash_reason(cmd, agent_type):
    """Причина запрета команды подагента или None."""
    import re
    if _roles is None:
        return None
    text = re.sub(r"'[^']*'", "''", cmd)
    text = re.sub(r'"(?:[^"\\]|\\.)*"', "''", text)
    text = re.sub(r"\d?>>?\s*/dev/null|2>&1|>&2", " ", text)
    if ">" in text:
        return "запись в файл перенаправлением: исполнитель пишет свой артефакт через Write"
    if "`" in text:
        return "подстановка команды в обратных кавычках"
    for seg in re.split(r"&&|\|\||[;|\n]|\$\(", text):
        words = seg.replace("(", " ").replace(")", " ").split()
        while words and re.match(r"^[A-Z_][A-Z0-9_]*=", words[0]):
            words = words[1:]
        if not words:
            continue
        head = os.path.basename(words[0])
        if head in ("python3", "python"):
            args = [w for w in words[1:] if w not in ("-I", "-u", "-B")]
            if args[:2] == ["-m", "trafilatura"] and web_allowed(agent_type):
                continue
            if not args or not re.search(r"(^|/)scripts/[\w/.-]+\.py$", args[0]):
                return "python3 — только скрипты системы scripts/…"
            continue
        if head in _roles.WEB_COMMANDS:
            if web_allowed(agent_type):
                continue
            return "у роли %s нет доступа к сети" % agent_type
        if head not in _roles.ALLOWED_COMMANDS:
            return "команда «%s» не из списка разрешённых исполнителю (scripts/roles.py)" % head
        if head == "sed" and re.search(r"(^|\s)-\w*i", seg):
            return "sed -i меняет файлы"
        if head == "find" and re.search(r"-delete|-exec|-ok", seg):
            return "find с -delete или -exec"
    return None



def step_masks(task_dir):
    """Маски записи идущих шагов; None — маршрута в коде нет."""
    try:
        with open(os.path.join(task_dir, "state.json"), encoding="utf-8") as f:
            st = json.load(f)
    except (OSError, ValueError):
        return None
    masks = []
    for step in st.get("steps", []):
        if step.get("status") == "running":
            masks += [step.get("artifact", "")] + list(step.get("allow", []))
    return masks


def project_root(data):
    """Корень проекта. CLAUDE_PROJECT_DIR бывает пустым или устаревшим после смены папки в сессии, поэтому сначала —
    рабочая папка сессии из события хука и её git-корень, потом переменная, потом текущая папка."""
    import subprocess
    candidates = []
    cwd = data.get("cwd")
    if cwd:
        try:
            top = subprocess.run(["git", "-C", cwd, "rev-parse", "--show-toplevel"], capture_output=True,
                                 text=True, timeout=5).stdout.strip()
        except Exception:
            top = ""
        candidates += [top, cwd]
    for c in candidates:
        if c and os.path.exists(os.path.join(c, "AGENTS.md")):
            return c
    env = os.environ.get("CLAUDE_PROJECT_DIR", "")
    if env and os.path.isdir(env):
        return env
    return os.getcwd()

def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    tool = data.get("tool_name")
    if tool not in TOOLS and tool not in WEB_TOOLS and tool != "Bash":
        return 0
    root = project_root(data)
    if tool in WEB_TOOLS or tool == "Bash":
        leak = web_leak_reason(root, tool, data.get("tool_input") or {})
        if leak:
            sys.stderr.write("{} заблокирован: {}.\n".format(tool, leak))
            return 2
    if os.path.exists(os.path.join(root, ".polygon-dev")):
        return 0
    agent_type = data.get("agent_type") or ""
    if tool in WEB_TOOLS:
        if data.get("agent_id") and not web_allowed(agent_type):
            sys.stderr.write("{} заблокирован: у роли {} нет доступа к сети (scripts/roles.py).\n".format(tool, agent_type))
            return 2
        return 0
    if tool == "Bash":
        if not data.get("agent_id"):
            return 0
        reason = bash_reason((data.get("tool_input") or {}).get("command", ""), agent_type)
        if reason:
            sys.stderr.write("Команда заблокирована: {}.\n".format(reason))
            return 2
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
        elif data.get("agent_id"):
            import fnmatch
            masks = step_masks(os.path.join(root, "tasks", parts[1]))
            inner = "/".join(parts[2:])
            if masks is not None and not any(m and fnmatch.fnmatch(inner, m) for m in masks):
                reason = ("файл вне периметра идущего шага (%s)" % ", ".join(m for m in masks if m) if masks else
                          "шаг не зарегистрирован: оркестратор запускает route.py start перед вызовом")

    if reason:
        sys.stderr.write("Запись в {} заблокирована: {}.\n".format(rel, reason))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
