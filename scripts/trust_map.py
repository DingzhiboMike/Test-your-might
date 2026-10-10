#!/usr/bin/env python3
"""Счёт опор задачи для карты доверия исследования — считает скрипт, а не модель.

  python3 scripts/trust_map.py tasks/<папка>

Пишет блок в tasks/<папка>/checks/trust.md и печатает его. Исследователь (research-report) переносит
блок в отчёт дословно: так сводка опор не зависит от того, что модель решит о себе написать.

Считает по реестрам: источники (типы, уровни, независимые корни, прочитанные не целиком, поданные
агентом), числа (факты, производные, допущения, без периода), проверки смысла (блокирующие и обычные замечания,
ответы автора по отчётам review-*.md, что проверяющий назвал несверенным).
"""
import csv
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_quotes import load_registry, root_of  # noqa: E402
import review_format as rf  # noqa: E402


def rows(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    if len(sys.argv) < 2:
        sys.stderr.write(__doc__)
        sys.exit(2)
    task = sys.argv[1].rstrip("/")
    reg = load_registry(task)
    nums = rows(os.path.join(task, "numbers.csv"))
    out = ["СЧЁТ ОПОР (считает scripts/trust_map.py)", ""]

    if reg:
        used = [r for r in reg.values() if r.get("read") != "not-read"]
        roots = {root_of(r["id"], reg) for r in used}
        kinds = Counter(r["kind"] + (" · уровень " + r["level"] if r.get("level") else "") for r in used)
        ctx = Counter(r["ctx_type"] for r in used if r.get("ctx_type"))
        out.append("Источников: {} прочитано, {} не прочитано; независимых корней: {}".format(
            len(used), len(reg) - len(used), len(roots)))
        out.append("  по типам: " + ", ".join("{} — {}".format(k, v) for k, v in sorted(kinds.items())))
        if ctx:
            out.append("  контекст по типам: " + ", ".join("{} — {}".format(k, v) for k, v in sorted(ctx.items())))
        partial = [r["id"] for r in used if r.get("read") in ("partial", "snippet")]
        by_agent = [r["id"] for r in used if r.get("kind") == "web" and r.get("fetched") == "agent"]
        outdated = [r["id"] for r in used if r.get("status") in ("outdated", "draft")]
        if partial:
            out.append("  прочитаны не целиком: " + ", ".join(partial))
        if by_agent:
            out.append("  текст подан агентом, не скачан скриптом: " + ", ".join(by_agent))
        if outdated:
            out.append("  черновики и устаревшие: " + ", ".join(outdated))
        claims = [r["id"] for r in used if r.get("ctx_type") == "claim"]
        if claims:
            out.append("  утверждения команды (опорой не служат): " + ", ".join(claims))
    else:
        out.append("Источников: реестра нет")

    out.append("")
    if nums:
        c = Counter(r["kind"] for r in nums)
        out.append("Чисел: {} (факты — {}, производные — {}, допущения — {})".format(
            len(nums), c.get("fact", 0), c.get("derived", 0), c.get("assumption", 0)))
        for r in nums:
            if r["kind"] == "assumption":
                out.append("  допущение [{}] {} = {} {} — {}".format(r["id"], r["what"], r["value"], r["unit"], r.get("note", "")))
        nop = [r["id"] for r in nums if r["kind"] == "fact" and not r.get("period")]
        if nop:
            out.append("  факты без периода данных: " + ", ".join(nop))
    else:
        out.append("Чисел: реестра нет")

    out.append("")
    reviews = sorted(n for n in os.listdir(task) if n.startswith("review-") and n.endswith(".md"))
    if reviews:
        out.append("Проверки смысла:")
        for rv in reviews:
            text = open(os.path.join(task, rv), encoding="utf-8").read()
            blocking = rf.blocking_ids(text)
            remarks = rf.remark_ids(text)
            m = re.search(r"^Артефакт:\s*(\S+)", text, re.M)
            ans = {}
            if m and os.path.exists(os.path.join(task, m.group(1))):
                block = rf.answer_block(open(os.path.join(task, m.group(1)), encoding="utf-8").read())
                ans = rf.answers(block) if block else {}

            def tally(ids):
                c = Counter(ans[i][0] for i in ids if i in ans)
                return "исправлено {}, снято {}, оспорено {}, без ответа {}".format(
                    c["исправлено"], c["снято"], c["оспорено"], sum(1 for i in ids if i not in ans))

            out.append("  {}: блокирующих {} ({}); замечаний {} ({})".format(
                m.group(1) if m else rv, len(blocking), tally(blocking), len(remarks), tally(remarks)))
            nc = rf.not_checked(text)
            if nc:
                out.append("    проверяющий не сверил: " + nc)
    else:
        out.append("Проверки смысла: отчётов нет")

    report = "\n".join(out) + "\n"
    os.makedirs(os.path.join(task, "checks"), exist_ok=True)
    with open(os.path.join(task, "checks", "trust.md"), "w", encoding="utf-8") as f:
        f.write(report)
    sys.stdout.write(report)


if __name__ == "__main__":
    main()
