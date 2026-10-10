#!/usr/bin/env python3
"""Проверяет, чем система умеет читать файлы и страницы, и печатает команды установки недостающего.

  python3 scripts/check_env.py [--strict]

Ничего не ставит. Код возврата всегда 0, с --strict — 1, если не хватает читателя PDF.
Список пакетов — requirements.txt: pip install -r requirements.txt
"""
import importlib
import os
import shutil
import sys

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
    return 1 if strict and not pdf_ok else 0


if __name__ == "__main__":
    sys.exit(main())
