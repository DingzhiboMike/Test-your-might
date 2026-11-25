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
  find -delete/-exec, python3 -c запрещены; curl, trafilatura и keenable — только ролям с сетью;
- WebSearch и WebFetch — не для известных ролей без сети (agent_type из таблицы). Подагент общего типа
  (agent_type не из таблицы) сеть не теряет: роль хук не знает.

Если в задаче заведён маршрут (tasks/<задача>/state.json, его пишет scripts/route.py), подагент пишет в папку задачи
только артефакт идущего шага и маски --allow этого шага; шага нет — запись блокируется: route.py start перед вызовом.

Для всех, включая основную сессию и режим правки системы: WebSearch, WebFetch, MCP Keenable (mcp__keenable__*)
и curl/trafilatura/keenable в Bash не уходят,
если в запросе, адресе или команде есть e-mail, телефон, ИНН, паспорт или термин из private.txt / closed-web.txt
любой задачи (scripts/check_private.py, web_leaks) — проверка до отправки, а не по логу после.

Чтобы править саму систему, создай в корне пустой файл .polygon-dev (в git не попадает) и удали после.

Хук защитный и при сбое закрыт: нечитаемый вход, не загрузившаяся таблица ролей или проверка закрытого — блокировка
с причиной, а не пропуск. Скрипт не найден или упал с исключением — блокирует команда в .claude/settings.json (код 2).
"""
import json
import os
import sys

TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
WEB_TOOLS = {"WebSearch", "WebFetch"}
MCP_WEB_PREFIX = "mcp__keenable__"  # движок Keenable как MCP в основной сессии: та же проверка закрытого

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    import roles as _roles
except Exception:  # таблицы нет — правила подагентов не проверить, и хук их блокирует (bash_reason, web_allowed)
    _roles = None


def known_role(agent_type):
    return _roles is not None and agent_type in _roles.roles()


def web_leak_reason(root, tool, ti):
    """Закрытое во внешнем запросе (scripts/check_private.py, web_leaks) или None. Действует для всех, включая
    основную сессию и режим правки системы: утечка одинакова, кто бы ни отправил."""
    import re
    if tool == "WebSearch":
        query, urls = ti.get("query", ""), list(ti.get("allowed_domains") or []) + list(ti.get("blocked_domains") or [])
    elif tool == "WebFetch":
        query, urls = ti.get("prompt", ""), [ti.get("url", "")]
    elif tool.startswith(MCP_WEB_PREFIX):
        query = " ".join(str(ti.get(k) or "") for k in ("query", "objective", "prompt"))
        urls = [str(u) for u in (ti.get("urls") or [])] + [str(ti.get(k) or "") for k in ("url", "site")]
    else:
        cmd = ti.get("command", "")
        net = {"curl", "wget", "trafilatura", "keenable"}
        net_segs = []  # проверяется только сетевой фрагмент: путь в cd, имена файлов и прочее в сеть не уходят
        for seg in re.split(r"&&|\|\||[;|\n]|\$\(", cmd):
            words = seg.replace("(", " ").split()
            while words and re.match(r"^[A-Z_][A-Z0-9_]*=", words[0]):
                words = words[1:]
            if not words:
                continue
            head = os.path.basename(words[0])
            if head in net or (head in ("python3", "python") and "trafilatura" in words[1:4]):
                net_segs.append(seg)
        if not net_segs:
            return None
        query, urls = "", net_segs
    try:
        import check_private
    except Exception as e:
        return "scripts/check_private.py не загрузился ({}) — закрытое в запросе не проверить".format(e)
    found = check_private.web_leaks(root, query, urls)
    if not found:
        return None
    return ("в запросе закрытое ({}). Замени описанием: «<категория> без названия», респондент — «Интервью N, "
            "сегмент» (methodology/web-protocol.md, п. 2)").format("; ".join(found))


def web_allowed(agent_type):
    if _roles is None:
        return False
    return not known_role(agent_type) or agent_type in _roles.WEB


def bash_reason(cmd, agent_type):
    """Причина запрета команды подагента или None."""
    import re
    if _roles is None:
        return "таблица ролей scripts/roles.py не загрузилась — права исполнителя не проверить"
    # путь к скрипту системы в кавычках или с экранированным пробелом (папка проекта с пробелом в имени) — это тот же
    # скрипт scripts/…: каталог перед ним не проверяем (как и у пути без кавычек), форму самого скрипта — да
    cmd = re.sub(r"""["'][^"']*?(scripts/[\w/.-]+\.py)["']""", r"\1", cmd.replace("\\ ", "_"))
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
    except Exception as e:
        sys.stderr.write("Хук записи: вход не читается как JSON ({}) — действие заблокировано.\n".format(e))
        return 2
    tool = data.get("tool_name")
    mcp_web = bool(tool) and tool.startswith(MCP_WEB_PREFIX)
    if tool not in TOOLS and tool not in WEB_TOOLS and tool != "Bash" and not mcp_web:
        return 0
    root = project_root(data)
    if tool in WEB_TOOLS or tool == "Bash" or mcp_web:
        leak = web_leak_reason(root, tool, data.get("tool_input") or {})
        if leak:
            sys.stderr.write("{} заблокирован: {}.\n".format(tool, leak))
            return 2
    if mcp_web:
        return 0  # подагенты MCP не получают (набор — scripts/roles.py); основной сессии — только проверка закрытого
    if os.path.exists(os.path.join(root, ".polygon-dev")):
        return 0
    agent_type = data.get("agent_type") or ""
    if tool in WEB_TOOLS:
        if data.get("agent_id") and not web_allowed(agent_type):
            why = "у роли {} нет доступа к сети".format(agent_type) if _roles is not None else "таблица ролей не загрузилась"
            sys.stderr.write("{} заблокирован: {} (scripts/roles.py).\n".format(tool, why))
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
    if parts[0] == "tasks" and len(parts) >= 3 and not data.get("agent_id"):
        note_orchestrator_write(os.path.join(root, "tasks", parts[1]), "/".join(parts[2:]))
    return 0


def note_orchestrator_write(task_dir, inner):
    """Запись основной сессии в файл задачи, пока идёт шаг, — в checks/orchestrator-writes.jsonl. route.py done не
    считает такой файл нарушением периметра, но выводит его отдельной строкой. Подагенту чужие файлы этот хук и так
    не даёт, так что след оставляет только оркестратор. Учётное, а не защитное: не записалось — периметр строже, не
    мягче."""
    import time
    masks = step_masks(task_dir)
    if not masks:
        return
    try:
        os.makedirs(os.path.join(task_dir, "checks"), exist_ok=True)
        with open(os.path.join(task_dir, "checks", "orchestrator-writes.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": round(time.time()), "path": inner}, ensure_ascii=False) + "\n")
    except OSError:
        pass


if __name__ == "__main__":
    sys.exit(main())
