#!/usr/bin/env python3
"""Готовые артефакты для тестов отдельных навыков: развернуть выдуманную задачу до нужного шага.

  python3 scripts/fixture.py list
  python3 scripts/fixture.py make light --task tasks/_fx-1 --upto knowledge

Фикстура лежит в tests/fixtures/<имя>/ и содержит выдуманный контекст, согласованное ТЗ, реестр источников и
готовые артефакты шагов. Тест навыка начинается с его шага и не оплачивает предыдущие: диспетчера, разбор материалов,
консультанта.

Шаги по порядку (--upto включает всё до него):
  tz         00-tz.md, контекст, реестр источников (sources.csv, sources/raw/)
  knowledge  + 00k-knowledge.md    — вход консультанта
  review     + 01-review.md        — вход генератора, источников данных, проверки по сути

Развёрнутая папка задачи лежит в tasks/ и в git не попадает. Артефакты фикстуры выдуманные и всегда проходят
проверки формы (цитаты, карта знания, путь); это проверяет selftest.py.
"""
import argparse
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIX = os.path.join(ROOT, "tests", "fixtures")
STAGES = [("tz", ["00-tz.md", "context", "sources", "sources.csv"]),
          ("knowledge", ["00k-knowledge.md"]),
          ("review", ["01-review.md"])]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    m = sub.add_parser("make")
    m.add_argument("name")
    m.add_argument("--task", required=True, help="куда развернуть: tasks/<папка>")
    m.add_argument("--upto", default="review", choices=[s for s, _ in STAGES])
    a = p.parse_args()
    if a.cmd == "list":
        for n in sorted(os.listdir(FIX)) if os.path.isdir(FIX) else []:
            print(n)
        return 0
    src = os.path.join(FIX, a.name)
    if not os.path.isdir(src):
        sys.exit("fixture: нет фикстуры %s (python3 scripts/fixture.py list)" % a.name)
    if os.path.exists(a.task) and os.listdir(a.task):
        sys.exit("fixture: папка %s не пуста — возьми новую" % a.task)
    os.makedirs(a.task, exist_ok=True)
    done = []
    for stage, names in STAGES:
        for n in names:
            s, d = os.path.join(src, n), os.path.join(a.task, n)
            if os.path.isdir(s):
                shutil.copytree(s, d)
            else:
                shutil.copy(s, d)
        done.append(stage)
        if stage == a.upto:
            break
    open(os.path.join(a.task, "log.md"), "w", encoding="utf-8").write(
        "# Лог задачи (фикстура %s)\n\nШаги до «%s» взяты из фикстуры, не выполнялись.\n" % (a.name, a.upto))
    print("фикстура %s развёрнута в %s до шага: %s" % (a.name, a.task, ", ".join(done)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
