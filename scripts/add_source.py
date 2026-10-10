#!/usr/bin/env python3
"""Регистрирует источник в реестре задачи и сохраняет его сырой текст.

Реестр: tasks/<задача>/sources.csv. Сырой текст: tasks/<задача>/sources/raw/<id>.txt.
На этот текст потом ссылаются цитаты в артефактах («…» [F-007]), и scripts/check_quotes.py
сверяет их механически. Пиши в реестр только этим скриптом: поля проверяются при записи.

Веб-страница — скрипт скачивает сам (так текст точно со страницы, а не из памяти агента):
  python3 scripts/add_source.py --task tasks/<папка> --kind web --location <адрес> --fetch \
      --level 1 --pub-date 2025-03-10

Если страница не отдаётся простым запросом (JavaScript, антибот), — текст через stdin, полученный
браузером без окна; тогда в реестре fetched = agent:
  <текст страницы> | python3 scripts/add_source.py --task tasks/<папка> --kind web --location <адрес> --level 1

Файл контекста или транскрипт (текст берётся из файла):
  python3 scripts/add_source.py --task tasks/<папка> --kind interview \
      --location context/interviews/ivanov.md --ctx-type voice --author "Иванов, финдир" --pub-date 2026-08-01

Файлы .docx (транскрипты, документы) скрипт читает сам: текст абзацев и таблиц. PDF — через pdftotext,
PyMuPDF или pypdf, что найдётся (скан или слайды без текстового слоя отклоняются с подсказкой, как выгрузить страницы
в картинки). Таблицы .xlsx и презентации .pptx читаются сами. Другой бинарный формат отклоняется с подсказкой:
сначала конвертируй в текст. Что установлено — python3 scripts/check_env.py.

Печатает id источника. Тот же адрес с тем же текстом повторно не регистрируется — возвращается прежний id.
"""
import argparse
import csv
import datetime
import hashlib
import os
import re
import subprocess
import sys
import time
import urllib.request

FIELDS = [
    "id", "kind", "location", "level", "ctx_type", "author", "pub_date", "data_date",
    "opened", "read", "method", "root", "status", "fetched", "sha256", "chars", "note", "ts",
]

KINDS = {"web", "context", "interview", "from-tasks"}
LEVELS = {"1", "2", "3", "4"}
CTX_TYPES = {"claim", "voice", "data", "result", "system", "other"}
READ = {"full", "partial", "snippet", "not-read"}
METHODS = {"raw", "summary"}
STATUSES = {"final", "draft", "outdated", "unknown"}
DATE_RE = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")


def fail(msg):
    sys.stderr.write("add_source: " + msg + "\n")
    sys.exit(2)


def check_date(name, value):
    if value and value != "unknown" and not DATE_RE.match(value):
        fail("{}: дата в формате ГГГГ, ГГГГ-ММ или ГГГГ-ММ-ДД, или unknown; получено {!r}".format(name, value))


def read_docx(path):
    """Текст .docx: абзацы и ячейки таблиц, по абзацу на строку."""
    import xml.etree.ElementTree as ET
    import zipfile
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    try:
        with zipfile.ZipFile(path) as z:
            root = ET.fromstring(z.read("word/document.xml"))
    except Exception as e:
        fail("не удалось прочитать .docx ({}): {}".format(path, e))
    paras = []
    for p in root.iter(ns + "p"):
        parts = []
        for el in p.iter():
            if el.tag == ns + "t":
                parts.append(el.text or "")
            elif el.tag == ns + "tab":
                parts.append("\t")
            elif el.tag in (ns + "br", ns + "cr"):
                parts.append("\n")
        paras.append("".join(parts))
    return "\n".join(paras)


def has_text(text):
    """Есть ли в извлечённом тексте что-то кроме пробелов: у PDF из слайдов-картинок текстового слоя нет."""
    return len(re.sub(r"\s", "", text or "")) >= 40


def read_pdf(path):
    """PDF: pdftotext, потом PyMuPDF, потом pypdf. Первый, что дал текст. Нет текстового слоя — понятная ошибка."""
    tried = []
    try:
        out = subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True, check=True).stdout.decode("utf-8", "replace")
        if has_text(out):
            return out
        tried.append("pdftotext: текста нет")
    except Exception:
        tried.append("pdftotext не установлен")
    try:
        import fitz
        with fitz.open(path) as doc:
            out = "\n\f".join(page.get_text() for page in doc)
        if has_text(out):
            return out
        tried.append("pymupdf: текста нет")
    except ImportError:
        tried.append("pymupdf не установлен")
    except Exception as e:
        tried.append("pymupdf: {}".format(e))
    try:
        from pypdf import PdfReader
        out = "\n\f".join((p.extract_text() or "") for p in PdfReader(path).pages)
        if has_text(out):
            return out
        tried.append("pypdf: текста нет")
    except ImportError:
        tried.append("pypdf не установлен")
    except Exception as e:
        tried.append("pypdf: {}".format(e))
    if any("текста нет" in t for t in tried):
        fail("PDF без текстового слоя (слайды-картинки или скан): {}. Выгрузи страницы в картинки: "
             "python3 scripts/pdf_to_images.py {} --out tasks/<папка>/sources/images, прочитай их и передай расшифровку "
             "через stdin с --read partial: цитаты из ручной расшифровки проверяются только по ней ({})".format(path, path, "; ".join(tried)))
    fail("PDF не прочитан ({}). Установи один читатель: pip install -r requirements.txt (pymupdf, pypdf) "
         "или brew install poppler; проверка окружения: python3 scripts/check_env.py".format("; ".join(tried)))


def _xml_texts(root, ns_tag):
    return "".join(el.text or "" for el in root.iter(ns_tag))


def read_xlsx(path):
    """Таблица: по листу «Лист: имя» и строкам через табуляцию. Через openpyxl, без него — прямым разбором архива."""
    try:
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        out = []
        for ws in wb.worksheets:
            out.append("Лист: " + ws.title)
            for row in ws.iter_rows(values_only=True):
                cells = ["" if v is None else str(v) for v in row]
                if any(c.strip() for c in cells):
                    out.append("\t".join(cells).rstrip())
        return "\n".join(out)
    except Exception:
        pass  # нет openpyxl или он не справился с файлом: читаем архив напрямую
    import xml.etree.ElementTree as ET
    import zipfile
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    try:
        with zipfile.ZipFile(path) as z:
            shared = []
            if "xl/sharedStrings.xml" in z.namelist():
                for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(ns + "si"):
                    shared.append(_xml_texts(si, ns + "t"))
            sheets = sorted((n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", n)),
                            key=lambda n: int(re.search(r"(\d+)\.xml$", n).group(1)))
            out = []
            for n in sheets:
                out.append("Лист: " + re.search(r"(sheet\d+)", n).group(1))
                for row in ET.fromstring(z.read(n)).iter(ns + "row"):
                    cells = []
                    for c in row.iter(ns + "c"):
                        v = c.find(ns + "v")
                        if c.get("t") == "s" and v is not None and (v.text or "").isdigit():
                            cells.append(shared[int(v.text)])
                        elif c.get("t") == "inlineStr":
                            cells.append(_xml_texts(c, ns + "t"))
                        else:
                            cells.append(v.text if v is not None and v.text else "")
                    if any(x.strip() for x in cells):
                        out.append("\t".join(cells).rstrip())
            return "\n".join(out)
    except Exception as e:
        fail("не удалось прочитать .xlsx ({}): {}".format(path, e))


def read_pptx(path):
    """Презентация: по слайду «Слайд N:» и тексту его фигур; текст заметок тоже."""
    import xml.etree.ElementTree as ET
    import zipfile
    a = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            slides = sorted((n for n in names if re.match(r"ppt/slides/slide\d+\.xml$", n)),
                            key=lambda n: int(re.search(r"(\d+)\.xml$", n).group(1)))
            out = []
            for n in slides:
                num = re.search(r"(\d+)\.xml$", n).group(1)
                root = ET.fromstring(z.read(n))
                paras = ["".join(t.text or "" for t in p.iter(a + "t")) for p in root.iter(a + "p")]
                out.append("Слайд {}:".format(num))
                out += [p for p in paras if p.strip()]
                note = "ppt/notesSlides/notesSlide{}.xml".format(num)
                if note in names:
                    nt = [("".join(t.text or "" for t in p.iter(a + "t"))) for p in ET.fromstring(z.read(note)).iter(a + "p")]
                    nt = [x for x in nt if x.strip() and not x.strip().isdigit()]
                    if nt:
                        out.append("Заметки:")
                        out += nt
            return "\n".join(out)
    except Exception as e:
        fail("не удалось прочитать .pptx ({}): {}".format(path, e))


def read_local(path):
    low = path.lower()
    if low.endswith(".docx"):
        return read_docx(path)
    if low.endswith(".pdf"):
        return read_pdf(path)
    if low.endswith(".xlsx") or low.endswith(".xlsm"):
        return read_xlsx(path)
    if low.endswith(".pptx"):
        return read_pptx(path)
    with open(path, "rb") as f:
        head = f.read(4096)
    if b"\x00" in head or head.startswith(b"PK\x03\x04"):
        fail("бинарный файл, не текст: {} — .docx, .pdf, .xlsx и .pptx читаются сами, остальное конвертируй в текст".format(path))
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (polygon add_source)"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data, ctype = r.read(), r.headers.get("Content-Type", "")
    except Exception as e:
        fail("не скачалось ({}): регистрируй с --read not-read или дай текст через stdin".format(e))
    if "pdf" in ctype or url.lower().endswith(".pdf"):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(data)
        try:
            return read_pdf(tmp.name)
        finally:
            os.unlink(tmp.name)
    html = data.decode("utf-8", "replace")
    try:
        import trafilatura
        text = trafilatura.extract(html, include_tables=True, include_comments=True)
        if text:
            return text
    except ImportError:
        pass
    html = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    import html as h
    return re.sub(r"[ \t]+", " ", h.unescape(text))


def read_rows(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def next_id(rows):
    nums = [int(r["id"][2:]) for r in rows if r.get("id", "").startswith("F-") and r["id"][2:].isdigit()]
    return "F-{:03d}".format(max(nums) + 1 if nums else 1)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--task", required=True, help="папка задачи, например tasks/2026-10-06-smb")
    p.add_argument("--kind", required=True, choices=sorted(KINDS))
    p.add_argument("--location", required=True, help="адрес страницы или путь к файлу контекста")
    p.add_argument("--level", default="", help="уровень по web-protocol.md (1–4); для веба обязателен")
    p.add_argument("--ctx-type", default="", help="для контекста: claim (утверждение команды), voice (прямая речь клиента), "
                   "data (выгрузка, цифры), result (результат живой проверки), system (материал прошлой задачи), other")
    p.add_argument("--author", default="", help="кто автор или кто заказал")
    p.add_argument("--pub-date", default="unknown", help="дата публикации или создания")
    p.add_argument("--data-date", default="unknown", help="дата, к которой относятся данные (если отличается)")
    p.add_argument("--read", default="full", choices=sorted(READ), help="насколько полно прочитан")
    p.add_argument("--method", default="raw", choices=sorted(METHODS), help="raw — сырой текст; summary — только пересказ инструмента")
    p.add_argument("--root", default="self", help="первоисточник: self, или id уже зарегистрированного источника, или адрес оригинала")
    p.add_argument("--status", default="unknown", choices=sorted(STATUSES), help="для документов: final, draft, outdated, unknown")
    p.add_argument("--note", default="", help="коротко: что не так с источником (заказчик, нет методологии, инструкция для ИИ…)")
    p.add_argument("--fetch", action="store_true", help="для веба: скачать страницу самим скриптом")
    p.add_argument("--file", default="", help="взять текст из файла; по умолчанию для веба — stdin, для контекста — сам --location")
    a = p.parse_args()

    if a.kind == "web":
        if a.level not in LEVELS:
            fail("для веба нужен --level 1, 2, 3 или 4")
        if a.ctx_type:
            fail("--ctx-type только для контекста")
    else:
        if a.ctx_type not in CTX_TYPES:
            fail("для контекста нужен --ctx-type: " + ", ".join(sorted(CTX_TYPES)))
        if a.level:
            fail("--level только для веба")
    check_date("--pub-date", a.pub_date)
    check_date("--data-date", a.data_date)

    src_file = a.file or ("" if a.kind == "web" else a.location)
    fetched = "agent"
    if a.fetch:
        if a.kind != "web":
            fail("--fetch только для веба")
        text, fetched = fetch(a.location), "script"
    elif src_file:
        if not os.path.exists(src_file):
            fail("файл не найден: " + src_file)
        text = read_local(src_file)
    else:
        text = sys.stdin.read()

    if not text.strip():
        # пустой текст = не прочитано, а не «на странице ничего нет» (web-protocol.md, 2а)
        if a.read != "not-read":
            fail("текст пустой: регистрируй с --read not-read, а не как прочитанный")
    elif a.kind == "web" and a.read == "full" and len(text) < 1500:
        sys.stderr.write("add_source: внимание — текста меньше 1500 знаков. Проверь, что это не заглушка, "
                         "не аннотация вместо статьи и не «включите JavaScript» (web-protocol.md, 2а). "
                         "Если так — перерегистрируй с --read partial или not-read.\n")
    if a.method == "summary" and a.read == "full":
        fail("пересказ инструмента чтения не бывает полным чтением: --read partial или snippet")

    if not os.path.isdir(a.task):
        fail("папки задачи нет: " + a.task)
    reg = os.path.join(a.task, "sources.csv")
    raw_dir = os.path.join(a.task, "sources", "raw")
    os.makedirs(raw_dir, exist_ok=True)
    rows = read_rows(reg)

    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    for r in rows:
        if r["location"] == a.location and r["sha256"] == sha:
            print(r["id"])
            return

    ids = {r["id"] for r in rows}
    if a.root not in ("self", "") and a.root.startswith("F-") and a.root not in ids:
        fail("--root {} не найден в реестре".format(a.root))

    sid = next_id(rows)
    with open(os.path.join(raw_dir, sid + ".txt"), "w", encoding="utf-8") as f:
        f.write(text)

    row = {
        "id": sid, "kind": a.kind, "location": a.location, "level": a.level, "ctx_type": a.ctx_type,
        "author": a.author, "pub_date": a.pub_date, "data_date": a.data_date,
        "opened": datetime.date.today().isoformat(), "read": a.read, "method": a.method,
        "root": a.root or "self", "status": a.status, "fetched": fetched if a.kind == "web" else "file", "sha256": sha, "chars": str(len(text)), "note": a.note, "ts": str(int(time.time())),
    }
    new = not os.path.exists(reg)
    with open(reg, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)
    print(sid)


if __name__ == "__main__":
    main()
