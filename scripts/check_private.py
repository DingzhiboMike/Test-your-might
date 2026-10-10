#!/usr/bin/env python3
"""Ищет персональные данные в артефактах задачи и в логе (там лежат запросы в веб).

  python3 scripts/check_private.py tasks/<папка>

Что считается персональными данными:
- по шаблону: e-mail, телефон, ИНН (слово ИНН рядом с номером), номер карты или счёта (16–20 цифр),
  паспорт или СНИЛС с номером; голые 10 или 12 цифр подряд — предупреждение;
- по списку задачи: tasks/<папка>/private.txt — по строке на термин, в основном имена респондентов
  и интервьюеров. Основу без окончания проверка выводит сама (Ольга → Ольг, Марина → Марин), так что полная форма тоже годится:
  она ищет слова, которые с основы начинаются (Ольгу, Марине, Ольгой…). Строки с # — комментарии.

Закрытые слова для веба: tasks/<папка>/closed-web.txt (партнёры, акции, продукты). В артефактах они допустимы, в блоках «Запросы:» лога (там лежат запросы в веб) нет.

Не проверяет: 00-tz.md и 00-hypotheses-in.md (там список материалов, он внутренний), sources.csv,
sources/raw/ (сырой текст лежит локально), checks/.

В отчёт найденное НЕ копируется: только файл, строка и вид («телефон», «термин из private.txt»),
чтобы проверка сама не размножала персональные данные. Отчёт: tasks/<папка>/checks/private.md.
Код возврата 1 — найдено что-то из шаблонов или списка.
"""
import os
import re
import sys

SKIP = {"00-tz.md", "00-hypotheses-in.md"}

ERROR_PATTERNS = [
    ("e-mail", re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")),
    ("телефон", re.compile(r"(?:\+7|\b8)[\s(\-]*\d{3}[\s)\-]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}\b")),
    ("ИНН", re.compile(r"ИНН\D{0,12}\d{10,12}", re.I)),
    ("номер карты или счёта", re.compile(r"\b\d{16,20}\b")),
    ("паспорт или СНИЛС с номером", re.compile(r"(?:паспорт|СНИЛС)\D{0,15}\d[\d\s\-]{6,}", re.I)),
]
WARN_PATTERNS = [
    ("10 или 12 цифр подряд (возможно ИНН)", re.compile(r"\b\d{10}\b|\b\d{12}\b")),
]


def stem(term):
    """Основа имени без окончания: Ольга → Ольг, Марина → Марин. Так проверка ловит все падежи,
    даже если в private.txt записана полная форма."""
    t = term.strip()
    if len(t) >= 4 and t[-1].lower() in "аяйь":
        return t[:-1]
    return t


def load_terms(task):
    path = os.path.join(task, "private.txt")
    if not os.path.exists(path):
        return []
    terms = []
    for line in open(path, encoding="utf-8"):
        t = line.strip()
        if t and not t.startswith("#"):
            terms.append(t)
    return terms


def load_closed_web(task):
    path = os.path.join(task, "closed-web.txt")
    if not os.path.exists(path):
        return []
    return [t.strip() for t in open(path, encoding="utf-8") if t.strip() and not t.strip().startswith("#")]


FIELD = re.compile(r"^[А-ЯЁA-Za-zа-яё\[(][^\n]{0,40}:\s")


def query_lines(log):
    """Строки блоков «Запросы:» в логе: от строки «Запросы:» до следующего поля или пустой строки."""
    inside = False
    for i, line in enumerate(log.splitlines(), 1):
        if line.startswith("Запросы:"):
            inside = True
        elif inside and (not line.strip() or (FIELD.match(line) and not line.startswith(" "))):
            inside = False
        if inside:
            yield i, line


def main():
    if len(sys.argv) < 2:
        sys.stderr.write(__doc__)
        sys.exit(2)
    task = sys.argv[1].rstrip("/")
    terms = load_terms(task)
    term_res = [(t, re.compile(r"\b" + re.escape(stem(t)) + r"\w*", re.I)) for t in terms]
    errors, warns = [], []
    names = sorted(n for n in os.listdir(task) if n.endswith(".md") and n not in SKIP)
    for name in names:
        for i, line in enumerate(open(os.path.join(task, name), encoding="utf-8").read().splitlines(), 1):
            for kind, rx in ERROR_PATTERNS:
                if rx.search(line):
                    errors.append("{}:{} — {}".format(name, i, kind))
            for kind, rx in WARN_PATTERNS:
                if rx.search(line) and not any(rx2.search(line) for _, rx2 in ERROR_PATTERNS):
                    warns.append("{}:{} — {}".format(name, i, kind))
            for t, rx in term_res:
                if rx.search(line):
                    errors.append("{}:{} — термин из private.txt: {}".format(name, i, t))

    closed = load_closed_web(task)
    logpath = os.path.join(task, "log.md")
    if closed and os.path.exists(logpath):
        crx = [(t, re.compile(r"\b" + re.escape(stem(t)) + r"\w*", re.I)) for t in closed]
        for i, line in query_lines(open(logpath, encoding="utf-8").read()):
            for t, rx in crx:
                if rx.search(line):
                    errors.append("log.md:{} — закрытое слово из closed-web.txt в запросе в веб: {}".format(i, t))

    out = ["# Проверка персональных данных: " + os.path.basename(task), "",
           "Файлов проверено: {}. Терминов в private.txt: {}.".format(len(names), len(terms))]
    if not terms:
        out.append("private.txt нет или пуст: имена не проверялись, только шаблоны.")
    out += ["", "## Ошибки"] + (["- " + e for e in errors] or ["- нет"])
    out += ["", "## Предупреждения"] + (["- " + w for w in warns] or ["- нет"])
    if errors:
        out += ["", "Исправить: заменить имена на «Интервью N, сегмент» или «Респондент N»; цитату сократить через «…» "
                    "так, чтобы личное в неё не попало; в запросах в веб личного нет вообще."]
    report = "\n".join(out) + "\n"
    os.makedirs(os.path.join(task, "checks"), exist_ok=True)
    with open(os.path.join(task, "checks", "private.md"), "w", encoding="utf-8") as f:
        f.write(report)
    sys.stdout.write(report)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
