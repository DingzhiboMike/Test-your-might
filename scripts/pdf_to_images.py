#!/usr/bin/env python3
"""Выгружает страницы PDF в картинки: для слайдов и сканов, у которых нет текстового слоя.

  python3 scripts/pdf_to_images.py файл.pdf --out tasks/<папка>/sources/images [--dpi 130] [--pages 1-6]

Картинки читает агент сам (инструмент Read показывает изображения), расшифровку передаёт в add_source.py через stdin
с --read partial. Нужен PyMuPDF (pip install pymupdf) или pdftoppm из poppler (brew install poppler).
Печатает пути созданных файлов. Код возврата 1 — нечем рендерить.
"""
import argparse
import os
import shutil
import subprocess
import sys


def page_range(spec, total):
    if not spec:
        return list(range(total))
    out = set()
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-", 1)
            out.update(range(int(a) - 1, min(int(b), total)))
        else:
            out.add(int(part) - 1)
    return sorted(p for p in out if 0 <= p < total)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--out", required=True)
    ap.add_argument("--dpi", type=int, default=130)
    ap.add_argument("--pages", default="")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    base = os.path.splitext(os.path.basename(a.pdf))[0]
    try:
        import fitz
        with fitz.open(a.pdf) as doc:
            for i in page_range(a.pages, len(doc)):
                path = os.path.join(a.out, "{}-{:03d}.png".format(base, i + 1))
                doc[i].get_pixmap(dpi=a.dpi).save(path)
                print(path)
        return 0
    except ImportError:
        pass
    if shutil.which("pdftoppm"):
        cmd = ["pdftoppm", "-png", "-r", str(a.dpi)]
        if a.pages and "-" in a.pages and "," not in a.pages:
            lo, hi = a.pages.split("-", 1)
            cmd += ["-f", lo, "-l", hi]
        subprocess.run(cmd + [a.pdf, os.path.join(a.out, base)], check=True)
        for f in sorted(os.listdir(a.out)):
            if f.startswith(base) and f.endswith(".png"):
                print(os.path.join(a.out, f))
        return 0
    sys.stderr.write("нечем рендерить: pip install pymupdf или brew install poppler (python3 scripts/check_env.py)\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
