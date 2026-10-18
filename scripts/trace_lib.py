#!/usr/bin/env python3
"""Расход вызовов по транскриптам Claude Code — общая часть для хука трассы, сводки и оценки цены.

Транскрипт — JSONL, строка на событие. У ответа модели (type: assistant) есть message.id, message.model и
message.usage; один ответ пишется несколькими строками с одним id и одинаковым usage, поэтому счёт — по
уникальным id. Токены: in — новые на входе, cache_write — записанные в кэш, cache_read — прочитанные из кэша,
out — на выходе. «Всего» — сумма четырёх, «новых» — всё, кроме чтения из кэша.
"""
import json
import os
import re
import subprocess
from collections import Counter
from datetime import datetime

KEYS = ("in", "cache_write", "cache_read", "out")
GENERIC_AGENTS = {"", "general-purpose", "Explore", "Plan", "claude", "fork"}


def read_jsonl(path):
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except ValueError:
                    continue
    except OSError:
        return


def parse_ts(s):
    """ISO-время транскрипта → секунды; не разобралось — None."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def message_text(d):
    """Текст сообщения пользователя: строка или текстовые блоки."""
    c = (d.get("message") or {}).get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "\n".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
    return ""


def usage(path, since=None, main_only=False):
    """Расход по транскрипту. since — учитывать ответы не раньше этого времени; main_only — без побочных веток."""
    seen, tot, models = set(), dict.fromkeys(KEYS, 0), Counter()
    first = last = None
    first_text = ""
    for d in read_jsonl(path):
        if main_only and d.get("isSidechain"):
            continue
        t = parse_ts(d.get("timestamp"))
        if since is not None and (t is None or t < since):
            continue
        if not first_text and d.get("type") == "user":
            first_text = message_text(d)
        if t is not None:
            first = t if first is None else min(first, t)
            last = t if last is None else max(last, t)
        if d.get("type") != "assistant":
            continue
        m = d.get("message") or {}
        u = m.get("usage")
        mid = m.get("id") or d.get("uuid")
        if not u or mid in seen:
            continue
        seen.add(mid)
        tot["in"] += int(u.get("input_tokens") or 0)
        tot["cache_write"] += int(u.get("cache_creation_input_tokens") or 0)
        tot["cache_read"] += int(u.get("cache_read_input_tokens") or 0)
        tot["out"] += int(u.get("output_tokens") or 0)
        if m.get("model") and m.get("model") != "<synthetic>":
            models[m["model"]] += 1
    rec = dict(tot)
    rec["responses"] = len(seen)
    rec["model"] = models.most_common(1)[0][0] if models else ""
    rec["models"] = sorted(models)
    rec["sec"] = round(last - first) if first is not None and last is not None else 0
    rec["first_text"] = first_text
    return rec


def total(rec):
    return sum(int(rec.get(k) or 0) for k in KEYS)


def fresh(rec):
    return total(rec) - int(rec.get("cache_read") or 0)


def skill_names(root):
    d = os.path.join(root, ".claude", "skills")
    try:
        return sorted(n for n in os.listdir(d) if os.path.isfile(os.path.join(d, n, "SKILL.md")))
    except OSError:
        return []


def detect_role(text, agent_type, skills):
    """Роль исполнителя: имя подагента, если оно своё; иначе первый скилл, названный в вызове."""
    if agent_type and agent_type not in GENERIC_AGENTS:
        return agent_type
    best = None
    for name in skills:
        m = re.search(r"\.claude/skills/%s/" % re.escape(name), text)
        pos = m.start() if m else None
        if pos is None:
            m = re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(name), text)
            pos = m.start() + 100000 if m else None  # имя без пути — слабее, чем путь к SKILL.md
        if pos is not None and (best is None or pos < best[0]):
            best = (pos, name)
    return best[1] if best else (agent_type or "неизвестно")


def detect_mode(text):
    m = re.search(r"режим[еау]?\s+«([^»]{1,60})»", text)
    return m.group(1) if m else ""


def detect_task(text, root):
    """Папка задачи из текста вызова: первая tasks/<имя>/, которая есть на диске."""
    for m in re.finditer(r"tasks/([^/\s`'\"«»()<>]+)", text):
        p = os.path.join(root, "tasks", m.group(1))
        if os.path.isdir(p):
            return p
    return None


def system_version(root):
    """Хэш коммита системы; незакоммиченные правки системы (без tasks/ и context/) — с пометкой «+правки»."""
    try:
        h = subprocess.run(["git", "-C", root, "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                           timeout=5).stdout.strip()
        dirty = subprocess.run(["git", "-C", root, "status", "--porcelain", "--", ".", ":!tasks", ":!context"],
                               capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:
        return "неизвестно"
    if not h:
        return "неизвестно"
    return h + ("+правки" if dirty else "")


def approved(task):
    """В 00-tz.md есть строка СОГЛАСОВАНО — оркестратор может начинать."""
    try:
        with open(os.path.join(task, "00-tz.md"), encoding="utf-8") as f:
            return bool(re.search(r"^\W*СОГЛАСОВАНО", f.read(), re.M))
    except OSError:
        return False


def load_trace(task):
    return list(read_jsonl(os.path.join(task, "trace.jsonl")))


def load_main(task):
    try:
        with open(os.path.join(task, "trace-main.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def k(n):
    """Токены по-человечески: 85 тыс., 2,6 млн."""
    n = float(n)
    if n >= 1e6:
        return ("%.1f млн" % (n / 1e6)).replace(".", ",")
    return "%d тыс." % round(n / 1e3)
