#!/usr/bin/env python3
"""Проверяет досье документов (слой 3 картографии): адресные цитаты, обязательные поля, полноту чисел.

  python3 scripts/check_map.py tasks/<папка>

Читает `00d-map.md` (досье пишет лёгкая модель по `map/<id>.lines.txt`, см. `scripts/map_docs.py`):
1. Каждый источник контекста из `sources.csv` (context, interview, from-tasks) есть в досье блоком `### F-id`.
2. В блоке все поля: Тип, Про кого, Сколько, Что измерено, Дата, Выводы документа, Числа и срезы, Про продукт,
   Риски и ограничения команды, Ключевая цитата, Сверх схемы, Отброшено, Статус чтения. Тип, «Что измерено» и
   статус — из допустимых значений; поле «Чего нет» необязательное. Поля «Влияние» и «Важность» запрещены: важность считает скрипт.
3. Каждая цитата «…» адресна: `L<номер>: «…»` или `«…» [L<номер>]` (диапазон `L5-L7`); текст цитаты дословно
   стоит в этих строках карты (регистр, ё/е, пробелы и разметка таблиц не важны; многоточие допустимо в конце).
4. Ключевая цитата — одна строка, не строка таблицы: фраза-вывод (строка таблицы — предупреждение).
5. Полнота: каждая строка карты с тегом «число» либо цитируется (номер строки в любом поле), либо перечислена в
   «Отброшено: L10, L20-L25 (причина)». Строка с тем же текстом, что уже учтённая (дубль блока), считается учтённой. Не учтено больше четверти таких строк — ошибка, меньше — предупреждение.
Документ со статусом «не читается» проверяется только на наличие блока и полей.

Ошибка — код возврата 1. Отчёт: tasks/<папка>/checks/map.md. Нет `00d-map.md` — проверять нечего.
"""
import csv
import json
import os
import re
import sys

REQUIRED = ["Тип", "Про кого", "Сколько", "Что измерено", "Дата", "Выводы документа", "Числа и срезы",
            "Про продукт", "Риски и ограничения команды", "Ключевая цитата", "Сверх схемы", "Отброшено",
            "Статус чтения"]
FORBIDDEN = ["Влияние", "Важность"]
TYPES = ["отчёт о тесте", "опрос", "интервью", "выгрузка", "описание продукта", "исследование",
         "расчёт или задача аналитиков", "утверждение команды", "другое"]
MEASURED = ["слова", "поведение", "результат теста", "описание", "утверждение команды"]
STATUS = ["прочитан", "частично", "не читается"]
KINDS = {"context", "interview", "from-tasks"}
UNCOVERED_ERROR = 0.25

REF = r"L(\d+)(?:\s*[-–]\s*L?(\d+))?"
Q1 = re.compile(REF + r"\s*:?\s*«([^»]+)»")
Q2 = re.compile(r"«([^»]+)»\s*\[" + REF + r"\]")
RANGE = re.compile(REF)


def squeeze(s):
    s = s.lower().replace("ё", "е")
    return re.sub(r"[\s |\\«»\"'`*_]+", "", s)


def read(path):
    return open(path, encoding="utf-8").read() if os.path.exists(path) else ""


def doc_ids(task):
    p = os.path.join(task, "sources.csv")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        return [r["id"] for r in csv.DictReader(f) if r.get("kind") in KINDS]


def blocks(text):
    out = {}
    for b in re.split(r"(?m)^(?=### F-\d+)", text):
        m = re.match(r"### (F-\d+)", b)
        if m:
            out[m.group(1)] = b
    return out


def fields(block):
    """Поля блока: имя -> текст (с продолжением на следующих строках)."""
    res, cur = {}, None
    for line in block.splitlines()[1:]:
        m = re.match(r"^- ([^:]+):\s*(.*)$", line)
        if m:
            cur = m.group(1).strip()
            res[cur] = m.group(2)
        elif cur and line.strip():
            res[cur] += "\n" + line
    return res


def lines_of(task, fid):
    p = os.path.join(task, "map", fid + ".json")
    if not os.path.exists(p):
        return None
    return {l["n"]: l for l in json.load(open(p, encoding="utf-8"))["lines"]}


def quotes(text):
    """Цитаты с адресом: (текст, от, до)."""
    out = []
    for m in Q1.finditer(text):
        out.append((m.group(3), int(m.group(1)), int(m.group(2) or m.group(1))))
    for m in Q2.finditer(text):
        out.append((m.group(1), int(m.group(2)), int(m.group(3) or m.group(2))))
    return out


def refs(text):
    cov = set()
    for m in RANGE.finditer(text):
        a, b = int(m.group(1)), int(m.group(2) or m.group(1))
        cov.update(range(a, max(a, b) + 1))
    return cov


def check_block(task, fid, block, errors, warnings):
    f = fields(block)
    for name in REQUIRED:
        if name not in f or not f[name].strip():
            errors.append("%s: нет поля «%s»" % (fid, name))
    for name in FORBIDDEN:
        if name in f:
            errors.append("%s: поле «%s» запрещено: важность документа считает скрипт, а не модель" % (fid, name))
    status = f.get("Статус чтения", "").strip().lower()
    if status and not any(status.startswith(s) for s in STATUS):
        errors.append("%s: «Статус чтения» должен начинаться с одного из: %s" % (fid, ", ".join(STATUS)))
    if status.startswith("не читается"):
        return
    typ = f.get("Тип", "").strip().lower()
    if typ and not any(typ.startswith(t) for t in TYPES):
        errors.append("%s: «Тип» должен начинаться с одного из: %s" % (fid, "; ".join(TYPES)))
    meas = f.get("Что измерено", "").strip().lower()
    if meas and not any(meas.startswith(t) for t in MEASURED):
        errors.append("%s: «Что измерено» должно начинаться с одного из: %s" % (fid, "; ".join(MEASURED)))
    lines = lines_of(task, fid)
    if lines is None:
        errors.append("%s: нет карты map/%s.json — запусти scripts/map_docs.py" % (fid, fid))
        return
    # цитаты: у каждой есть адрес, и текст дословно стоит в этих строках
    for key, val in f.items():
        for m in re.finditer(r"«([^»]+)»", val):
            q = m.group(1)
            if len(q) < 12:
                continue
            if not any(x[0] == q for x in quotes(val)):
                errors.append("%s: цитата без адреса строки: «%s…»" % (fid, q[:50]))
    for key, val in f.items():
        for q, a, b in quotes(val):
            if a not in lines or b not in lines:
                errors.append("%s: в карте нет строки L%d–L%d: «%s…»" % (fid, a, b, q[:40]))
                continue
            span = squeeze(" ".join(lines[n]["text"] for n in range(a, b + 1)))
            probe = squeeze(q.rstrip("…").rstrip("."))
            if probe and probe not in span:
                errors.append("%s: цитата не найдена в строках L%d–L%d: «%s…»" % (fid, a, b, q[:50]))
    key_q = f.get("Ключевая цитата", "")
    kq = quotes(key_q)
    if f.get("Ключевая цитата") and not kq:
        errors.append("%s: ключевая цитата без адреса строки" % fid)
    for q, a, b in kq:
        if a != b:
            warnings.append("%s: ключевая цитата занимает несколько строк (L%d–L%d): нужна одна фраза-вывод" % (fid, a, b))
        elif a in lines and lines[a]["text"].count(" | ") >= 2:
            warnings.append("%s: ключевая цитата — строка таблицы (L%d): лучше фраза-вывод" % (fid, a))
    # полнота чисел
    numeric = [n for n, l in lines.items() if "число" in l["tags"]]
    if len(numeric) >= 5:
        covered = refs(block)
        seen = {squeeze(lines[n]["text"]) for n in covered if n in lines}
        miss = [n for n in numeric if n not in covered and squeeze(lines[n]["text"]) not in seen]
        ratio = len(miss) / len(numeric)
        if ratio > UNCOVERED_ERROR:
            errors.append("%s: не учтено строк с числами: %d из %d (%.0f%%): L%s …"
                          % (fid, len(miss), len(numeric), 100 * ratio, ", L".join(str(n) for n in miss[:6])))
        elif miss:
            warnings.append("%s: не учтено строк с числами: %d из %d: L%s" % (fid, len(miss), len(numeric),
                                                                         ", L".join(str(n) for n in miss[:6])))
    if status.startswith("прочитан") and not status.startswith("прочитан частично"):
        read_flag = ""
        try:
            read_flag = json.load(open(os.path.join(task, "map", fid + ".json"), encoding="utf-8")).get("read", "")
        except Exception:
            pass
        if read_flag == "partial":
            warnings.append("%s: источник зарегистрирован как прочитанный частично, а в досье стоит «прочитан»" % fid)


def main():
    if len(sys.argv) < 2:
        sys.stderr.write(__doc__)
        return 2
    task = sys.argv[1].rstrip("/")
    text = read(os.path.join(task, "00d-map.md"))
    if not text:
        print("Досье документов (00d-map.md) нет: проверять нечего.")
        return 0
    bl = blocks(text)
    errors, warnings = [], []
    ids = doc_ids(task)
    for fid in ids:
        if fid not in bl:
            errors.append("%s: нет блока в досье" % fid)
    for fid in bl:
        if fid not in ids:
            warnings.append("%s: блок в досье есть, а источника контекста с таким id в реестре нет" % fid)
    for fid in ids:
        if fid in bl:
            check_block(task, fid, bl[fid], errors, warnings)
    os.makedirs(os.path.join(task, "checks"), exist_ok=True)
    with open(os.path.join(task, "checks", "map.md"), "w", encoding="utf-8") as f:
        f.write("# Проверка досье документов: %s\n\nДокументов в реестре: %d, блоков в досье: %d.\n\n## Ошибки\n%s\n\n"
                "## Предупреждения\n%s\n" % (os.path.basename(task), len(ids), len(bl),
                                             "\n".join("- " + e for e in errors) or "- нет",
                                             "\n".join("- " + w for w in warnings) or "- нет"))
    print("Досье: документов %d, блоков %d, ошибок %d, предупреждений %d." % (len(ids), len(bl), len(errors), len(warnings)))
    for e in errors[:15]:
        print("  ОШИБКА " + e)
    for w in warnings[:8]:
        print("  внимание " + w)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
