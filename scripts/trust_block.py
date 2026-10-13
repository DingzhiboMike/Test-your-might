#!/usr/bin/env python3
"""Общая функция: какие строки артефакта принадлежат блоку «СЧЁТ ОПОР».

Блок пишет scripts/trust_map.py и переносится в отчёт дословно (check_artifact --contains checks/trust.md),
поэтому проверки чисел и свежести его не разбирают: в нём числа стоят после [N-id], а годы веб-источников
не привязаны к строке. Блок начинается строкой «СЧЁТ ОПОР», заканчивается первой пустой строкой после
строки «Проверки смысла».
"""


def trust_block_lines(lines):
    """Множество индексов строк (с нуля), входящих в блок «СЧЁТ ОПОР». Пусто, если блока нет."""
    start = next((i for i, ln in enumerate(lines) if ln.startswith("СЧЁТ ОПОР")), None)
    if start is None:
        return set()
    marker = next((i for i in range(start, len(lines)) if lines[i].startswith("Проверки смысла")), None)
    if marker is None:
        end = len(lines)
        for i in range(start + 1, len(lines)):
            if lines[i].startswith(("## ", "**")):
                end = i
                break
    else:
        end = next((i for i in range(marker, len(lines)) if not lines[i].strip()), len(lines))
    return set(range(start, end))


def mask_trust_block(text):
    """Текст без блока «СЧЁТ ОПОР»: строки блока заменены пустыми, номера остальных строк сохраняются."""
    lines = text.split("\n")
    skip = trust_block_lines(lines)
    return "\n".join("" if i in skip else ln for i, ln in enumerate(lines))
