#!/usr/bin/env python3
"""Склейка досье документов из пачек картографа: 00d-map-<буква>.md → 00d-map.md.

  python3 scripts/merge_map.py tasks/<папка>

Картографы идут пачками параллельно и пишут свои файлы (`00d-map-a.md`, `00d-map-b.md`, …). Скрипт собирает блоки
`### F-id` из всех частей в один `00d-map.md` по возрастанию номера источника; один и тот же F-id в двух частях —
ошибка (документ описан дважды). Результат проверяет `check_map.py`. Файл `00d-map.md` — служебный: его запись скриптом не
нарушает периметр шага.
"""
import glob
import os
import re
import sys


def main():
    if len(sys.argv) < 2:
        sys.stderr.write(__doc__)
        return 2
    task = sys.argv[1].rstrip("/")
    parts = sorted(glob.glob(os.path.join(task, "00d-map-*.md")))
    if not parts:
        print("Частей досье (00d-map-*.md) нет: склеивать нечего.")
        return 1
    blocks, errors = {}, []
    for p in parts:
        text = open(p, encoding="utf-8").read()
        for b in re.split(r"(?m)^(?=### F-\d+)", text):
            m = re.match(r"### F-(\d+)", b)
            if not m:
                continue
            n = int(m.group(1))
            if n in blocks:
                errors.append("F-%03d описан дважды (%s и ещё в одной части)" % (n, os.path.basename(p)))
            blocks[n] = b.rstrip() + "\n"
    out = os.path.join(task, "00d-map.md")
    open(out, "w", encoding="utf-8").write("\n".join(blocks[n] for n in sorted(blocks)))
    for e in errors:
        print("склейка: " + e)
    print("Склеено блоков: %d из %d частей → 00d-map.md." % (len(blocks), len(parts)))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
