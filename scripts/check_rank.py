#!/usr/bin/env python3
"""Порядок направлений в позиции выводится из надёжности клеток модели.

  python3 scripts/check_rank.py tasks/<папка>

Читает `02e-trace.md` — служебный след итоговой позиции (человеку он не показывается), по строке на направление в
порядке позиции:
  1. Клетка: <группа> × <признак>; надёжность: значение|версия|идея|нет данных; гипотеза: Г-12
  2. Клетка: …; надёжность: идея; гипотеза: Г-5; расхождение: <почему выше надёжности>
  3. Клетка: …; надёжность: нет данных; гипотеза: Г-22; не ранжируется
и `00m-model.json`. Проверки:
- клетка есть в модели, названная надёжность равна посчитанной скриптом;
- надёжность по направлениям не растёт вниз по списку (значение → версия → идея), если у следующего нет строки
  «расхождение: причина»;
- направление с «нет данных» помечено «не ранжируется» и стоит после ранжированных;
- клетки со значением, на которые не опирается ни одно направление, — предупреждение.
Отчёт: `checks/rank.md`. Ошибка — код возврата 1. Нет `02e-trace.md` — проверять нечего.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_map import read  # noqa: E402

RANK = {"значение": 3, "версия": 2, "идея": 1, "нет данных": 0}
LINE = re.compile(r"^\s*(\d+)\.\s*Клетка:\s*(.+?)\s*;\s*надёжность:\s*([^;]+?)\s*(?:;(.*))?$")


def main():
    if len(sys.argv) < 2:
        sys.stderr.write(__doc__)
        return 2
    task = sys.argv[1].rstrip("/")
    trace = read(os.path.join(task, "02e-trace.md"))
    if not trace:
        print("След позиции (02e-trace.md) нет: проверять нечего.")
        return 0
    mp = os.path.join(task, "00m-model.json")
    if not os.path.exists(mp):
        print("Нет 00m-model.json: сначала собери модель (scripts/build_model.py).")
        return 1
    model = json.load(open(mp, encoding="utf-8"))
    errors, warnings, used, prev = [], [], set(), None
    seen_unranked = False
    n = 0
    for line in trace.splitlines():
        m = LINE.match(line)
        if not m:
            continue
        n += 1
        num, cell, claimed, rest = m.group(1), m.group(2), m.group(3).strip(), (m.group(4) or "")
        key = re.sub(r"\s*[×xх]\s*", " × ", cell, count=1)
        c = model["cells"].get(key)
        tag = "направление %s" % num
        if claimed not in RANK:
            errors.append("%s: надёжность «%s» — допустимо: значение, версия, идея, нет данных" % (tag, claimed))
            continue
        if c is None:
            errors.append("%s: клетки «%s» нет в модели" % (tag, cell))
            continue
        used.add(key)
        if c["level"] != claimed:
            errors.append("%s: надёжность клетки по модели — «%s», в следе — «%s»" % (tag, c["level"], claimed))
        unranked = "не ранжируется" in rest
        if claimed == "нет данных" and not unranked:
            errors.append("%s: клетка без данных должна быть помечена «не ранжируется»" % tag)
        if unranked:
            seen_unranked = True
        elif seen_unranked:
            errors.append("%s: ранжированное направление стоит после «не ранжируется»" % tag)
        if not unranked:
            if prev is not None and RANK[claimed] > prev and "расхождение:" not in rest:
                errors.append("%s: надёжность выше, чем у предыдущего направления, без строки «расхождение: причина»" % tag)
            prev = RANK[claimed]
    if n == 0:
        errors.append("в 02e-trace.md нет строк вида «1. Клетка: …; надёжность: …»")
    for key, c in model["cells"].items():
        if c["level"] == "значение" and key not in used:
            warnings.append("клетка «%s» со значением не использована ни одним направлением" % key)
    os.makedirs(os.path.join(task, "checks"), exist_ok=True)
    open(os.path.join(task, "checks", "rank.md"), "w", encoding="utf-8").write(
        "# Проверка порядка: %s\n\nНаправлений: %d.\n\n## Ошибки\n%s\n\n## Предупреждения\n%s\n" % (
            os.path.basename(task), n, "\n".join("- " + e for e in errors) or "- нет",
            "\n".join("- " + w for w in warnings) or "- нет"))
    print("Порядок: направлений %d, ошибок %d, предупреждений %d." % (n, len(errors), len(warnings)))
    for e in errors[:15]:
        print("  ОШИБКА " + e)
    for w in warnings[:8]:
        print("  внимание " + w)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
