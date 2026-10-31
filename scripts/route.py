#!/usr/bin/env python3
"""Состояние маршрута в коде: какой шаг идёт, что он изменил, какие обязательные шаги впереди, готова ли сдача.

  python3 scripts/route.py init   tasks/<папка>                        # перед первым шагом: state.json из ТЗ
  python3 scripts/route.py start  tasks/<папка> <роль> <артефакт> [--allow <маска> …]   # перед вызовом
  python3 scripts/route.py done   tasks/<папка> [<номер шага>]          # после вызова: периметр, проверки, расход
  python3 scripts/route.py next   tasks/<папка>                         # обязательные шаги впереди и остаток бюджета
  python3 scripts/route.py ready  tasks/<папка>                         # готовность: артефакты и проверки типа
  python3 scripts/route.py status tasks/<папка>                         # продолжение после обрыва
  python3 scripts/route.py retry  tasks/<папка>                         # перезапрос: заново открыть последний шаг с ошибками (та же роль и артефакт)
  python3 scripts/route.py waive  tasks/<папка> <номер шага> <причина>   # принять упавший шаг с оговоркой (причина видна в готовности)
  python3 scripts/route.py profile tasks/<папка> generation=wide evidence=links validation=logic data=public ceiling="8 вызовов, sonnet"
                                                                        # профиль прогона (выбирает оркестратор по ТЗ; нет профиля — всё строго, как в v1)

state.json пишет только этот скрипт. Шаг — роль, артефакт (имя или маска для пачки), хэши всех файлов задачи до
вызова. `done` сверяет хэши после: изменилось что-то кроме артефакта, масок --allow и служебного (log.md,
реестр источников и чисел, checks/, map/, трасса, модель предмета) — ошибка периметра, по содержимому, а не по
времени файла. Затем запускает check_step.py по артефакту и печатает его строки «Проверки» и «Расход» для лога.

Пока шаг идёт, хук записи пускает подагента только в артефакт и маски этого шага; хук остановки подагента
прогоняет check_step и один раз возвращает исполнителю ошибки, чтобы он исправил артефакт сам (не для пачек).

Обязательные шаги и артефакты готовности — по типу выхода (REQUIRED). Решения, какой источник звать, остаются
за оркестратором: скрипт проверяет только допустимость и полноту. Код возврата 1 — ошибки.
"""
import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from check_effort import ideas_required, output_type, tz_field  # noqa: E402
import profile_lib  # noqa: E402

STATE = "state.json"
OS_JUNK = (".DS_Store", "Thumbs.db", "desktop.ini")  # служебные файлы ОС: не артефакты и не нарушение периметра
SERVICE = ("log.md", "state.json", "state.json.tmp", "trace.jsonl", "trace.jsonl.tmp", "trace-main.json",
           "trace-main.json.tmp", "sources.csv", "numbers.csv", "sources/*", "sources/*/*", "checks/*", "map/*",
           "00m-model.md", "00m-model.json", "00i-impact.md", "00d-map.md")

# Обязательные шаги по типу выхода: (роль, артефакт, условие). Условие: None — всегда; "ideas" — если новые идеи
# нужны (check_effort.ideas_required); "rehearsal" — если в РЕЖИМЕ «пробный прогон: да».
AUDIT = ("meaning-review", "audit.md", None)  # выборочный аудит итоговых артефактов (audit_sample.py)
TAIL_IDEAS = [("nostradamus", "02f-forecast.md", None), ("hypothesis-validator", "02g-ideas-check.md", "ideas")]
REQUIRED = {
    "разбор": [("b2b-consultant", "01-review.md", None)],
    "гипотезы": [("b2b-consultant", "01-review.md", None), ("hypothesis-generator", "02-hypotheses.md", None),
                 ("hypothesis-validator", "02c-validation.md", None),
                 ("meaning-review", "review-02c-validation.md", None)] + TAIL_IDEAS +
                [("b2b-consultant", "02e-position.md", None), ("project-analyst", "03-backlog.md", None),
                 ("synthetic-interviews", "03c-rehearsal.md", "rehearsal"), AUDIT],
    "план проверки": [("b2b-consultant", "01-review.md", None), ("hypothesis-generator", "02-hypotheses.md", None),
                      ("hypothesis-validator", "02c-validation.md", None),
                      ("meaning-review", "review-02c-validation.md", None)] + TAIL_IDEAS +
                     [("project-analyst", "03-plan.md", None), ("test-kit", "03b-test-kit.md", None),
                      ("synthetic-interviews", "03c-rehearsal.md", "rehearsal"), AUDIT],
    "ТЗ на доработку": [("b2b-consultant", "01-review.md", None), ("hypothesis-generator", "02-hypotheses.md", None),
                        ("hypothesis-validator", "02c-validation.md", None),
                        ("meaning-review", "review-02c-validation.md", None)] + TAIL_IDEAS +
                       [("b2b-consultant", "02e-position.md", None), ("brief-writer", "07a-analyst.md", None),
                        ("brief-writer", "07b-editor.md", None), ("brief-writer", "07c-decisions.md", None), AUDIT],
    "валидация": [("b2b-consultant", "01-review.md", None), ("hypothesis-validator", "02c-validation.md", None),
                  ("meaning-review", "review-02c-validation.md", None),
                  ("hypothesis-generator", "02b-reinforced.md", None), ("project-analyst", "03-plan.md", None),
                  ("research-report", "06-validation.md", None),
                  ("meaning-review", "review-06-validation.md", None), AUDIT],
    "исследование": [("b2b-consultant", "01-review.md", None)] + TAIL_IDEAS +
                    [("research-report", "06-research.md", None), ("meaning-review", "review-06-research.md", None),
                     AUDIT],
    "вердикты по проверке": [("results-reviewer", "04-results.md", None)],
}
# Проверки готовности по типу: скрипт и аргументы после папки задачи.
READY_CHECKS = {
    "разбор": [("check_path.py", ["--plan"])],
    "гипотезы": [("check_path.py", []), ("check_log_sources.py", []), ("check_forecast.py", []),
                 ("check_ideas.py", []), ("check_readable.py", []), ("check_effort.py", []),
                 ("check_rehearsal.py", [])],
    "план проверки": [("check_path.py", []), ("check_log_sources.py", []), ("check_forecast.py", []),
                      ("check_ideas.py", []), ("check_effort.py", []), ("check_rehearsal.py", [])],
    "ТЗ на доработку": [("check_path.py", []), ("check_log_sources.py", []), ("check_forecast.py", []),
                        ("check_ideas.py", []), ("check_readable.py", []), ("check_effort.py", [])],
    "валидация": [("check_path.py", []), ("check_log_sources.py", []), ("check_readable.py", [])],
    "исследование": [("check_path.py", []), ("check_log_sources.py", []), ("check_forecast.py", []),
                     ("check_ideas.py", []), ("check_effort.py", [])],
    "вердикты по проверке": [],
}
COMMON_CHECKS = [("check_quotes.py", []), ("check_private.py", [])]
for _kind in ("гипотезы", "план проверки", "ТЗ на доработку", "валидация", "исследование"):
    READY_CHECKS[_kind].append(("audit_sample.py", ["--check"]))


def read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def load(task):
    try:
        with open(os.path.join(task, STATE), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def save(task, st):
    tmp = os.path.join(task, STATE + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)
    os.replace(tmp, os.path.join(task, STATE))


def snapshot(task):
    out = {}
    for base, _, files in os.walk(task):
        for name in files:
            if name in OS_JUNK:
                continue
            p = os.path.join(base, name)
            rel = os.path.relpath(p, task)
            if rel.startswith(STATE):
                continue
            h = hashlib.sha256()
            with open(p, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 16), b""):
                    h.update(chunk)
            out[rel] = h.hexdigest()
    return out


def matches(rel, masks):
    return any(fnmatch.fnmatch(rel, m) for m in masks)


def running(st):
    return [s for s in (st or {}).get("steps", []) if s.get("status") == "running"]


def allowed_writes(task):
    """Маски, куда подагент может писать сейчас; None — маршрута в коде нет (state.json не заведён)."""
    st = load(task)
    if st is None:
        return None
    masks = []
    for s in running(st):
        masks += [s["artifact"]] + s.get("allow", [])
    return masks


def modes(tz):
    return {"rehearsal": bool(re.search(r"пробный прогон:\s*да", tz_field(tz, "РЕЖИМ")))}


PROFILED = ("гипотезы", "план проверки", "ТЗ на доработку", "валидация", "исследование")


def profile_keeps(prof, role, art):
    """Какие обязательные шаги остаются при профиле. validation: none — без проверки по сути и всего, что после неё;
    logic/web — проверка по сути; full — ещё проверка смысла и аудит. generation: narrow — без Нострадамуса и отсева идей."""
    val, gen = prof["validation"], prof["generation"]
    forecast = prof.get("forecast", "on") == "on"
    if role == "meaning-review" and val != "full":
        return False
    if role == "hypothesis-validator" and art == "02c-validation.md" and val == "none":
        return False
    if role == "nostradamus" or art == "02g-ideas-check.md":
        return gen != "narrow" and forecast
    return True


def required(task):
    tz = read(os.path.join(task, "00-tz.md"))
    kind = output_type(tz)
    out = []
    prof = profile_lib.load(task)
    for role, art, cond in REQUIRED.get(kind, []):
        if kind in PROFILED and not profile_keeps(prof, role, art):
            continue
        if cond == "ideas" and not ideas_required(task):
            continue
        if cond == "rehearsal" and not modes(tz)["rehearsal"]:
            continue
        out.append((role, art))
    if kind == "гипотезы" and prof.get("run") == "solo":
        out = [("light-run", art) for _, art in out]  # один агент пишет все артефакты типа
    return kind, out


def cmd_init(task):
    tz = read(os.path.join(task, "00-tz.md"))
    if not re.search(r"^\W*СОГЛАСОВАНО", tz, re.M):
        print("Маршрут не заведён: в 00-tz.md нет строки СОГЛАСОВАНО.")
        return 1
    kind = output_type(tz)
    if kind is None:
        print("Маршрут не заведён: в ТЗ не выбран ТИП ВЫХОДА.")
        return 1
    st = load(task) or {"type": kind, "created": round(time.time()), "steps": []}
    st["type"] = kind
    st["price"] = tz_field(tz, "ЦЕНА")
    save(task, st)
    print("Маршрут: %s, шагов записано %d." % (kind, len(st["steps"])))
    return 0


def cmd_profile(task, kv):
    st = load(task)
    if st is None:
        print("Нет state.json: сначала python3 scripts/route.py init %s" % task)
        return 1
    prof = dict(st.get("profile") or {})
    pairs = []
    for item in kv:
        if "=" not in item:
            print("Ожидается ключ=значение: %s" % item)
            return 2
        pairs.append(item.split("=", 1))
    # level=… задаёт набор параметров; остальные ключи в той же команде его уточняют
    for k, v in pairs:
        if k == "level":
            if v not in profile_lib.LEVELS:
                print("Параметр level: допустимо %s" % ", ".join(profile_lib.LEVELS))
                return 2
            prof.update(profile_lib.preset(v))
            prof["level"] = v
    for k, v in pairs:
        if k == "level":
            continue
        if k not in profile_lib.KEYS:
            print("Неизвестный параметр профиля: %s (есть: %s)" % (k, ", ".join(profile_lib.KEYS)))
            return 2
        v = profile_lib.ALIASES.get(k, {}).get(v, v)
        if k in profile_lib.CHOICES and v not in profile_lib.CHOICES[k]:
            print("Параметр %s: допустимо %s" % (k, ", ".join(profile_lib.CHOICES[k])))
            return 2
        prof[k] = v
    if kv:
        st["profile"] = prof
        save(task, st)
    cur = profile_lib.load(task)
    print("Профиль: " + "; ".join("%s=%s" % (k, cur[k]) for k in profile_lib.KEYS))
    return 0


def cmd_retry(task):
    """Перезапрос исполнителя после ошибок проверок: одной командой открывает заново последний шаг со статусом failed
    (та же роль, тот же артефакт и маски). Закрывай `done` только после возврата исполнителя."""
    st = load(task)
    if st is None:
        print("Нет state.json: сначала python3 scripts/route.py init %s" % task)
        return 1
    if running(st):
        print("Шаг %d ещё идёт: дождись возврата исполнителя и закрой его (route.py done)." % running(st)[0]["n"])
        return 1
    failed = [s for s in st.get("steps", []) if s.get("status") == "failed" and not superseded(st, s)]
    if not failed:
        print("Нет шага с ошибками: перезапрашивать нечего.")
        return 1
    last = failed[-1]
    return cmd_start(task, last["role"], last["artifact"], last.get("allow", []))


def cmd_waive(task, n, reason):
    """Принять упавший шаг с оговоркой: причина обязательна, пишется в state.json и печатается в готовности.
    Для случаев, когда проверка шага ошиблась или ошибку нельзя исправить (state.json руками не правится)."""
    st = load(task)
    if st is None:
        print("Нет state.json: сначала python3 scripts/route.py init %s" % task)
        return 1
    step = next((s for s in st.get("steps", []) if s["n"] == n), None)
    if step is None or step.get("status") != "failed":
        print("Шага %d с ошибками нет." % n)
        return 1
    if len(reason.strip()) < 15:
        print("Нужна причина (не короче 15 знаков): почему ошибку принимаем и что она значит для результата.")
        return 2
    step["waived"] = reason.strip()
    save(task, st)
    print("Шаг %d (%s) принят с оговоркой: %s" % (n, step["role"], step["waived"]))
    return 0


def cmd_start(task, role, artifact, allow):
    st = load(task)
    if st is None:
        print("Нет state.json: сначала python3 scripts/route.py init %s" % task)
        return 1
    n = len(st["steps"]) + 1
    st["steps"].append({"n": n, "role": role, "artifact": artifact, "allow": allow, "status": "running",
                        "started": round(time.time()), "before": snapshot(task)})
    save(task, st)
    print("Шаг %d: %s → %s%s; --since %d" % (n, role, artifact, " (+ %s)" % ", ".join(allow) if allow else "",
                                            st["steps"][-1]["started"]))
    return 0


def cmd_done(task, n=None):
    st = load(task)
    run_ = running(st)
    step = next((s for s in run_ if n is None or s["n"] == n), None) if run_ else None
    if step is None:
        print("Нет идущего шага%s: route.py start перед вызовом." % ("" if n is None else " %d" % n))
        return 1
    after = snapshot(task)
    before = step.pop("before", {})
    changed = sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))
    masks = [step["artifact"]] + step.get("allow", [])
    others = [s for s in run_ if s is not step]
    foreign = [p for p in changed if not matches(p, masks) and not matches(p, SERVICE)
               and not any(matches(p, [o["artifact"]] + o.get("allow", [])) for o in others)]
    produced = [p for p in changed if matches(p, masks)]
    errors = []
    if foreign:
        errors.append("изменено вне периметра шага: " + ", ".join(foreign))
    if not produced:
        errors.append("артефакт шага %s не создан и не изменён" % step["artifact"])
    r = subprocess.run([sys.executable, os.path.join(HERE, "check_step.py"), task, step["artifact"],
                        "--since", str(step["started"]), "--allow", "*"],  # периметр уже сверен по хэшам
                       capture_output=True, text=True)
    lines = [l for l in r.stdout.splitlines() if l.startswith(("Проверки:", "Расход:"))]
    step.update(status="failed" if errors or r.returncode else "done", finished=round(time.time()),
                changed=changed, checks=lines[0] if lines else "", errors=errors)
    save(task, st)
    print("Шаг %d — %s: %s" % (step["n"], step["role"], "ок" if step["status"] == "done" else "ОШИБКИ"))
    for e in errors:
        print("Периметр: " + e)
    for l in lines:
        print(l)
    if r.returncode:
        print("\n".join(l for l in r.stdout.splitlines() if not l.startswith(("Проверки:", "Расход:"))).strip())
    return 0 if step["status"] == "done" else 1


def superseded(st, s):
    """Упавший шаг снят, если позже тот же артефакт сдан успешно (перезапрос) или шаг принят с оговоркой (waive)."""
    if s.get("waived"):
        return True
    return any(x["n"] > s["n"] and x.get("status") == "done" and x["artifact"] == s["artifact"]
               for x in st.get("steps", []))


def done_artifacts(st):
    return {s["artifact"] for s in st.get("steps", []) if s.get("status") == "done"}


def cmd_next(task):
    st = load(task)
    if st is None:
        print("Нет state.json: сначала route.py init.")
        return 1
    kind, req = required(task)
    have = done_artifacts(st)
    left = [(r, a) for r, a in req if a not in have and not os.path.exists(os.path.join(task, a))]
    for s in running(st):
        print("Идёт: шаг %d — %s → %s" % (s["n"], s["role"], s["artifact"]))
    print("Обязательные впереди (%s): %s" % (kind, "; ".join("%s → %s" % x for x in left) or "нет"))
    r = subprocess.run([sys.executable, os.path.join(HERE, "cost_estimate.py"), task, "--left"],
                       capture_output=True, text=True)
    if r.stdout.strip():
        print(r.stdout.strip())
    return 0


def cmd_ready(task):
    st = load(task) or {"steps": []}
    kind, req = required(task)
    if kind is None:
        print("Готовность: в ТЗ не выбран ТИП ВЫХОДА.")
        return 1
    errors = []
    for role, art in req:
        if not os.path.exists(os.path.join(task, art)):
            errors.append("нет артефакта %s (%s)" % (art, role))
    for s in running(st):
        errors.append("шаг %d (%s) не закрыт: route.py done" % (s["n"], s["role"]))
    for s in st.get("steps", []):
        if s.get("status") == "failed":
            if s.get("waived"):
                print("Принято с оговоркой: шаг %d (%s) — %s" % (s["n"], s["role"], s["waived"]))
            elif not superseded(st, s):
                errors.append("шаг %d (%s) закрыт с ошибками: %s" % (s["n"], s["role"], "; ".join(s.get("errors") or [])
                                                                      or s.get("checks", "")))
    prof = profile_lib.load(task)
    checks = list(READY_CHECKS.get(kind, [])) + list(COMMON_CHECKS)
    if prof["validation"] != "full":
        checks = [c for c in checks if c[0] != "audit_sample.py"]
    if prof["generation"] == "narrow" or prof.get("forecast", "on") != "on":
        checks = [c for c in checks if c[0] not in ("check_forecast.py", "check_ideas.py")]
    if kind != "вердикты по проверке":
        checks.append(("check_path.py", ["--tz"]))
    if os.path.exists(os.path.join(task, "00k-knowledge.md")):
        checks.append(("check_knowledge.py", []))
    if os.path.exists(os.path.join(task, "numbers.csv")):
        checks.append(("check_numbers.py", []))
    if prof["evidence"] != "quotes":
        checks = [c for c in checks if c[0] not in ("check_quotes.py", "check_numbers.py")]
    for script, args in checks:
        r = subprocess.run([sys.executable, os.path.join(HERE, script), task] + args, capture_output=True, text=True)
        if r.returncode:
            last = next((l for l in reversed(r.stdout.splitlines()) if l.strip()), "")
            errors.append("%s — ошибки: %s" % (script, last[:200]))
    for e in errors:
        print("Готовность: " + e)
    if not errors:
        print("Готовность (%s): обязательные артефакты на месте, проверки типа без ошибок." % kind)
    print("Содержательные пункты чек-листа (например, «у каждой гипотезы есть опровергающее наблюдение») сверяет "
          "оркестратор по реестру.")
    return 1 if errors else 0


def cmd_status(task):
    st = load(task)
    if st is None:
        print("Нет state.json.")
        return 1
    print("Маршрут: %s; %s" % (st.get("type"), st.get("price") or "строки ЦЕНА нет"))
    for s in st.get("steps", []):
        print("Шаг %d — %s → %s: %s%s" % (s["n"], s["role"], s["artifact"], s["status"],
                                         ("; " + s["checks"]) if s.get("checks") else ""))
    return cmd_next(task)


def main():
    a = sys.argv[1:]
    if len(a) < 2:
        sys.stderr.write(__doc__)
        return 2
    cmd, task = a[0], a[1].rstrip("/")
    if cmd == "init":
        return cmd_init(task)
    if cmd == "start":
        if len(a) < 4:
            sys.stderr.write(__doc__)
            return 2
        allow = [a[i + 1] for i, x in enumerate(a) if x == "--allow" and i + 1 < len(a)]
        return cmd_start(task, a[2], a[3], allow)
    if cmd == "done":
        return cmd_done(task, int(a[2]) if len(a) > 2 else None)
    if cmd == "next":
        return cmd_next(task)
    if cmd == "ready":
        return cmd_ready(task)
    if cmd == "status":
        return cmd_status(task)
    if cmd == "profile":
        return cmd_profile(task, a[2:])
    if cmd == "retry":
        return cmd_retry(task)
    if cmd == "waive":
        if len(a) < 4 or not a[2].isdigit():
            sys.stderr.write(__doc__)
            return 2
        return cmd_waive(task, int(a[2]), " ".join(a[3:]))
    sys.stderr.write(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
