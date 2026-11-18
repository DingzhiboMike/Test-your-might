#!/usr/bin/env python3
"""Проверяет научные источники по DOI: существует ли работа, та ли она, не отозвана ли.

  python3 scripts/check_doi.py tasks/<папка>
  python3 scripts/check_doi.py --doi 10.xxxx/yyyy [--title "название, как заявлено"] [--year 2021]

Режим задачи: для каждой строки sources.csv, где в адресе есть DOI, сверяется с Crossref и OpenAlex
(сеть нужна, ключи нет; в запрос уходит только DOI):
- DOI не зарегистрирован в doi.org — ошибка: источник выдуман или адрес искажён;
- работа отозвана (OpenAlex `is_retracted` или запись об отзыве в Crossref) — ошибка: опорой не служит;
- название по базам не находится в сыром тексте источника (меньше ~60% слов названия) — ошибка: DOI ведёт
  на другую работу, чем страница, которую прочитали, либо в реестр положен не тот текст;
- год по базам и `pub_date` в реестре расходятся больше чем на год — предупреждение;
- базы не ответили (нет сети, лимит) — «не проверено», это не ошибка и не подтверждение.

Режим --doi: то же для одного DOI; --title сверяет заявленное название с базами вместо сырого текста.
Скрипт проверяет форму и существование, а не то, что вывод из работы выведен верно: это проверка смысла.
Отчёт задачи: tasks/<папка>/checks/doi.md. Код возврата 1 — есть ошибки.
"""
import argparse
import csv
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

UA = "polygon-check-doi/1.0"
TIMEOUT = 20
MATCH_MIN = 0.6
DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"<>|]+", re.I)
WORD_RE = re.compile(r"[^\W_]{3,}", re.U)


def clean_doi(text):
    """DOI из адреса или строки; хвосты страницы издателя и знаки в конце отрезаются."""
    m = DOI_RE.search(urllib.parse.unquote(text or ""))
    if not m:
        return ""
    doi = m.group(0).rstrip(".,;:)]")
    doi = re.sub(r"/(full|abstract|pdf|epdf|html)$", "", doi, flags=re.I)
    return doi.rstrip(".,;:)]").lower()


def words(text):
    return {w.lower().replace("ё", "е") for w in WORD_RE.findall(text or "")}


def title_overlap(title, text):
    """Доля слов названия, которые есть в тексте. 0..1; пустое название — None (нечего сверять)."""
    tw = words(title)
    if not tw:
        return None
    return len(tw & words(text)) / len(tw)


def get_json(url):
    """(код, объект). Код 0 — не открылось по сети, объект None."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, json.loads(r.read(5_000_000).decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception:  # noqa: BLE001 — любая сетевая ошибка значит «не открылось»
        return 0, None


def fetch_meta(doi):
    """Сводка по DOI из сети: {registered, title, year, retracted, answered}.
    registered: True / False / None (не ответили). answered — сколько баз ответило."""
    q = urllib.parse.quote(doi, safe="")
    meta = {"registered": None, "title": "", "year": None, "retracted": False, "answered": 0}
    code, h = get_json("https://doi.org/api/handles/" + q)
    if code == 404 or (h and h.get("responseCode") == 100):
        meta["registered"] = False
        return meta
    if h and h.get("responseCode") == 1:
        meta["registered"] = True
    code, cr = get_json("https://api.crossref.org/works/" + q)
    if code == 200 and cr:
        meta["answered"] += 1
        msg = cr.get("message", {})
        titles = msg.get("title") or []
        meta["title"] = titles[0] if titles else ""
        for k in ("issued", "published-print", "published-online"):
            parts = (msg.get(k) or {}).get("date-parts") or [[None]]
            if parts[0] and parts[0][0]:
                meta["year"] = int(parts[0][0])
                break
        for u in msg.get("updated-by") or []:
            if "retract" in str(u.get("type", "")).lower():
                meta["retracted"] = True
        if meta["registered"] is None:
            meta["registered"] = True
    elif code == 404 and meta["registered"] is None:
        meta["registered"] = False
    code, oa = get_json("https://api.openalex.org/works/doi:" + q)
    if code == 200 and oa:
        meta["answered"] += 1
        if not meta["title"]:
            meta["title"] = oa.get("title") or oa.get("display_name") or ""
        if not meta["year"] and oa.get("publication_year"):
            meta["year"] = int(oa["publication_year"])
        if oa.get("is_retracted"):
            meta["retracted"] = True
        if meta["registered"] is None:
            meta["registered"] = True
    return meta


def judge(meta, raw_text="", claimed_title="", pub_year=None):
    """Чистая функция: решение по сводке. Возвращает (статус, замечания).
    статус: ok / ошибка / предупреждение / не проверено."""
    if meta["registered"] is False:
        return "ошибка", ["DOI не зарегистрирован: источник выдуман или адрес искажён"]
    if meta["registered"] is None and not meta["answered"]:
        return "не проверено", ["базы не ответили"]
    errors, warns = [], []
    if meta["retracted"]:
        errors.append("работа отозвана: опорой не служит")
    reference = claimed_title or ""
    haystack = reference or raw_text
    if meta["title"] and haystack:
        ov = title_overlap(meta["title"], haystack)
        if ov is not None and ov < MATCH_MIN:
            where = "заявленным названием" if claimed_title else "сырым текстом источника"
            errors.append("название по базам («%s») не совпадает с %s (%.0f%% слов): DOI ведёт на другую работу"
                          % (meta["title"][:90], where, ov * 100))
    elif not meta["title"]:
        warns.append("базы не отдали название: соответствие работы не проверено")
    if meta["year"] and pub_year and abs(meta["year"] - pub_year) > 1:
        warns.append("год по базам %d, в реестре %d" % (meta["year"], pub_year))
    if errors:
        return "ошибка", errors + warns
    if warns:
        return "предупреждение", warns
    return "ok", []


def year_of(s):
    m = re.match(r"^(\d{4})", s or "")
    return int(m.group(1)) if m else None


def task_rows(task):
    path = os.path.join(task, "sources.csv")
    if not os.path.isfile(path):
        return []
    out = []
    with open(path, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            doi = clean_doi(r.get("location", ""))
            if doi:
                out.append((r, doi))
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("task", nargs="?", help="папка задачи")
    p.add_argument("--doi")
    p.add_argument("--title", default="")
    p.add_argument("--year", type=int)
    a = p.parse_args()
    lines, errors = [], 0

    if a.doi:
        doi = clean_doi(a.doi)
        if not doi:
            print("Не похоже на DOI: " + a.doi)
            sys.exit(1)
        status, notes = judge(fetch_meta(doi), "", a.title, a.year)
        print("%s: %s" % (doi, status))
        for n in notes:
            print("  - " + n)
        sys.exit(1 if status == "ошибка" else 0)

    if not a.task:
        p.error("нужна папка задачи или --doi")
    task = a.task.rstrip("/")
    rows = task_rows(task)
    cache = {}
    for r, doi in rows:
        raw = ""
        rp = os.path.join(task, "sources", "raw", r["id"] + ".txt")
        if os.path.isfile(rp):
            raw = open(rp, encoding="utf-8", errors="replace").read(60000)
        if doi not in cache:
            cache[doi] = fetch_meta(doi)
        status, notes = judge(cache[doi], raw, "", year_of(r.get("pub_date", "")))
        if status == "ошибка":
            errors += 1
        lines.append("| %s | %s | %s | %s |" % (r["id"], doi, status, "; ".join(notes) or "—"))
    head = ["# Проверка DOI (scripts/check_doi.py)", "",
            "Источников с DOI: %d. Ошибок: %d." % (len(rows), errors), ""]
    if lines:
        head += ["| Источник | DOI | Итог | Замечания |", "| --- | --- | --- | --- |"] + lines
    else:
        head += ["В реестре нет источников с DOI."]
    out = os.path.join(task, "checks")
    if os.path.isdir(task):
        os.makedirs(out, exist_ok=True)
        open(os.path.join(out, "doi.md"), "w", encoding="utf-8").write("\n".join(head) + "\n")
    print("\n".join(head))
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
