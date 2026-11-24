#!/usr/bin/env python3
"""Профиль прогона — запись решений оркестратора о шагах и проверках, а не готовый уровень нагрузки.

Хранится в state.json задачи (пишет только `route.py profile`). Нет профиля — действует v1: всё строго и обязательно.

Вариант A (ветка variant-a-ceiling): уровней нагрузки нет. Есть один стартовый набор `auto` — инварианты включены
(отдельная проверка по сути с вебом, дословные цитаты), всё остальное оркестратор решает сам по ходу и фиксирует
командой `route.py profile <параметр>=<значение>` с причиной в логе. Ограничение сверху — ПОТОЛОК вызовов от человека.

  level:      auto                          — стартовый набор (параметры ниже оркестратор меняет сам)
  generation: narrow | medium | wide        — ширина генерации (narrow: без линз, Нострадамуса, отсева идей)
  evidence:   none | links | quotes         — опоры (none, links: цитаты/свежесть/числа не блокируют; quotes: как в v1)
  validation: none | method | web | full    — проверка (none: без проверки по сути; method: проверка по сути по методологии
                                              без своей веб-сверки (веб по пунктам ТЗ — ход к источнику); web: то же с веб-сверкой; full: + проверка смысла и аудит)
  forecast:   on | off                      — Нострадамус и отсев идей
  lenses:     0..3                          — сколько линз до генератора (ходов к источникам за сырьём); по умолчанию 0: линзы выключены, число берётся из строки РЕЖИМ в ТЗ
  data:       none | context | public       — какие данные человека берём (подсказка оркестратору)
  run:        steps | solo                  — steps: цепочка отдельных агентов; solo: один агент light-run пишет все артефакты
                                              типа «гипотезы» (по умолчанию на light)
  reviewer:   same | other | human          — проверка смысла и аудит: same (по умолчанию на всех уровнях) — модель по умолчанию; other — модель
                                              сильнее, чем у авторов, того же производителя (sonnet → opus;
                                              audit_sample.py --check сверяет по трассе); human — то же, и места аудита идут человеку в сдачу
  audit:      off | on                      — аудит находок до генерации (00a-audit.md): проверка по сути сверяет ключевые
                                              находки разбора материалов до генератора; по умолчанию off на всех уровнях
  ceiling:    произвольная строка           — потолок вызовов и модель (подсказка оркестратору)

Старые уровни fast / light / work / strict сняты: они существовали, чтобы выключать обязательные шаги, а
обязательными в варианте A остаются только инварианты. Профили старых задач в state.json читаются как есть.
"""
import json
import os

KEYS = ("level", "generation", "evidence", "validation", "forecast", "lenses", "data", "ceiling", "run", "reviewer", "audit")
DEFAULT = {"level": "strict", "generation": "wide", "evidence": "quotes", "validation": "full", "forecast": "on",
           "lenses": "0", "data": "context", "ceiling": "", "run": "steps", "reviewer": "same", "audit": "off"}
CHOICES = {"level": ("auto", "fast", "light", "work", "strict"), "generation": ("narrow", "medium", "wide"),
           "evidence": ("none", "links", "quotes"), "validation": ("none", "method", "web", "full"),
           "forecast": ("on", "off"), "lenses": ("0", "1", "2", "3"), "data": ("none", "context", "public"), "run": ("steps", "solo"),
           "reviewer": ("same", "other", "human"), "audit": ("off", "on")}
# Один стартовый набор. Инварианты: проверка по сути отдельным агентом с вебом (R-002, R-008), дословные цитаты
# (R-019, R-024). Нострадамус, линзы, ширина, проверка смысла, аудит — не обязательны: включает оркестратор, когда
# шаг меняет ответ («Если пропустить» в логе), или человек в ответах на вопросы (строка РЕЖИМ).
LEVELS = {
    "auto": {"generation": "medium", "evidence": "quotes", "validation": "web", "forecast": "off", "lenses": "0",
             "run": "steps", "reviewer": "same", "audit": "off"},
}
ALIASES = {"validation": {"logic": "method"}}


def normalize(prof):
    out = {}
    for k, v in prof.items():
        if k in KEYS:
            out[k] = ALIASES.get(k, {}).get(v, v)
    return out


def preset(level):
    return dict(LEVELS.get(level, {}))


def load(task):
    try:
        with open(os.path.join(task, "state.json"), encoding="utf-8") as f:
            st = json.load(f)
    except (OSError, ValueError):
        st = {}
    prof = dict(DEFAULT)
    prof.update(normalize(st.get("profile") or {}))
    return prof


def has_profile(task):
    try:
        with open(os.path.join(task, "state.json"), encoding="utf-8") as f:
            return bool(json.load(f).get("profile"))
    except (OSError, ValueError):
        return False


def strict_evidence(task):
    return load(task)["evidence"] == "quotes"
