#!/usr/bin/env python3
"""Разброс генерации: не одна мысль в разных обёртках. Раньше генератор проверял это сам у себя — теперь скрипт.

  python3 scripts/check_diversity.py tasks/<папка>

Длинный список `02-long-list.md` (режим ширины) — колонки «Слой» и «Рамка» после семи обязательных:
1. Слой — один из пяти слоёв GTM: клиент, конкуренция, сообщение и цена, канал, рост. Пусто или не слой — ошибка.
2. Слоёв не меньше трёх, и ни на один слой не приходится больше половины ходов.
3. Если у консультанта есть вектор (`01-review.md`) — ходов с пометкой «[контрольный]» не меньше трёх; если в реестре
   есть утверждение команды (ctx_type claim) — ходов с пометкой «[наперекор]» не меньше двух.
4. Почти одинаковые ходы (общих основ слов 60% и больше) — предупреждение: дословные повторы ловит check_long_list.

Гипотезы `02-hypotheses.md` — блоки «### Г-N» со слотами «Слой:», «Рамка:», «Механизм:»:
5. Слоя нет или он не из пяти — ошибка. При трёх гипотезах и больше — хотя бы два слоя.
6. Одна рамка у трёх гипотез из трёх-четырёх или у четырёх из пяти — «разброса не произошло».
7. Механизмы двух гипотез совпадают по основам слов на половину и больше — «обёртки одной мысли».
8. Есть вектор консультанта — хотя бы одна гипотеза с пометкой «[контрольная]».
Если в задаче есть гипотезы человека (`00-hypotheses-in.md`), гипотезы не проверяются: их строил не генератор.

Скрипт сверяет форму разброса — метки и слова, а не смысл: разные слова при одной мысли видит проверка смысла.
Отчёт — tasks/<папка>/checks/diversity.md. Код возврата 1 — есть ошибки.
"""
import argparse
import csv
import os
import re
import sys

LAYERS = [("клиент", "клиент"), ("конкур", "конкуренция"), ("сообщ", "сообщение и цена"), ("цен", "сообщение и цена"),
          ("канал", "канал"), ("рост", "рост"), ("цел", "рост")]
STOP = {"чтобы", "потому", "котор", "который", "если", "будет", "этого", "через", "после", "перед", "когда", "тогда",
        "больш", "меньш", "своих", "свою", "своей", "можно", "нужно", "такой", "также", "только", "очень", "сразу"}


def read(path):
    return open(path, encoding="utf-8").read() if os.path.exists(path) else ""


def layer(value):
    v = value.strip().lower().replace("ё", "е")
    for prefix, name in LAYERS:
        if v.startswith(prefix):
            return name
    return None


def stems(text):
    words = re.findall(r"[а-яёa-z]{4,}", text.lower().replace("ё", "е"))
    return {w[:5] for w in words if w not in STOP and w[:5] not in STOP}


def jaccard(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0


def table(text):
    head, rows = None, []
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if head is None and any(c.lower() == "ход" for c in cells):
            head = [c.lower() for c in cells]
        elif re.match(r"^\d+$", cells[0]):
            rows.append(cells)
    return head or [], rows


def has_claim(task):
    try:
        with open(os.path.join(task, "sources.csv"), encoding="utf-8", newline="") as f:
            return any(r.get("ctx_type") == "claim" for r in csv.DictReader(f))
    except OSError:
        return False


def long_list(text, vector, claim, errors, warns):
    head, rows = table(text)
    if not rows:
        return "длинный список: строк нет"
    if "слой" not in head:
        errors.append("длинный список: нет колонки «Слой»")
        return "длинный список: %d ходов, слоёв не видно" % len(rows)
    li, mi = head.index("слой"), head.index("ход")
    count, controls, contra = {}, 0, 0
    for r in rows:
        name = layer(r[li]) if li < len(r) else None
        if not name:
            errors.append("длинный список, ход %s: слой «%s» не из пяти" % (r[0], r[li] if li < len(r) else ""))
            continue
        count[name] = count.get(name, 0) + 1
        controls += "[контрольн" in r[mi].lower()
        contra += "[наперекор]" in r[mi].lower()
    if claim and contra < 2:
        errors.append("длинный список: ходов наперекор %d, при утверждениях команды в реестре нужно не меньше двух" % contra)
    if len(count) < 3:
        errors.append("длинный список: слоёв %d, нужно не меньше трёх" % len(count))
    top = max(count.items(), key=lambda x: x[1]) if count else ("", 0)
    if top[1] * 2 > len(rows):
        errors.append("длинный список: слой «%s» у %d ходов из %d — больше половины" % (top[0], top[1], len(rows)))
    if vector and controls < 3:
        errors.append("длинный список: контрольных ходов %d, при векторе консультанта нужно не меньше трёх" % controls)
    st = [(r[0], stems(r[mi])) for r in rows]
    for i in range(len(st)):
        for j in range(i + 1, len(st)):
            if jaccard(st[i][1], st[j][1]) >= 0.6:
                warns.append("длинный список: ходы %s и %s почти совпадают по словам" % (st[i][0], st[j][0]))
    return "длинный список: %d ходов, слоёв %d (%s), контрольных %d, наперекор %d" % (
        len(rows), len(count), ", ".join("%s %d" % kv for kv in sorted(count.items())), controls, contra)


def field(block, name):
    m = re.search(r"(?mi)^[\s>*-]*\**%s\**\s*:\**\s*(.*)$" % name, block)
    return m.group(1).strip() if m else ""


def hypotheses(text, vector, errors, warns):
    parts = re.split(r"(?m)^#{2,4}\s*(?=Г-\d+)", text)
    blocks = [(re.match(r"Г-\d+", b).group(0), b) for b in parts[1:]]
    if not blocks:
        warns.append("гипотезы: блоков «### Г-N» нет, разброс не проверен")
        return "гипотезы: блоков нет"
    layers, frames, mech, controls = {}, {}, [], 0
    for hid, b in blocks:
        name = layer(field(b, "Слой"))
        if not name:
            errors.append("%s: слой не назван или не из пяти" % hid)
        else:
            layers[name] = layers.get(name, 0) + 1
        for f in re.split(r"[,/;]+", field(b, "Рамка").lower()):
            f = f.strip(" .—-")
            if f and f not in ("пусто", "нет"):
                frames.setdefault(f, []).append(hid)
        mech.append((hid, stems(field(b, "Механизм"))))
        controls += "[контрольная]" in b.lower()
    n = len(blocks)
    if n >= 3 and len(layers) < 2:
        errors.append("гипотезы: все %d в одном слое" % n)
    limit = 3 if n <= 4 else n - 1
    for f, hids in sorted(frames.items()):
        if n >= 3 and len(hids) >= limit:
            errors.append("гипотезы: рамка «%s» у %d из %d — разброса не произошло" % (f, len(hids), n))
    for i in range(len(mech)):
        for j in range(i + 1, len(mech)):
            if jaccard(mech[i][1], mech[j][1]) >= 0.5:
                errors.append("%s и %s: механизм почти совпадает — обёртки одной мысли" % (mech[i][0], mech[j][0]))
    if vector and not controls:
        errors.append("гипотезы: у консультанта есть вектор, контрольной гипотезы нет")
    return "гипотезы: %d, слоёв %d, рамок %d, контрольных %d" % (n, len(layers), len(frames), controls)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("task")
    a = p.parse_args()
    task = a.task.rstrip("/")
    vector = "вектор" in read(os.path.join(task, "01-review.md")).lower()
    errors, warns, lines = [], [], []
    ll = read(os.path.join(task, "02-long-list.md"))
    if ll:
        lines.append(long_list(ll, vector, has_claim(task), errors, warns))
    hyp = read(os.path.join(task, "02-hypotheses.md"))
    if hyp and os.path.exists(os.path.join(task, "00-hypotheses-in.md")):
        lines.append("гипотезы человека — разброс не проверяется")
    elif hyp:
        lines.append(hypotheses(hyp, vector, errors, warns))
    if not lines:
        print("Разброс: длинного списка и гипотез нет, проверять нечего.")
        return 0
    os.makedirs(os.path.join(task, "checks"), exist_ok=True)
    out = ["# Разброс генерации: " + os.path.basename(task), ""] + ["- " + l for l in lines]
    out += ["", "## Ошибки"] + (["- " + e for e in errors] or ["- нет"])
    out += ["", "## Предупреждения"] + (["- " + w for w in warns] or ["- нет"])
    open(os.path.join(task, "checks", "diversity.md"), "w", encoding="utf-8").write("\n".join(out) + "\n")
    for e in errors:
        print("разброс: " + e)
    for w in warns:
        print("разброс (предупреждение): " + w)
    print("Разброс: " + "; ".join(lines) + ("; ошибок %d" % len(errors) if errors else "; ок"))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
