#!/usr/bin/env python3
"""Размер инструкций в токенах (оценка): ядро оркестратора, маршруты, скиллы и то, что грузит оркестратор на тип.

  python3 scripts/check_size.py            # таблица и пороги; код 1 — порог превышен

Токены — оценка по символам (CHARS_PER_TOKEN): для русского текста с разметкой это ближе к правде, чем по
байтам, но это не счёт токенизатора. Пороги — чтобы инструкции не разрастались обратно: каждое новое правило
либо помещается, либо вытесняет старое, либо уезжает в файл, который читается по требованию.

Что грузит оркестратор на тип выхода: ядро, указатель реестра, файл маршрута типа и файлы по требованию, до
которых этот тип доходит (источники, Нострадамус, сдача).
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
O = os.path.join(ROOT, ".claude", "skills", "orchestrator")
CHARS_PER_TOKEN = 2.6
LIMITS = {"core": 15000, "route": 8000, "skill": 15000, "per_type": 35000}
PER_TYPE = {
    "разбор": ["routes/review.md", "routes/subject-model.md", "routes/handoff.md"],
    "гипотезы, план проверки, ТЗ на доработку": ["routes/hypotheses.md", "routes/sources.md", "routes/forecast.md",
                                                 "routes/meaning.md", "routes/subject-model.md", "routes/handoff.md"],
    "валидация": ["routes/validation.md", "routes/sources.md", "routes/meaning.md", "routes/subject-model.md",
                  "routes/handoff.md"],
    "исследование": ["routes/research.md", "routes/sources.md", "routes/forecast.md", "routes/meaning.md",
                     "routes/subject-model.md", "routes/handoff.md"],
    "вердикты по проверке": ["routes/results.md", "routes/handoff.md"],
}


def tokens(path):
    try:
        with open(path, encoding="utf-8") as f:
            return round(len(f.read()) / CHARS_PER_TOKEN)
    except OSError:
        return 0


def main():
    errors, rows = [], []
    core = tokens(os.path.join(O, "SKILL.md"))
    reg = tokens(os.path.join(O, "registry.md"))
    rows.append(("ядро оркестратора", core, LIMITS["core"]))
    rows.append(("указатель реестра", reg, None))
    for f in sorted(os.listdir(os.path.join(O, "routes"))):
        rows.append(("routes/" + f, tokens(os.path.join(O, "routes", f)), LIMITS["route"]))
    for kind, files in PER_TYPE.items():
        missing = [f for f in files if not os.path.exists(os.path.join(O, f))]
        if missing:
            errors.append("нет файлов маршрута: " + ", ".join(missing))
        rows.append(("оркестратор на тип «%s»" % kind, core + reg + sum(tokens(os.path.join(O, f)) for f in files),
                     LIMITS["per_type"]))
    skills = os.path.join(ROOT, ".claude", "skills")
    for s in sorted(os.listdir(skills)):
        p = os.path.join(skills, s, "SKILL.md")
        if s != "orchestrator" and os.path.exists(p):
            rows.append(("скилл " + s, tokens(p), LIMITS["skill"]))
    rows.append(("AGENTS.md (у каждого агента)", tokens(os.path.join(ROOT, "AGENTS.md")), None))
    print("| Что | Токенов (оценка) | Порог |\n| --- | --- | --- |")
    for name, n, lim in rows:
        print("| %s | %d | %s |" % (name, n, lim or "—"))
        if lim and n > lim:
            errors.append("%s: %d при пороге %d — перенеси часть в файл по требованию или сократи" % (name, n, lim))
    for e in errors:
        print("размер: " + e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
