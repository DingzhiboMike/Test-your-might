#!/usr/bin/env python3
"""Опровержение в проверке по сути — из другого источника, а не на честном слове (R-008, `web-protocol.md`, п. 2).

  python3 scripts/check_refute.py tasks/<папка>

Читает `02c-validation.md` и `02d-validation2.md` (если есть). Блок — «ГИПОТЕЗА N — …» или «У-k — …» (валидация).
Поле сверки — «Сверка:» (гипотезы) или «Из сети:» (утверждения) вместе со строками продолжения с отступом.
Формат строк опровержения (контракт `.claude/skills/hypothesis-validator/SKILL.md`, «Формат выхода»):

            опровержение: `запрос` → что нашёл «…» [F-id]
            опровержение: `запрос` → не найдено
            опровержение из реестра (другой источник): «…» [F-id]   — уже найденный источник, без нового запроса

Правила для каждого блока, где сверка была (поле не начинается с «не требовалась»):
1. Строк «опровержение…:» не меньше двух; в каждой — запрос в обратных кавычках или id источника.
2. Опровержение с id засчитывается, если хотя бы один его id — не из опор «за» этого поля и с другого домена
   (адрес из sources.csv). Иначе — ошибка «из того же источника или сайта». У открытых архивов статей (arxiv.org,
   ssrn.com и др., ARCHIVES) вместо сайта сравнивается статья: другая статья того же архива засчитывается.
3. «Не найдено» засчитывается как сделанный запрос, но не как опровержение. Если засчитанного опровержения нет
   ни одного, «Уверенность:» блока — только «низкая».

Проверка действует при профиле validation=web или full (и без профиля — v1): при method проверка по сути в веб не ходит.
Отчёт: tasks/<папка>/checks/refute.md. Код возврата 1 — есть ошибки (оркестратор: один перезапрос с отчётом).
"""
import csv
import os
import re
import sys
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import profile_lib  # noqa: E402

FILES = ("02c-validation.md", "02d-validation2.md")
MIN_REFUTE = 2
REF = re.compile(r"\bF-\d+\b")
HEAD = re.compile(r"^(?:\W*)(ГИПОТЕЗА\s+\d+|У-\d+)\b", re.M)
WEB_FIELD = re.compile(r"^(Сверка|Из сети)\s*:\s*(.*)$")
FIELD = re.compile(r"^[А-ЯЁ][А-Яа-яЁё ]{1,30}:")
REFUTE = re.compile(r"^\s*[-*]?\s*опровержение\b[^:«»\n]{0,80}:", re.I)  # «опровержение:», «опровержение из реестра (…):»


def read(path):
    return open(path, encoding="utf-8").read() if os.path.exists(path) else ""


def registry(task):
    try:
        with open(os.path.join(task, "sources.csv"), encoding="utf-8", newline="") as f:
            return {r["id"]: r for r in csv.DictReader(f)}
    except (OSError, KeyError):
        return {}


# Открытые архивы статей: на одном сайте лежат работы независимых авторов, поэтому граница независимости — статья,
# а не сайт. Версии одной статьи (…v2) — один источник.
ARCHIVES = ("arxiv.org", "ssrn.com", "biorxiv.org", "medrxiv.org", "osf.io", "zenodo.org", "openreview.net",
            "aclanthology.org", "hal.science", "researchgate.net", "semanticscholar.org")


def domain(row):
    loc = (row or {}).get("location", "")
    url = urlparse(loc) if "://" in loc else None
    host = url.netloc.lower() if url else ""
    host = host[4:] if host.startswith("www.") else host
    if any(host == a or host.endswith("." + a) for a in ARCHIVES):
        path = re.sub(r"(v\d+)?(\.pdf)?/?$", "", url.path.replace("/pdf/", "/abs/"))
        return "архив:%s%s" % (host, path)
    return host or ("файл:" + loc if loc else "")


def blocks(text):
    heads = list(HEAD.finditer(text))
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        yield m.group(1), text[m.start():end]


def web_field(block):
    """Поле сверки: первая строка и строки продолжения до следующего поля без отступа."""
    lines = block.splitlines()
    for i, line in enumerate(lines):
        m = WEB_FIELD.match(line)
        if not m:
            continue
        out = [m.group(2)]
        for nxt in lines[i + 1:]:
            if nxt.strip() and not nxt[:1].isspace() and FIELD.match(nxt):
                break
            out.append(nxt)
        return m.group(1), out
    return None, []


def confidence(block):
    m = re.search(r"^Уверенность\s*:\s*(\S+)", block, re.M)
    return m.group(1).lower().strip(".,;—-") if m else ""


def check_block(label, block, reg):
    errors = []
    name, lines = web_field(block)
    if name is None:
        return errors, None
    if re.match(r"^\s*[«\"]?\s*не требовал", lines[0], re.I):
        return errors, None
    refutes = [l for l in lines if REFUTE.match(l)]
    support = " ".join(l for l in lines if not REFUTE.match(l))
    own = set(REF.findall(support))
    own_domains = {domain(reg.get(i)) for i in own} - {""}
    if len(refutes) < MIN_REFUTE:
        errors.append("%s: строк «опровержение:» в поле «%s» %d, нужно не меньше %d" % (label, name, len(refutes), MIN_REFUTE))
    counted = 0
    for n, line in enumerate(refutes, 1):
        ids = set(REF.findall(line))
        if "`" not in line and not ids:
            errors.append("%s: опровержение %d без запроса в обратных кавычках и без id источника" % (label, n))
        if not ids:
            continue
        other = [i for i in ids - own if domain(reg.get(i)) not in own_domains]
        if other:
            counted += 1
        else:
            errors.append("%s: опровержение %d из того же источника или сайта, что опора «за»" % (label, n))
    if refutes and not counted and confidence(block) not in ("низкая",):
        errors.append("%s: засчитанных опровержений нет (только «не найдено»), а уверенность «%s» — допустима только "
                      "«низкая»" % (label, confidence(block) or "не указана"))
    return errors, (len(refutes), counted)


def main():
    if len(sys.argv) < 2:
        sys.stderr.write(__doc__)
        return 2
    task = sys.argv[1].rstrip("/")
    texts = [(f, read(os.path.join(task, f))) for f in FILES]
    texts = [(f, t) for f, t in texts if t]
    if not texts:
        print("Проверки по сути нет: проверять нечего.")
        return 0
    if profile_lib.has_profile(task) and profile_lib.load(task)["validation"] not in ("web", "full"):
        print("Опровержения: профиль validation=%s — проверка по сути в веб не ходит, не проверяется."
              % profile_lib.load(task)["validation"])
        return 0
    reg = registry(task)
    errors, stats = [], []
    for f, text in texts:
        for label, block in blocks(text):
            e, st = check_block("%s, %s" % (f, label), block, reg)
            errors += e
            if st:
                stats.append("%s, %s: строк %d, засчитано %d" % (f, label, st[0], st[1]))
    lines = ["# Опровержения в проверке по сути", ""] + (["- " + s for s in stats] or ["- блоков со сверкой нет"]) + [""]
    lines += (["Ошибки:"] + ["- " + e for e in errors]) if errors else ["Ошибок нет."]
    os.makedirs(os.path.join(task, "checks"), exist_ok=True)
    open(os.path.join(task, "checks", "refute.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print("Опровержения: %s" % ("ОШИБКИ (%d)" % len(errors) if errors else "ок"))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
