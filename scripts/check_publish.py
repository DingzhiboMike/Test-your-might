#!/usr/bin/env python3
"""Не даёт отправить на GitHub данные проектов: имена, партнёров, внутренние коды, слова из задач.

  python3 scripts/check_publish.py --all       # текущая ветка целиком: файлы и сообщения всех её коммитов
  python3 scripts/check_publish.py --pre-push  # из git-хука pre-push: только то, что сейчас уходит

Слова берутся из локальных файлов, которые в репозиторий не попадают:
- tasks/*/private.txt и tasks/*/closed-web.txt — имена, партнёры, коды из задач;
- .publish-stopwords в корне — свои слова, по одному в строке (названия продуктов, компаний); строки с # — комментарии.

Совпадение — без учёта регистра и ё/е, целым словом с падежным окончанием: у имён ищется основа без окончания
(как в check_private.py), поэтому «Марине» найдётся, а «маринад» по слову «Марина» — нет.
Найдено — код возврата 1 и список мест: отправка не проходит, пока слово не убрано или не заменено нейтральным примером.

Подключить хук в копии репозитория (один раз):  git config core.hooksPath scripts/git-hooks
"""
import glob
import os
import re
import subprocess
import sys

ZERO = "0" * 40
ENDINGS = r"(?:а|я|у|ю|е|и|ы|о|ой|ей|ом|ем|ью|ам|ям|ами|ями|ах|ях|ов|ев|ы|ий|ая|ое|ые)?"


def git(*args, root="."):
    return subprocess.run(["git", "-C", root] + list(args), capture_output=True, text=True).stdout


def norm(s):
    return s.replace("ё", "е").replace("Ё", "Е").lower()


def stem(term):
    t = term.strip()
    if len(t) >= 4 and t[-1].lower() in "аяйь":
        t = t[:-1]
    return t


def load_terms(root):
    files = glob.glob(os.path.join(root, "tasks", "*", "private.txt")) + \
        glob.glob(os.path.join(root, "tasks", "*", "closed-web.txt")) + [os.path.join(root, ".publish-stopwords")]
    terms = set()
    for path in files:
        if not os.path.exists(path):
            continue
        for line in open(path, encoding="utf-8"):
            t = line.strip()
            if t and not t.startswith("#"):
                terms.add(stem(t))
    rx = []
    for t in sorted(terms, key=len, reverse=True):
        body = re.escape(norm(t))
        # основа + падежное окончание, дальше граница слова: «Марине» ловится, «маринад» для «Марина» — нет
        pattern = r"(?<![\w])" + body + ENDINGS + r"(?![\w])"
        rx.append((t, re.compile(pattern)))
    return rx


def find(rx, text, where, hits):
    low = norm(text)
    for term, r in rx:
        for m in r.finditer(low):
            line = low.count("\n", 0, m.start()) + 1
            hits.append("%s:%d — «%s»" % (where, line, term))
            break


def scan_tree(rx, ref, root, hits):
    for f in git("ls-tree", "-r", "--name-only", ref, root=root).splitlines():
        if f.lower().endswith((".png", ".jpg", ".jpeg", ".pdf", ".bundle")):
            continue
        find(rx, git("show", "%s:%s" % (ref, f), root=root), f, hits)


def scan_messages(rx, rev_range, root, hits):
    out = git("log", "--format=%h%x00%B%x01", *rev_range, root=root)
    for block in out.split("\x01"):
        if "\x00" in block:
            h, body = block.strip().split("\x00", 1)
            find(rx, body, "сообщение коммита " + h, hits)


def scan_range(rx, local, remote, root, hits):
    if remote == ZERO:
        scan_tree(rx, local, root, hits)
        scan_messages(rx, [local, "--not", "--remotes"], root, hits)
        return
    diff = git("diff", "-U0", remote, local, root=root)
    cur = None
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            cur = line[6:]
        elif line.startswith("+") and not line.startswith("+++") and cur:
            find(rx, line[1:], cur, hits)
    scan_messages(rx, ["%s..%s" % (remote, local)], root, hits)


def main():
    root = git("rev-parse", "--show-toplevel").strip() or "."
    rx = load_terms(root)
    if not rx:
        print("Слов для проверки нет: tasks/*/private.txt, tasks/*/closed-web.txt и .publish-stopwords пусты.")
        return 0
    hits = []
    if "--pre-push" in sys.argv:
        for line in sys.stdin.read().splitlines():
            parts = line.split()
            if len(parts) == 4 and parts[1] != ZERO:
                scan_range(rx, parts[1], parts[3], root, hits)
    else:
        scan_tree(rx, "HEAD", root, hits)
        scan_messages(rx, ["HEAD"], root, hits)
    if hits:
        print("Данные проектов в том, что уходит на GitHub — отправка остановлена:")
        for h in sorted(set(hits)):
            print("  - " + h)
        print("Замени нейтральным примером (правка файла или git commit --amend) и отправь снова.")
        return 1
    print("Данных проектов не найдено (слов в списке: %d)." % len(rx))
    return 0


if __name__ == "__main__":
    sys.exit(main())
