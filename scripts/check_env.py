#!/usr/bin/env python3
"""Проверяет, чем система умеет читать файлы и страницы, и печатает команды установки недостающего.

  python3 scripts/check_env.py [--strict] [--web]

Ничего не ставит. Код возврата всегда 0, с --strict — 1, если не хватает читателя PDF (или, вместе с --web, если
внешний веб закрыт).

--web — проверить выход во внешний веб: два запроса по HTTPS с коротким таймаутом. Это проверка из скриптов
(add_source.py --fetch ходит тем же путём). Инструменты агента — поиск и чтение страниц — идут другим путём, поэтому
перед «ВЕБ: да» диспетчер делает ещё один пробный вызов поиска сам.
Список пакетов — requirements.txt: pip install -r requirements.txt
"""
import importlib
import os
import shutil
import sys
import urllib.request

WEB_PROBES = ("https://example.com/", "https://www.wikipedia.org/")

PY_TOOLS = [
    ("pymupdf", "fitz", "PDF с текстом, страницы в картинки для слайдов и сканов"),
    ("pypdf", "pypdf", "PDF с текстом, запасной читатель"),
    ("openpyxl", "openpyxl", ".xlsx; без него таблицы читаются прямым разбором архива"),
    ("python-pptx", "pptx", "не нужен: .pptx читается прямым разбором архива"),
    ("trafilatura", "trafilatura", "текст веб-страниц без шума; без него — разбор HTML регулярками"),
]
BIN_TOOLS = [
    ("pdftotext", "brew install poppler", "PDF с разметкой колонок"),
    ("pdftoppm", "brew install poppler", "страницы PDF в картинки, если нет pymupdf"),
    ("tesseract", "brew install tesseract tesseract-lang", "необязателен: распознавание сканов; слайды агент читает по картинкам сам"),
]


def web_ok():
    """True, если хотя бы один адрес ответил; иначе (False, причина последней ошибки)."""
    reason = ""
    for url in WEB_PROBES:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "polygon-check-env"})
            with urllib.request.urlopen(req, timeout=6) as r:
                if r.status < 500:
                    return True, ""
        except Exception as e:  # сеть закрыта, DNS, прокси, песочница
            reason = type(e).__name__ + ": " + str(e)[:120]
    return False, reason


def main():
    strict = "--strict" in sys.argv
    print("Python {}.{}.{}".format(*sys.version_info[:3]))
    print("CLAUDE_PROJECT_DIR: " + (os.environ.get("CLAUDE_PROJECT_DIR") or "не задан — хуки не сработают, открой Claude Code в корне проекта"))
    have = {}
    print("\nПакеты Python:")
    for name, mod, why in PY_TOOLS:
        try:
            importlib.import_module(mod)
            have[name] = True
        except Exception:
            have[name] = False
        print("  {} {:<12} {}".format("есть " if have[name] else "нет  ", name, why))
    print("\nПрограммы:")
    for name, how, why in BIN_TOOLS:
        have[name] = bool(shutil.which(name))
        print("  {} {:<10} {}{}".format("есть " if have[name] else "нет  ", name, why, "" if have[name] else "  → " + how))
    pdf_ok = have["pymupdf"] or have["pypdf"] or have["pdftotext"]
    print("\nЧтение PDF с текстом: " + ("работает" if pdf_ok else "НЕ работает"))
    print("Страницы PDF в картинки: " + ("работает" if have["pymupdf"] or have["pdftoppm"] else "не работает (слайды-картинки не прочитать)"))
    missing = [n for n, ok in have.items() if not ok and n in ("pymupdf", "pypdf", "openpyxl", "trafilatura")]
    if missing:
        print("\nУстановить: pip install -r requirements.txt   (нет: " + ", ".join(missing) + ")")
    web_fail = False
    if "--web" in sys.argv:
        ok, reason = web_ok()
        web_fail = not ok
        print("\nВнешний веб из скриптов: " + ("доступен" if ok else "ЗАКРЫТ (" + reason + ") — «ВЕБ: да» ставить нельзя, "
                                               "пока сеть не открыта; что останется несверенным — в ТЗ"))
    return 1 if strict and (not pdf_ok or web_fail) else 0


if __name__ == "__main__":
    sys.exit(main())
