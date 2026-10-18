#!/usr/bin/env python3
"""Проверка цепочки гипотез: клетка модели, рамка продукта, размер группы.

  python3 scripts/check_chain.py tasks/<папка>

Читает `02-hypotheses.md` (блоки `### Г-<номер>`), `00m-model.json` (после `build_model.py`) и `00r-limits.md`.
В каждой гипотезе обязательны строки:
  - **Клетка:** <группа> × <признак> — клетка есть в модели. Клетка «нет данных» — предупреждение: гипотеза
    стоит на пробеле, опорой служит только идея.
  - **Рамка продукта:** R-<номер> (одна или несколько) — рамка есть в `00r-limits.md` и имеет статус «есть»;
    «нет» — ошибка (механики нет в продукте); «неясно» или не подтверждена — предупреждение. Либо
    «не требует: <причина>».
  - **Размер группы:** число и источник — `[F-…]`, `[N-…]` или `[допущение: причина]`; без числа — ошибка.
Рамки: таблица `| R-1 | есть | описание | «цитата» [F-007 L5] | документы |`; последняя колонка — кто
подтвердил: документы или человек. Цитата проверяется по строкам карты, как в `check_map.py`; рамка без цитаты
допустима, если её подтвердил человек.
Отчёт: `checks/chain.md`. Ошибка — код возврата 1.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_map import lines_of, read, squeeze  # noqa: E402

LIM = re.compile(r"^\|\s*(R-\d+)\s*\|\s*(есть|нет|неясно)\s*\|([^|]*)\|([^|]*)\|\s*([^|]*?)\s*\|?\s*$")
QL = re.compile(r"«([^»]+)»\s*\[(F-\d+)\s+L(\d+)(?:\s*[-–]\s*L?(\d+))?\]")


def limits(task, errors):
    out = {}
    for line in read(os.path.join(task, "00r-limits.md")).splitlines():
        m = LIM.match(line.strip())
        if not m:
            continue
        rid, status, desc, proof, who = m.group(1), m.group(2), m.group(3).strip(), m.group(4).strip(), m.group(5).strip().lower()
        ok = False
        for q, src, a, b in QL.findall(proof):
            a, b = int(a), int(b or a)
            lines = lines_of(task, src)
            if lines is None or a not in lines or b not in lines:
                errors.append("%s: в карте %s нет строк L%d–L%d" % (rid, src, a, b))
            elif squeeze(q.rstrip("…")) not in squeeze(" ".join(lines[n]["text"] for n in range(a, b + 1))):
                errors.append("%s: цитата не найдена в %s L%d–L%d" % (rid, src, a, b))
            else:
                ok = True
        if not ok and not who.startswith("человек"):
            errors.append("%s: нет проверяемой цитаты [F-id L…] и не подтверждено человеком" % rid)
        out[rid] = {"status": status, "who": who, "desc": desc}
    return out


def field(block, name):
    m = re.search(r"(?m)^- (?:\*\*)?%s:(?:\*\*)?\s*(.+)$" % re.escape(name), block)
    return m.group(1).strip() if m else ""


def main():
    if len(sys.argv) < 2:
        sys.stderr.write(__doc__)
        return 2
    task = sys.argv[1].rstrip("/")
    text = read(os.path.join(task, "02-hypotheses.md"))
    if not text:
        print("Гипотез (02-hypotheses.md) нет: проверять нечего.")
        return 0
    errors, warnings = [], []
    mp = os.path.join(task, "00m-model.json")
    model = json.load(open(mp, encoding="utf-8")) if os.path.exists(mp) else None
    if model is None:
        errors.append("нет 00m-model.json: сначала собери модель (scripts/build_model.py)")
    lim = limits(task, errors)
    hyps = re.split(r"(?m)^(?=###\s+Г-\d+)", text)
    n = 0
    for b in hyps:
        m = re.match(r"###\s+(Г-\d+)", b)
        if not m:
            continue
        n += 1
        hid = m.group(1)
        cell = field(b, "Клетка")
        if not cell:
            errors.append("%s: не названа клетка модели" % hid)
        elif model is not None:
            key = re.sub(r"\s*[×xх]\s*", " × ", cell.strip(), count=1)
            c = model["cells"].get(key)
            if c is None:
                errors.append("%s: клетки «%s» нет в модели" % (hid, cell))
            elif c["level"] == "нет данных":
                warnings.append("%s: клетка «%s» пуста — гипотеза стоит на пробеле, опора только идея" % (hid, key))
        fr = field(b, "Рамка продукта")
        if not fr:
            errors.append("%s: не названа рамка продукта" % hid)
        elif fr.lower().startswith("не требует"):
            if len(fr) < len("не требует: ") + 5:
                errors.append("%s: «не требует» без причины" % hid)
        else:
            ids = re.findall(r"R-\d+", fr)
            if not ids:
                errors.append("%s: в «Рамка продукта» нет R-номера" % hid)
            for rid in ids:
                r = lim.get(rid)
                if r is None:
                    errors.append("%s: рамки %s нет в 00r-limits.md" % (hid, rid))
                elif r["status"] == "нет":
                    errors.append("%s: механики нет в продукте (%s: %s)" % (hid, rid, r["desc"][:60]))
                elif r["status"] == "неясно":
                    warnings.append("%s: рамка %s «неясно» — нужен ответ продукта" % (hid, rid))
                elif not r["who"].startswith(("человек", "документы")):
                    warnings.append("%s: рамка %s без указания, кто подтвердил" % (hid, rid))
        sz = field(b, "Размер группы")
        if not sz or not re.search(r"\d", sz):
            errors.append("%s: нет «Размер группы» с числом" % hid)
        elif not re.search(r"\[(F-\d+|N-\d+|допущение)", sz):
            warnings.append("%s: размер группы без источника ([F-…], [N-…] или [допущение: причина])" % hid)
    if n == 0:
        errors.append("в 02-hypotheses.md нет блоков гипотез")
    os.makedirs(os.path.join(task, "checks"), exist_ok=True)
    open(os.path.join(task, "checks", "chain.md"), "w", encoding="utf-8").write(
        "# Проверка цепочки: %s\n\nГипотез: %d, рамок: %d.\n\n## Ошибки\n%s\n\n## Предупреждения\n%s\n" % (
            os.path.basename(task), n, len(lim), "\n".join("- " + e for e in errors) or "- нет",
            "\n".join("- " + w for w in warnings) or "- нет"))
    print("Цепочка: гипотез %d, ошибок %d, предупреждений %d." % (n, len(errors), len(warnings)))
    for e in errors[:15]:
        print("  ОШИБКА " + e)
    for w in warnings[:8]:
        print("  внимание " + w)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
