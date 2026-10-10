#!/usr/bin/env python3
"""Сверяет цитаты в артефактах задачи с сырым текстом их источников.

Цитата-опора оформляется так: «дословный фрагмент» [F-007]. Пропуск внутри цитаты — «…».
Каждая часть цитаты должна найтись в tasks/<задача>/sources/raw/F-007.txt именно этого источника,
а не где угодно в задаче. Сравнение без учёта регистра, ё/е, вида кавычек, тире и пробелов.

Запускает оркестратор после шага, а не исполнитель:
  python3 scripts/check_quotes.py tasks/<папка>                  # все артефакты задачи
  python3 scripts/check_quotes.py tasks/<папка> 02c-validation.md

В отчёте проверки смысла (review-*.md) цитата текста артефакта оформляется «…» [A]. С флагом --check-a
скрипт сверяет её с артефактом из строки «Артефакт: <файл>» — так проверяющий не может процитировать то,
чего в тексте нет. Без флага такие цитаты пропускаются: после исправления артефакта они устаревают.

Пишет отчёт в tasks/<папка>/checks/quotes.md и печатает его.
Код возврата 1 — есть ошибки: цитата не найдена, ссылка на несуществующий источник,
опора на непрочитанный источник или только на пересказ.
"""
import csv
import os
import re
import sys
import unicodedata

SEP = r"[\s|—–:,;()]{0,8}"  # между цитатой и id: пробелы, разделитель колонки таблицы, тире
LONG_QUOTE_RE = re.compile(r"«([^«»]+)»(?!" + SEP + r"\[(?:F-\d|A\]))")
A_QUOTE_RE = re.compile(r"«([^«»]{3,}?)»" + SEP + r"\[A\]")
ART_RE = re.compile(r"^Артефакт:\s*(\S+)", re.M)
QUOTE_RE = re.compile(r"«([^«»]{3,}?)»" + SEP + r"\[(F-\d{3,})\]")
URL_RE = re.compile(r"https?://[^\s)\]>|«»\"']+")
REF_RE = re.compile(r"\[(F-\d{3,})\]")
SKIP = {"log.md", "00-tz.md"}


def norm(s):
    s = unicodedata.normalize("NFKC", s).lower().replace("ё", "е")
    s = s.replace("­", "")
    s = re.sub(r"[‐‑‒–—―−]", "-", s)
    s = re.sub(r"[\"'“”„‟‘’‚‛«»`]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def parts(quote):
    pieces = re.split(r"…|\.\.\.|\[\.\.\.\]|\(\.\.\.\)", quote)
    return [norm(p).strip(" .,;:") for p in pieces if norm(p).strip(" .,;:")]


def load_registry(task):
    path = os.path.join(task, "sources.csv")
    if not os.path.exists(path):
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        return {r["id"]: r for r in csv.DictReader(f)}


def root_of(sid, reg, seen=None):
    seen = seen or set()
    r = reg.get(sid)
    if not r or sid in seen:
        return sid
    root = (r.get("root") or "self").strip()
    if root in ("self", ""):
        return sid
    if root in reg:
        return root_of(root, reg, seen | {sid})
    return root  # адрес оригинала, который сам не открывали


def found_in_order(pieces, text):
    pos = 0
    for p in pieces:
        i = text.find(p, pos)
        if i < 0:
            return p
        pos = i + len(p)
    return None


def main():
    if len(sys.argv) < 2:
        sys.stderr.write(__doc__)
        sys.exit(2)
    args = [x for x in sys.argv[1:] if x != "--check-a"]
    check_a = "--check-a" in sys.argv
    task = args[0].rstrip("/")
    names = args[1:] or sorted(n for n in os.listdir(task) if n.endswith(".md") and n not in SKIP)
    reg = load_registry(task)
    raw_cache = {}

    def raw(sid):
        if sid not in raw_cache:
            p = os.path.join(task, "sources", "raw", sid + ".txt")
            raw_cache[sid] = norm(open(p, encoding="utf-8").read()) if os.path.exists(p) else None
        return raw_cache[sid]

    out, errors = [], 0
    out.append("# Проверка цитат: " + os.path.basename(task))
    out.append("")
    out.append("Источников в реестре: {}.".format(len(reg)))
    for name in names:
        path = os.path.join(task, name)
        if not os.path.exists(path):
            out += ["", "## " + name, "- ОШИБКА: файла нет"]
            errors += 1
            continue
        text = open(path, encoding="utf-8").read()
        quotes = QUOTE_RE.findall(text)
        refs = set(REF_RE.findall(text))
        loose = [q for q in LONG_QUOTE_RE.findall(text) if len(q.split()) >= 6]
        known = {r["location"].rstrip("/") for r in reg.values()}
        stray = sorted({u.rstrip(".,;/") for u in URL_RE.findall(text)} - {k.rstrip(".,;/") for k in known})
        if not refs and not loose and not stray and not (check_a and A_QUOTE_RE.search(text)):
            continue
        problems = []
        for q, sid in quotes:
            r = reg.get(sid)
            short = (q[:80] + "…") if len(q) > 80 else q
            if not r:
                problems.append("ОШИБКА [{}] нет в реестре: «{}»".format(sid, short))
                continue
            if r.get("read") == "not-read":
                problems.append("ОШИБКА [{}] источник не прочитан, опорой быть не может: «{}»".format(sid, short))
                continue
            if r.get("method") == "summary":
                problems.append("ОШИБКА [{}] есть только пересказ инструмента, не сырой текст: «{}»".format(sid, short))
                continue
            body = raw(sid)
            if body is None:
                problems.append("ОШИБКА [{}] нет сырого текста sources/raw/{}.txt".format(sid, sid))
                continue
            miss = found_in_order(parts(q), body)
            if miss is not None:
                problems.append("ОШИБКА [{}] не найдено в источнике: «{}»".format(sid, short))
        for sid in sorted(refs - set(reg)):
            if sid not in {s for _, s in quotes}:
                problems.append("ОШИБКА [{}] ссылка на источник, которого нет в реестре".format(sid))
        a_quotes = A_QUOTE_RE.findall(text) if check_a else []
        if a_quotes:
            m = ART_RE.search(text)
            target = os.path.join(task, m.group(1)) if m else None
            if not target or not os.path.exists(target):
                problems.append("ОШИБКА нет строки «Артефакт: <файл>» или файла артефакта — цитаты [A] не с чем сверить")
            else:
                art = norm(open(target, encoding="utf-8").read())
                for q in a_quotes:
                    if found_in_order(parts(q), art) is not None:
                        short = (q[:80] + "…") if len(q) > 80 else q
                        problems.append("ОШИБКА [A] нет в артефакте {}: «{}»".format(m.group(1), short))
        errors += len(problems)

        used = [reg[s] for s in refs if s in reg]
        roots = {root_of(s, reg) for s in refs if s in reg}
        levels = sorted({r["level"] for r in used if r.get("level")})
        ctx = sorted({r["ctx_type"] for r in used if r.get("ctx_type")})
        partial = sorted(s for s in refs if s in reg and reg[s].get("read") in ("partial", "snippet"))
        by_agent = sorted(s for s in refs if s in reg and reg[s].get("fetched") == "agent")
        claims = sorted(s for s in refs if s in reg and reg[s].get("ctx_type") == "claim")
        system = sorted(s for s in refs if s in reg and reg[s].get("ctx_type") == "system")
        out += ["", "## " + name,
                "- цитат проверено: {}{}, ошибок: {}".format(len(quotes), " (+ {} цитат артефакта)".format(len(a_quotes)) if a_quotes else "", len(problems)),
                "- источников: {}, независимых корней: {}".format(len(used), len(roots)),
                "- уровни веба: {}; типы контекста: {}".format(", ".join(levels) or "—", ", ".join(ctx) or "—")]
        if partial:
            out.append("- прочитаны не целиком: " + ", ".join(partial))
        if by_agent:
            out.append("- текст веба подан агентом, а не скачан скриптом: " + ", ".join(by_agent))
        if claims:
            out.append("- внимание: ссылки на утверждения команды ({}) — это то, что проверяется, опорой они не служат".format(", ".join(claims)))
        if system:
            out.append("- внимание: ссылки на материалы прошлых задач ({}) — опора только через исходный фрагмент, который в них приведён".format(", ".join(system)))
        if stray:
            out.append("- внимание: ссылок вне реестра — {}; опорой они не считаются. Первая: {}".format(len(stray), stray[0]))
        if loose:
            out.append("- внимание: цитат без id источника — {}; опорой они не считаются. Первая: «{}»".format(
                len(loose), (loose[0][:80] + "…") if len(loose[0]) > 80 else loose[0]))
        out += ["- " + p for p in problems]

    if errors == 0:
        out += ["", "Итог: ошибок нет."]
    else:
        out += ["", "Итог: ошибок {}. Исправить: найти верный фрагмент, или снять утверждение, "
                    "или пометить «первоисточник не прочитан». Переклассифицировать ошибку нельзя.".format(errors)]
    report = "\n".join(out) + "\n"
    os.makedirs(os.path.join(task, "checks"), exist_ok=True)
    with open(os.path.join(task, "checks", "quotes.md"), "w", encoding="utf-8") as f:
        f.write(report)
    sys.stdout.write(report)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
