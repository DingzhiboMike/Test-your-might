#!/usr/bin/env python3
"""Профиль прогона: нагрузка, строгость и ширина, которые выбирает оркестратор по тексту ТЗ и ответу человека.

Хранится в state.json задачи (пишет только `route.py profile`). Нет профиля — действует v1: всё строго и обязательно.

  level:      fast | light | work | strict  — уровень нагрузки (готовый набор параметров; параметры ниже можно править)
  generation: narrow | medium | wide        — ширина генерации (narrow: без линз, Нострадамуса, отсева идей)
  evidence:   none | links | quotes         — опоры (none, links: цитаты/свежесть/числа не блокируют; quotes: как в v1)
  validation: none | method | web | full    — проверка (none: без проверки по сути; method: проверка по сути по методологии
                                              без веба; web: то же с веб-сверкой; full: + проверка смысла и аудит)
  forecast:   on | off                      — Нострадамус и отсев идей
  lenses:     0..3                          — сколько линз до генератора (ходов к источникам за сырьём); по умолчанию 0: линзы выключены, число берётся из строки РЕЖИМ в ТЗ
  data:       none | context | public       — какие данные человека берём (подсказка оркестратору)
  run:        steps | solo                  — steps: цепочка отдельных агентов; solo: один агент light-run пишет все артефакты
                                              типа «гипотезы» (по умолчанию на light)
  ceiling:    произвольная строка           — потолок вызовов и модель (подсказка оркестратору)

Шкала «креатив ↔ точность» (К5 … Т5) — язык для человека; уровни нагрузки — её готовые наборы:
  light ≈ К5/К4, work ≈ баланс, strict ≈ Т4/Т5 (Т5: добавить generation=narrow).
"""
import json
import os

KEYS = ("level", "generation", "evidence", "validation", "forecast", "lenses", "data", "ceiling", "run")
DEFAULT = {"level": "strict", "generation": "wide", "evidence": "quotes", "validation": "full", "forecast": "on",
           "lenses": "0", "data": "context", "ceiling": "", "run": "steps"}
CHOICES = {"level": ("fast", "light", "work", "strict"), "generation": ("narrow", "medium", "wide"),
           "evidence": ("none", "links", "quotes"), "validation": ("none", "method", "web", "full"),
           "forecast": ("on", "off"), "lenses": ("0", "1", "2", "3"), "data": ("none", "context", "public"), "run": ("steps", "solo")}
# Готовые наборы по уровню. fast — без маршрута (ответ диспетчера/оркестратора без исполнителей, 0–2 вызова).
LEVELS = {
    "fast": {"generation": "narrow", "evidence": "none", "validation": "none", "forecast": "off", "lenses": "0", "run": "steps"},
    "light": {"generation": "medium", "evidence": "none", "validation": "method", "forecast": "off", "lenses": "0", "run": "solo"},
    "work": {"generation": "medium", "evidence": "links", "validation": "web", "forecast": "on", "lenses": "0", "run": "steps"},
    "strict": {"generation": "medium", "evidence": "quotes", "validation": "full", "forecast": "on", "lenses": "0", "run": "steps"},
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
