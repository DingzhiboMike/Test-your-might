#!/usr/bin/env python3
"""Картография документов, слой 1 (скрипт, без модели): нумерует строки текста и размечает теги.

  python3 scripts/map_docs.py tasks/<папка> [--force]

Для каждого источника контекста из `sources.csv` (kind = context, interview, from-tasks) берёт сырой текст
`sources/raw/<id>.txt`, очищает разметку (HTML, таблицы по строкам), нумерует непустые строки и размечает их
тегами: «число» (доля, размер группы, p-значение, N респондентов), «срез» (сегмент, портрет, оборот, новички,
отток), «продукт» (тариф, лимит, подписка, выгрузка, бонус), «риск» (ограничения и оговорки).

Словарь здесь — общий. Слова своего продукта и рынка (названия функций, видов продукта, сегментов) кладутся в
локальный файл .map-terms в корне — в git он не попадает, в репозиторий слова проектов не уходят. Формат: строка
«срез: слово», «продукт: слово» или «риск: слово»; слово — регулярное выражение (например, «продукт: подписк» — основа ловит все формы).
Путь можно переопределить переменной MAP_TERMS. Словарь входит в ключ кэша: поменял — карта пересчитается.

Результат: tasks/<папка>/map/<id>.json (строки и теги), tasks/<папка>/map/<id>.lines.txt (то, что читает лёгкая
модель: «L<номер>\\tтекст»), tasks/<папка>/map/index.csv. Карта кэшируется по хэшу сырого текста и версии скрипта:
неизменившийся документ не пересчитывается. Теги — не оценка важности, а список кандидатов и основа проверки
полноты (`check_map.py`): каждая строка с числом должна быть учтена в досье или отброшена с причиной.
"""
import csv
import hashlib
import html
import json
import os
import re
import sys

VERSION = "2"
KINDS = {"context", "interview", "from-tasks"}

NUM = re.compile(
    r"(\d[\d\s]*[,.]?\d*\s?(%|тыс\b|тыс\.|млн|к\b|руб|₽|п\.п))|(\d+\s*/\s*\d+)|(p[-\s]?value|p\s*=)"
    r"|(\d+\s*(респондент|клиент|человек|наблюден|интервью|участник))", re.I)
GRP_BASE = (r"ИП|ЮЛ|ООО|портрет\w*|оборот\w*|бросил\w*|никогда|ядр[оа]|новичк\w*|сегмент\w*|"
            r"отток\w*|отточн\w*|уснув\w*|спящ\w*|активн\w*")
PRD_BASE = (r"балл\w*|бонус\w*|лимит\w*|тариф\w*|подписк\w*|комисси\w*|выгрузк\w*|функци\w*|интеграци\w*|"
            r"программ\w* лояльн\w*")
RSK_BASE = (r"риск\w*|ограничени\w*|\bи так\b|не окуп\w*|не значим\w*|не прокраси\w*|не изменил\w*|"
            r"мощност\w*|не хватил\w*")


def local_terms():
    """Слова своего продукта и рынка из .map-terms (вне git): {категория: [регулярки]}."""
    path = os.environ.get("MAP_TERMS") or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                                       ".map-terms")
    out = {"срез": [], "продукт": [], "риск": []}
    try:
        for line in open(path, encoding="utf-8"):
            m = re.match(r"^\s*(срез|продукт|риск)\s*:\s*(\S.*?)\s*$", line)
            if m:
                re.compile(m.group(2))
                out[m.group(1)].append(m.group(2))
    except (OSError, re.error):
        pass
    return out


_LOCAL = local_terms()
VERSION += "+" + hashlib.sha256(repr(sorted(_LOCAL.items())).encode()).hexdigest()[:8] if any(_LOCAL.values()) else ""
GRP = re.compile(r"\b(%s)\b" % "|".join([GRP_BASE] + _LOCAL["срез"]), re.I)
PRD = re.compile(r"(%s)" % "|".join([PRD_BASE] + _LOCAL["продукт"]), re.I)
RSK = re.compile(r"(%s)" % "|".join([RSK_BASE] + _LOCAL["риск"]), re.I)


def clean(raw):
    t = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
    rows = []
    for tr in re.findall(r"(?is)<tr[^>]*>(.*?)</tr>", t):
        cells = [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", c))).strip()
                 for c in re.findall(r"(?is)<t[dh][^>]*>(.*?)</t[dh]>", tr)]
        cells = [c for c in cells if c]
        if len(cells) >= 2:
            rows.append(" | ".join(cells))
    t = re.sub(r"(?is)<tr[^>]*>.*?</tr>", "\n@@ROW@@\n", t)
    t = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</h\d>|</div>", "\n", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t)
    out, ri = [], 0
    for line in t.split("\n"):
        if line.strip() == "@@ROW@@":
            if ri < len(rows):
                out.append(rows[ri])
                ri += 1
            continue
        line = line.replace("\t", " | ")
        line = re.sub(r"[  ]+", " ", line).strip()
        if line:
            out.append(line)
    return out


LINE_LIMIT = 1000


def chunks(s, limit=LINE_LIMIT):
    """Длинную строку (статья одним абзацем) режем на куски до limit знаков по границам предложений и пробелов,
    а не обрезаем: иначе досье и модель предмета видят только начало документа."""
    if len(s) <= limit:
        return [s]
    out, cur = [], ""
    for part in re.split(r"(?<=[.!?…])\s+", s):
        while len(part) > limit:  # предложение длиннее лимита — режем по пробелу
            cut = part.rfind(" ", 0, limit)
            cut = cut if cut > limit // 2 else limit
            if cur:
                out.append(cur)
                cur = ""
            out.append(part[:cut].strip())
            part = part[cut:].strip()
        if cur and len(cur) + 1 + len(part) > limit:
            out.append(cur)
            cur = part
        else:
            cur = (cur + " " + part).strip()
    if cur:
        out.append(cur)
    return [c for c in out if c]


def tags(line):
    k = []
    if NUM.search(line):
        k.append("число")
    if GRP.search(line):
        k.append("срез")
    if PRD.search(line):
        k.append("продукт")
    if RSK.search(line):
        k.append("риск")
    return k


def sha(text):
    return hashlib.sha256((VERSION + "\n" + text).encode("utf-8")).hexdigest()


def sources(task):
    path = os.path.join(task, "sources.csv")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r.get("kind") in KINDS]


def build(task, force=False):
    mdir = os.path.join(task, "map")
    os.makedirs(mdir, exist_ok=True)
    index, done, cached = [], 0, 0
    for r in sources(task):
        rid = r["id"]
        rawp = os.path.join(task, "sources", "raw", rid + ".txt")
        if not os.path.exists(rawp):
            continue
        raw = open(rawp, encoding="utf-8", errors="ignore").read()
        h = sha(raw)
        jp = os.path.join(mdir, rid + ".json")
        data = None
        if not force and os.path.exists(jp):
            try:
                old = json.load(open(jp, encoding="utf-8"))
                if old.get("sha") == h and old.get("version") == VERSION:
                    data, cached = old, cached + 1
            except Exception:
                data = None
        if data is None:
            pieces = [c for s in clean(raw) for c in chunks(s)]
            lines = [{"n": i, "text": s, "tags": tags(s)} for i, s in enumerate(pieces, 1)]
            data = {"id": rid, "sha": h, "version": VERSION, "location": r.get("location", ""),
                    "read": r.get("read", ""), "lines": lines}
            json.dump(data, open(jp, "w", encoding="utf-8"), ensure_ascii=False)
            with open(os.path.join(mdir, rid + ".lines.txt"), "w", encoding="utf-8") as f:
                for l in lines:
                    f.write("L%d\t%s\n" % (l["n"], l["text"]))
            done += 1
        ls = data["lines"]
        index.append({"id": rid, "location": data["location"], "ctx_type": r.get("ctx_type", ""),
                      "read": data["read"], "lines": len(ls),
                      "tagged": sum(1 for l in ls if l["tags"]),
                      "numeric": sum(1 for l in ls if "число" in l["tags"]), "sha": h[:12]})
    with open(os.path.join(mdir, "index.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "location", "ctx_type", "read", "lines", "tagged", "numeric", "sha"])
        w.writeheader()
        w.writerows(index)
    return index, done, cached


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.stderr.write(__doc__)
        return 2
    task = args[0].rstrip("/")
    index, done, cached = build(task, "--force" in sys.argv)
    nl = sum(i["lines"] for i in index)
    nt = sum(i["tagged"] for i in index)
    print("Карта: документов %d (пересчитано %d, из кэша %d), строк %d, с тегами %d, строк с числами %d."
          % (len(index), done, cached, nl, nt, sum(i["numeric"] for i in index)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
