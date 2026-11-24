#!/usr/bin/env python3
"""Форма карты поля (`src-field.md`, исполнитель field-scan): ширина, разнообразие опор, контраргумент из другого
источника, журнал запросов. Смысл — держит ли фрагмент механизм — не проверяет: это проверка смысла.

  python3 scripts/check_field.py tasks/<папка>

Правила (контракт `.claude/skills/field-scan/SKILL.md`, лестница — `methodology/web-protocol.md`, п. 1б):
1. Направлений «## НП-k — …» в разделе «# КАРТА ПОЛЯ» от 6 до 12.
2. У каждого заполнены поля: Суть, Механизм, Где применяли, Сила опоры, Контраргумент, Цена, Перенос к нам, Уверенность.
3. «Где применяли» и «Сила опоры» — с id источника [F-k].
4. «Сила опоры» начинается со ступени: обзор, сравнение, кейс, практик, вендор.
5. «Контраргумент» — с id источника, которого нет в опорах этого направления, и с другого домена (у открытых
   архивов статей — другая статья, check_refute.ARCHIVES); или «не нашли:» с
   запросом в обратных кавычках. «Не нашли» больше чем у половины направлений — ошибка: опровержения не искали.
6. Веб-опор карты (уникальных id из «Где применяли» и «Сила опоры») — не меньше 6 доменов; ни один домен не держит
   больше 30% опор.
7. Ступеней в карте не меньше двух разных; если в карте только «практик» и «вендор», в «# БЕЛЫЕ ПЯТНА» должно быть
   сказано, где искали сильнее (строка с «обзор», «сравнение» или «исследован»).
8. Источник «Силы опоры» прочитан целиком (`read=full` в sources.csv) хотя бы у половины направлений.
9. Разделы «# ОСИ», «# БЕЛЫЕ ПЯТНА», «# СПОРНЫЕ МЕСТА», «# ЗАПРОСЫ» есть и не пусты; осей не меньше трёх.
10. В «# ЗАПРОСЫ» от 15 до 40 строк с запросом в обратных кавычках; помеченных «[опровержение]» не меньше трёх.
    Если в ТЗ потолок («потолок: до N запросов»), он — верхняя граница, а нижняя — две трети N.

Отчёт: tasks/<папка>/checks/field.md. Код возврата 1 — есть ошибки (оркестратор: один перезапрос с отчётом).
"""
import csv
import os
import re
import sys
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_refute import domain as refute_key  # noqa: E402

FILE = "src-field.md"
FIELDS = ("Суть", "Механизм", "Где применяли", "Сила опоры", "Контраргумент", "Цена", "Перенос к нам", "Уверенность")
STEPS = ("обзор", "сравнение", "кейс", "практик", "вендор")
MIN_DIR, MAX_DIR = 6, 12
MIN_DOMAINS, MAX_SHARE = 6, 0.30
MIN_Q, MAX_Q, MIN_REFUTE = 15, 40, 3
REF = re.compile(r"\bF-\d+\b")


def read(path):
    return open(path, encoding="utf-8").read() if os.path.exists(path) else ""


def sections(text):
    """Разделы верхнего уровня «# ИМЯ» → текст."""
    out, cur = {}, None
    for line in text.splitlines():
        m = re.match(r"^#\s+(.+?)\s*$", line)
        if m:
            cur = m.group(1).strip().upper().replace("Ё", "Е")
            out[cur] = []
            continue
        if cur is not None:
            out[cur].append(line)
    return {k: "\n".join(v) for k, v in out.items()}


def directions(body):
    """Направления «## НП-k — название» → (метка, {поле: значение})."""
    out = []
    for block in re.split(r"(?m)^(?=##\s)", body):
        m = re.match(r"^##\s+(НП-\d+)\b.*", block)
        if not m:
            continue
        fields = {}
        for line in block.splitlines()[1:]:
            f = re.match(r"^\s*[-*]\s*\**\s*([^:*]+?)\s*:\s*\**\s*(.*)$", line)
            if f:
                fields[f.group(1).strip()] = f.group(2).strip()
        out.append((m.group(1), fields))
    return out


def registry(task):
    try:
        with open(os.path.join(task, "sources.csv"), encoding="utf-8", newline="") as f:
            return {r["id"]: r for r in csv.DictReader(f)}
    except (OSError, KeyError):
        return {}


def domain(row):
    loc = (row or {}).get("location", "")
    host = urlparse(loc).netloc.lower() if "://" in loc else ""
    host = host[4:] if host.startswith("www.") else host
    return host or ("файл:" + loc if loc else "")


def filled(v):
    return bool(v and v.strip(" —-–.…"))


def query_bounds(tz):
    """Границы числа запросов. Потолок в ТЗ («СТАВКИ: … потолок: до 15 запросов …») решает человек: он становится
    верхней границей, а нижняя — две трети потолка, но не выше обычной. Потолка нет — обычные MIN_Q–MAX_Q."""
    m = re.search(r"потолок[^\n]*?(\d+)\s*запрос", tz or "", re.I)
    if not m:
        return MIN_Q, MAX_Q
    cap = int(m.group(1))
    return min(MIN_Q, max(MIN_REFUTE, -(-cap * 2 // 3))), min(MAX_Q, cap)


def main():
    if len(sys.argv) < 2:
        sys.stderr.write(__doc__)
        return 2
    task = sys.argv[1].rstrip("/")
    text = read(os.path.join(task, FILE))
    if not text:
        print("Карты поля нет: проверять нечего.")
        return 0
    reg = registry(task)
    sec = sections(text)
    errors = []

    for name in ("ОСИ", "КАРТА ПОЛЯ", "БЕЛЫЕ ПЯТНА", "СПОРНЫЕ МЕСТА", "ЗАПРОСЫ"):
        if not sec.get(name, "").strip():
            errors.append("нет раздела «# %s» или он пуст" % name)
    axes = [l for l in sec.get("ОСИ", "").splitlines() if re.match(r"^\s*[-*]\s+\S", l)]
    if sec.get("ОСИ") and len(axes) < 3:
        errors.append("осей поиска %d, нужно не меньше трёх" % len(axes))

    dirs = directions(sec.get("КАРТА ПОЛЯ", ""))
    if not MIN_DIR <= len(dirs) <= MAX_DIR:
        errors.append("направлений %d, нужно %d–%d" % (len(dirs), MIN_DIR, MAX_DIR))

    support_ids, steps_seen, not_found, full_read = [], set(), 0, 0
    for label, f in dirs:
        missing = [k for k in FIELDS if not filled(f.get(k, ""))]
        if missing:
            errors.append("%s: не заполнено — %s" % (label, ", ".join(missing)))
        where, strength, counter = f.get("Где применяли", ""), f.get("Сила опоры", ""), f.get("Контраргумент", "")
        own = set(REF.findall(where)) | set(REF.findall(strength))
        if filled(where) and not REF.search(where):
            errors.append("%s: «Где применяли» без id источника" % label)
        if filled(strength) and not REF.search(strength):
            errors.append("%s: «Сила опоры» без id источника" % label)
        step = re.match(r"^[«\"`]?\s*([а-яё]+)", strength.lower())
        if filled(strength):
            if not step or step.group(1) not in STEPS:
                errors.append("%s: «Сила опоры» не начинается со ступени (%s)" % (label, ", ".join(STEPS)))
            else:
                steps_seen.add(step.group(1))
        sids = REF.findall(strength)
        if sids and all(reg.get(s, {}).get("read") == "full" for s in sids[:1]):
            full_read += 1
        support_ids.extend(i for i in own if i not in support_ids)
        if not filled(counter):
            continue
        if re.match(r"^\s*не нашли\s*:", counter, re.I):
            not_found += 1
            if "`" not in counter:
                errors.append("%s: «не нашли» без запроса в обратных кавычках" % label)
            continue
        cids = set(REF.findall(counter))
        if not cids:
            errors.append("%s: контраргумент без id источника и без «не нашли:»" % label)
            continue
        # независимость контраргумента — как в check_refute: у открытых архивов статей граница — статья, а не сайт
        own_domains = {refute_key(reg.get(i)) for i in own} - {""}
        other = [i for i in cids - own if refute_key(reg.get(i)) not in own_domains]
        if not other:
            errors.append("%s: контраргумент из того же источника или домена, что опора направления" % label)
    if dirs and not_found * 2 > len(dirs):
        errors.append("«не нашли» в контраргументе у %d из %d направлений: опровержения не искали" % (not_found, len(dirs)))

    web = [i for i in support_ids if reg.get(i, {}).get("kind") == "web"]
    doms = {}
    for i in web:
        doms.setdefault(domain(reg.get(i)), []).append(i)
    if dirs and len(doms) < MIN_DOMAINS:
        errors.append("веб-опоры карты с %d доменов, нужно не меньше %d" % (len(doms), MIN_DOMAINS))
    for d, ids in sorted(doms.items(), key=lambda x: -len(x[1])):
        if web and len(ids) / len(web) > MAX_SHARE:
            errors.append("домен %s держит %d из %d веб-опор карты (больше %d%%)" % (d, len(ids), len(web), int(MAX_SHARE * 100)))
        break

    if dirs and len(steps_seen) < 2:
        errors.append("в карте одна ступень силы опоры (%s): поле не разведено по силе" % (", ".join(steps_seen) or "—"))
    if steps_seen and steps_seen <= {"практик", "вендор"}:
        if not re.search(r"обзор|сравнени|исследован", sec.get("БЕЛЫЕ ПЯТНА", ""), re.I):
            errors.append("опоры только «практик» и «вендор», а в «БЕЛЫХ ПЯТНАХ» не сказано, где искали сильнее")
    if dirs and full_read * 2 < len(dirs):
        errors.append("источник «Силы опоры» прочитан целиком у %d из %d направлений, нужно хотя бы у половины"
                      % (full_read, len(dirs)))

    qs = [l for l in sec.get("ЗАПРОСЫ", "").splitlines() if re.match(r"^\s*[-*]\s*`[^`]+`", l)]
    refute = [l for l in qs if "[опровержение]" in l.lower()]
    min_q, max_q = query_bounds(read(os.path.join(task, "00-tz.md")))
    if sec.get("ЗАПРОСЫ") is not None and not min_q <= len(qs) <= max_q:
        errors.append("запросов в журнале %d, нужно %d–%d" % (len(qs), min_q, max_q))
    if sec.get("ЗАПРОСЫ") is not None and len(refute) < MIN_REFUTE:
        errors.append("запросов с пометкой [опровержение] %d, нужно не меньше %d" % (len(refute), MIN_REFUTE))

    lines = ["# Проверка карты поля", "",
             "Направлений: %d; ступени: %s; веб-опор: %d с %d доменов; «не нашли» в контраргументе: %d; "
             "запросов: %d, против подхода: %d" % (len(dirs), ", ".join(sorted(steps_seen)) or "—", len(web), len(doms),
                                                   not_found, len(qs), len(refute)), ""]
    lines += ["Ошибки:"] + ["- " + e for e in errors] if errors else ["Ошибок нет."]
    os.makedirs(os.path.join(task, "checks"), exist_ok=True)
    open(os.path.join(task, "checks", "field.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print("Карта поля: %s" % ("ОШИБКИ (%d)" % len(errors) if errors else "ок"))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
