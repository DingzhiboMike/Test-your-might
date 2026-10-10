#!/usr/bin/env python3
"""Проверяет артефакт шага и то, что исполнитель не тронул чужие файлы.

Оркестратор перед вызовом скилла запоминает время (`date +%s`), после — запускает:
  python3 scripts/check_artifact.py tasks/<папка> 02-hypotheses.md --since 1767000000

Пачка параллельных исполнителей (например, разборы интервью) — одной командой, по маске:
  python3 scripts/check_artifact.py tasks/<папка> 'src-interview-*.md' --since 1767000000
Каждый файл по маске проверяется отдельно; при проверке периметра соседние файлы пачки не считаются чужими.

После исправления по проверке смысла — ещё и ответы на замечания:
  python3 scripts/check_artifact.py tasks/<папка> src-market.md --review review-src-market.md

Для отчёта-исследования — что блок счёта опор перенесён дословно (его считает trust_map.py):
  python3 scripts/check_artifact.py tasks/<папка> 06-research.md --contains checks/trust.md

Проверяет:
- файл артефакта есть, не пустой и не состоит из одного резюме или «сигнала оркестратору»;
- с --review: на каждое блокирующее замечание из отчёта проверки в артефакте есть ответ
  «С-01 — исправлено / снято / оспорено: …» в блоке «ПО ПРОВЕРКЕ СМЫСЛА» (формат гибкий, см. review_format.py);
- после --since в папке задачи не менялись другие файлы, кроме: реестра источников (sources.csv, sources/),
  checks/, log.md и 00-tz.md (их ведёт оркестратор и диспетчер), private.txt, файлов пачки и путей из --allow.

Код возврата 1 — что-то не так; что именно, печатается.
"""
import argparse
import fnmatch
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import review_format as rf  # noqa: E402

MIN_CHARS = 400
ALWAYS_OK = ("sources.csv", "sources/", "checks/", "log.md", "00-tz.md", "private.txt")


def norm_rel(p):
    return p.replace(os.sep, "/")


def is_allowed(rel, patterns):
    rel = norm_rel(rel)
    for x in patterns:
        if x.endswith("/"):
            if rel.startswith(x):
                return True
        elif fnmatch.fnmatch(rel, x):
            return True
    return False


def check_one(task, artifact, contains, review):
    problems = []
    path = os.path.join(task, artifact)
    if not os.path.exists(path):
        return ["{}: артефакта нет".format(artifact)]
    text = open(path, encoding="utf-8").read()
    body = [l for l in text.splitlines() if l.strip() and not l.lstrip().startswith("#")]
    if len(text.strip()) < MIN_CHARS:
        problems.append("{}: короче {} знаков — похоже на резюме вместо полного текста".format(artifact, MIN_CHARS))
    if body and body[0].lower().lstrip("*# ").startswith(("сигнал", "резюме", "результат записан")):
        problems.append("{}: начинается с сигнала или резюме, а не с формата выхода скилла".format(artifact))

    body_norm = re.sub(r"\s+", " ", text)
    for rel in contains:
        cp = os.path.join(task, rel)
        if not os.path.exists(cp):
            problems.append("{}: нет файла для сверки {}".format(artifact, rel))
        elif re.sub(r"\s+", " ", open(cp, encoding="utf-8").read()).strip() not in body_norm:
            problems.append("{}: нет дословного блока из {} — перенеси его целиком, не пересказывай".format(artifact, rel))

    if review:
        rpath = os.path.join(task, review)
        if not os.path.exists(rpath):
            problems.append("{}: отчёта проверки нет: {}".format(artifact, review))
        else:
            blocking = rf.blocking_ids(open(rpath, encoding="utf-8").read())
            block = rf.answer_block(text)
            if blocking and block is None:
                problems.append("{}: нет блока «ПО ПРОВЕРКЕ СМЫСЛА» с ответами на замечания".format(artifact))
            elif blocking:
                ans = rf.answers(block)
                for fid in blocking:
                    if fid not in ans:
                        problems.append("{}: нет ответа на блокирующее замечание {}".format(artifact, fid))
                for fid, (status, reason) in ans.items():
                    if status == "оспорено" and not reason:
                        problems.append("{}: замечание {} оспорено без причины (нужно «{} — оспорено: причина»)".format(artifact, fid, fid))
    return problems


def main():
    p = argparse.ArgumentParser()
    p.add_argument("task")
    p.add_argument("artifact", help="файл артефакта или маска, например 'src-interview-*.md'")
    p.add_argument("--since", type=float, default=0, help="время начала шага, секунды Unix")
    p.add_argument("--allow", action="append", default=[], help="ещё разрешённый путь или маска внутри задачи (папка — с / на конце)")
    p.add_argument("--contains", action="append", default=[], help="файл внутри задачи, содержимое которого должно входить в артефакт дословно")
    p.add_argument("--review", default="", help="отчёт проверки смысла, на который артефакт должен ответить (только для одного файла)")
    a = p.parse_args()

    if any(ch in a.artifact for ch in "*?["):
        names = sorted(norm_rel(os.path.relpath(x, a.task)) for x in glob.glob(os.path.join(a.task, a.artifact)))
        if not names:
            print("ОШИБКА по маске {} в {} ничего нет".format(a.artifact, a.task))
            sys.exit(1)
        if a.review:
            print("ОШИБКА --review работает только с одним файлом, а не с маской")
            sys.exit(2)
    else:
        names = [a.artifact]

    problems = []
    for name in names:
        problems += check_one(a.task, name, a.contains, a.review)

    if a.since:
        allowed = list(ALWAYS_OK) + names + a.allow
        for root, _, files in os.walk(a.task):
            for f in files:
                full = os.path.join(root, f)
                if os.path.getmtime(full) < a.since:
                    continue
                rel = os.path.relpath(full, a.task)
                if not is_allowed(rel, allowed):
                    problems.append("изменён файл вне периметра шага: " + norm_rel(rel))

    if problems:
        print("\n".join("ОШИБКА " + x for x in problems))
        sys.exit(1)
    print("ок: " + (a.artifact if len(names) == 1 else "{} ({} файлов)".format(a.artifact, len(names))))


if __name__ == "__main__":
    main()
