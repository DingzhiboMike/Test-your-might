#!/usr/bin/env python3
"""Служебная сдача `08-service.md`: механическую часть собирает скрипт, а не оркестратор вручную.

  python3 scripts/handoff_service.py tasks/<папка>

Из файлов задачи собираются разделы: «Путь — исходы» (таблица из log.md), «Чек-лист готовности» (итог
`route.py ready`), «Маршрут» (шаги из state.json), «Расход» (`trace_summary.py --save`), «Запросы данных» (блоки
D-N из лога), «Числа» (numbers.csv), «Смысл, аудит и опоры» (строки «Смысл:» лога, `audit_sample.py --check`,
сводка `checks/quotes.md`). Четыре раздела требуют суждения и остаются за оркестратором: «Обещанное и полученное»,
«Что профиль не покрыл», «Перенесено в контекст», «Замечания к системе»: если они уже заполнены в существующем
`08-service.md`, скрипт их сохраняет, иначе ставит заглушку «— заполнить». Печатает, сколько заглушек осталось.
Повторный запуск безопасен: механические разделы пересобираются, заполненные руками не трогаются.
"""
import csv
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MANUAL = ("Обещанное и полученное", "Что профиль не покрыл", "Перенесено в контекст", "Замечания к системе")
STUB = "— заполнить"


def read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def run(script, *args):
    r = subprocess.run([sys.executable, os.path.join(HERE, script)] + list(args), capture_output=True, text=True)
    return r.returncode, (r.stdout or "").strip()


def sections(text):
    """{заголовок: тело} для разделов «## …»."""
    out, cur = {}, None
    for line in text.splitlines():
        m = re.match(r"^##\s+(.*?)\s*$", line)
        if m:
            cur = m.group(1)
            out[cur] = []
        elif cur is not None:
            out[cur].append(line)
    return {k: "\n".join(v).strip() for k, v in out.items()}


def path_table(log):
    m = re.search(r"^#*\s*ПУТЬ\s*[—-]\s*ИСХОДЫ\s*$", log, re.M)
    if not m:
        return "— в log.md нет раздела «ПУТЬ — ИСХОДЫ»"
    rest = log[m.end():]
    stop = re.search(r"^(#+ |ШАГ\s+\d|ПОРУЧЕНИЕ|СДАЧА)", rest, re.M)
    body = (rest[:stop.start()] if stop else rest).strip()
    return body or "— пусто"


def route_lines(task):
    import json
    try:
        st = json.load(open(os.path.join(task, "state.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return "— нет state.json"
    lines = []
    for s in st.get("steps", []):
        extra = "" if s.get("status") == "done" else " — %s%s" % (s.get("status"), (": " + s["waived"]) if s.get("waived") else "")
        lines.append("%d. %s → %s%s" % (s["n"], s["role"], s["artifact"], extra))
    return "\n".join(lines) or "— шагов нет"


def spend(task):
    code, out = run("trace_summary.py", task, "--save")
    if code == 0 and out:
        return out.splitlines()[-1]
    return "трассы нет: " + (out.splitlines()[0] if out else "хук трассы не сработал")


def data_requests(log):
    blocks, cur = [], None
    for line in log.splitlines():
        if re.match(r"^\s*\**D-\d+\b", line):
            cur = [line.strip()]
            blocks.append(cur)
        elif cur is not None and line.startswith((" ", "\t")) and line.strip():
            cur.append(line.strip())
        else:
            cur = None
    return "\n".join("- " + " ".join(b) for b in blocks) or "нет"


def numbers(task):
    try:
        rows = list(csv.DictReader(open(os.path.join(task, "numbers.csv"), encoding="utf-8", newline="")))
    except OSError:
        return "реестра чисел нет"
    kinds = {}
    for r in rows:
        kinds[r.get("kind", "?")] = kinds.get(r.get("kind", "?"), 0) + 1
    return "всего %d: %s" % (len(rows), ", ".join("%s %d" % kv for kv in sorted(kinds.items())) or "—")


def meaning_audit(task, log):
    parts = ["Смысл: " + x.split(":", 1)[1].strip() for x in re.findall(r"^Смысл:.*$", log, re.M)] or ["проверка смысла не шла"]
    sys.path.insert(0, HERE)
    import profile_lib
    if profile_lib.has_profile(task) and profile_lib.load(task)["validation"] != "full":
        parts.append("Аудит: не входит в профиль (validation=%s)" % profile_lib.load(task)["validation"])
    else:
        code, out = run("audit_sample.py", task, "--check")
        parts.append("Аудит: " + (out.splitlines()[-1] if out else ("нет плана" if code else "—")))
        parts += [l for l in (out or "").splitlines() if l.startswith(("Человеку:", "аудит: проверка смысла шла"))]
    q = read(os.path.join(task, "checks", "quotes.md"))
    first = next((l.strip("# ").strip() for l in q.splitlines() if l.strip()), "")
    parts.append("Опоры: " + (first or "checks/quotes.md нет"))
    return "\n".join("- " + p for p in parts)


def checklist(task):
    code, out = run("route.py", "ready", task)
    lines = [l for l in out.splitlines() if l.startswith(("Готовность", "Принято"))]
    return "\n".join(("- [x] " if code == 0 else "- [ ] ") + l for l in lines) or "- [ ] route.py ready не дал вывода"


def keep_items(body):
    """Содержательные пункты чек-листа, которые оркестратор записал руками, сохраняются при пересборке."""
    own = [l for l in body.splitlines() if l.strip() and not re.match(r"^- \[[ x]\] (Готовность|Принято)", l)]
    return ("\n" + "\n".join(own)) if own else ""


def main():
    if len(sys.argv) < 2:
        sys.stderr.write(__doc__)
        return 2
    task = sys.argv[1].rstrip("/")
    log = read(os.path.join(task, "log.md"))
    path = os.path.join(task, "08-service.md")
    old = sections(read(path))
    auto = [
        ("Путь — исходы", path_table(log)),
        ("Чек-лист готовности", checklist(task) + keep_items(old.get("Чек-лист готовности", ""))),
        ("Маршрут", route_lines(task)),
        ("Расход", spend(task)),
        ("Запросы данных", data_requests(log)),
        ("Числа", numbers(task)),
        ("Смысл, аудит и опоры", meaning_audit(task, log)),
    ]
    out = ["# Служебная сдача", ""]
    stubs = 0
    for name in MANUAL[:1]:
        body = old.get(name) or STUB
        stubs += body == STUB
        out += ["## " + name, "", body, ""]
    for name, body in auto:
        out += ["## " + name, "", body, ""]
    for name in MANUAL[1:]:
        body = old.get(name) or STUB
        stubs += body == STUB
        out += ["## " + name, "", body, ""]
    open(path, "w", encoding="utf-8").write("\n".join(out).rstrip() + "\n")
    print("08-service.md собран: разделов %d, заглушек для оркестратора %d (%s)" % (
        len(auto) + len(MANUAL), stubs, ", ".join(n for n in MANUAL if (old.get(n) or STUB) == STUB) or "нет"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
