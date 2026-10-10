#!/usr/bin/env python3
"""Самопроверка скриптов: запускай после любой правки в scripts/.

  python3 scripts/selftest.py

Собирает временную задачу и проверяет, что проверки ловят то, что должны, и не ругаются на верное:
русский текст, ё/е, тире, пропуск «…», подмену источника, непрочитанный источник, цитату без id,
пустой артефакт, файл вне периметра, хук записи, стоп-хук, проверку смысла (цитаты [A], ответы автора), реестр чисел (пересчёт, период, противоречия). Сеть не нужна.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
fails = []


def run(args, stdin=None, env=None, cwd=None):
    return subprocess.run([PY] + args, input=stdin, capture_output=True, text=True, env=env, cwd=cwd)


def expect(name, cond, detail=""):
    print(("ок    " if cond else "ПРОВАЛ") + "  " + name)
    if not cond:
        fails.append(name + (": " + detail if detail else ""))


def closed_web_tests(root):
    cw = os.path.join(root, "tasks", "cw")
    os.makedirs(cw)
    open(os.path.join(cw, "closed-web.txt"), "w", encoding="utf-8").write("# партнёр\nПартнёрКо\n")
    open(os.path.join(cw, "log.md"), "w", encoding="utf-8").write("ШАГ 1\nЗапросы:   WebSearch «закон о рекламе требования к акциям»\nПроверки: ок\nЗамечание: акция ПартнёрКо одобрена\n")
    open(os.path.join(cw, "src-a.md"), "w", encoding="utf-8").write("Акция ПартнёрКо — чисто для артефакта.\n")
    r = run([os.path.join(HERE, "check_private.py"), cw])
    expect("закрытое слово не в запросах: проверка чистая", r.returncode == 0, r.stdout)
    open(os.path.join(cw, "log.md"), "w", encoding="utf-8").write("ШАГ 1\nЗапросы:   WebSearch «ПартнёрКо промокод условия»\nПроверки: ок\n")
    r = run([os.path.join(HERE, "check_private.py"), cw])
    expect("закрытое слово в запросе в веб пойман", r.returncode == 1 and "closed-web.txt" in r.stdout, r.stdout)


def readable_tests(root):
    cr = os.path.join(HERE, "check_readable.py")
    d = os.path.join(root, "tasks", "rd")
    os.makedirs(d)
    q = "Хочу один понятный отчёт, а не десять вкладок"
    files = {
        "07a-analyst.md": "# Задача аналитику\n\n## 1. Воронка по шагам — срочно\nЧто нужно: доля клиентов на каждом шаге.\nЗачем: если на активации теряем больше половины — чиним её, иначе смотрим письма.\n",
        "07b-editor.md": "# Бриф\n\n## Онбординг\nСлова клиентов: «%s» (опрос ИП, 2025)\n" % q,
        "07c-decisions.md": "# Решения\n\n1. Кому адресован запуск?\n   От чего зависит: срочно.\n",
        "07d-trace.md": "Г-1, вердикт: сузить. «%s» [F-012]\n" % q,
    }
    for n, c in files.items():
        open(os.path.join(d, n), "w", encoding="utf-8").write(c)
    r = run([cr, d])
    expect("читаемость: чистые документы проходят", r.returncode == 0, r.stdout)
    base = files["07a-analyst.md"]
    open(os.path.join(d, "07a-analyst.md"), "w", encoding="utf-8").write(base + "Гипотеза Г-11 сужена.\n")
    r = run([cr, d])
    expect("читаемость: номер и слово системы пойманы", r.returncode == 1 and "номер гипотезы" in r.stdout and "гипотез" in r.stdout, r.stdout)
    open(os.path.join(d, "07a-analyst.md"), "w", encoding="utf-8").write(base + "Источник [F-007].\n")
    r = run([cr, d])
    expect("читаемость: id источника пойман", r.returncode == 1 and "id источника" in r.stdout, r.stdout)
    open(os.path.join(d, "07a-analyst.md"), "w", encoding="utf-8").write(base)
    open(os.path.join(d, "07b-editor.md"), "w", encoding="utf-8").write("## Онбординг\nСлова клиентов: «Совсем другая цитата, которой нет в служебном файле» (опрос)\n")
    r = run([cr, d])
    expect("читаемость: цитата вне служебного файла поймана", r.returncode == 1 and "цитаты нет" in r.stdout, r.stdout)
    open(os.path.join(d, "07b-editor.md"), "w", encoding="utf-8").write("## Онбординг\n" + "слово " * 1700)
    r = run([cr, d])
    expect("читаемость: превышение лимита слов поймано", r.returncode == 1 and "лимите" in r.stdout, r.stdout)
    d2 = os.path.join(root, "tasks", "rd2")
    os.makedirs(d2)
    expect("читаемость: нет документов — проверять нечего", run([cr, d2]).returncode == 0)
    open(os.path.join(d2, "07-briefs.md"), "w", encoding="utf-8").write("# Брифы\n")
    r = run([cr, d2])
    expect("читаемость: брифы под чужим именем пойманы", r.returncode == 1 and "чужим именем" in r.stdout, r.stdout)
    d4 = os.path.join(root, "tasks", "rd4")
    os.makedirs(d4)
    pos = "ЧТО ЗАПУСКАТЬ\nКому: владельцы без сотрудников\nЧто говорим: один отчёт вместо десяти вкладок\n"
    open(os.path.join(d4, "02e-position.md"), "w", encoding="utf-8").write(pos)
    r = run([cr, d4])
    expect("читаемость: позиция простым языком проходит без брифов", r.returncode == 0, r.stdout)
    open(os.path.join(d4, "02e-position.md"), "w", encoding="utf-8").write(pos + "Гипотеза Г-3 сужена [F-002].\n")
    r = run([cr, d4])
    expect("читаемость: язык системы в позиции пойман", r.returncode == 1 and "02e-position.md" in r.stdout and "номер гипотезы" in r.stdout, r.stdout)
    d5 = os.path.join(root, "tasks", "rd5")
    os.makedirs(d5)
    val = "ВЕРДИКТ ПО ИДЕЕ\nГипотеза человека держится частично: «отчёт за минуту» [F-006].\n"
    open(os.path.join(d5, "06-validation.md"), "w", encoding="utf-8").write(val)
    r = run([cr, d5])
    expect("читаемость: документ валидации с [F-id] и словом «гипотеза» проходит", r.returncode == 0, r.stdout)
    open(os.path.join(d5, "06-validation.md"), "w", encoding="utf-8").write(val + "M1 · пройдена; слот пуст; см. D-1 и Г-2.\n")
    r = run([cr, d5])
    expect("читаемость: модуль курса, слот, D-1 и Г-2 в документе валидации пойманы", r.returncode == 1 and "номер гипотезы" in r.stdout and "слово системы" in r.stdout, r.stdout)
    d3 = os.path.join(root, "tasks", "rd3")
    os.makedirs(d3)
    open(os.path.join(d3, "00-tz.md"), "w", encoding="utf-8").write("**ТИП ВЫХОДА:** ТЗ на доработку\n")
    r = run([cr, d3])
    expect("читаемость: тип «ТЗ на доработку» без брифов — ошибка", r.returncode == 1 and "файла нет" in r.stdout, r.stdout)


def step_tests(root):
    cs = os.path.join(HERE, "check_step.py")
    d = os.path.join(root, "tasks", "stp")
    os.makedirs(d)
    since = str(int(time.time()) - 5)
    open(os.path.join(d, "01-review.md"), "w", encoding="utf-8").write("# Разбор\n\n## Слабые места\n" + "Разрыв логики между первым запуском и регулярным использованием продукта. " * 10 + "\n")
    r = run([cs, d, "01-review.md", "--since", since])
    expect("шаг: чистый артефакт — одна строка без ошибок", r.returncode == 0 and r.stdout.startswith("Проверки: check_artifact — ок"), r.stdout)
    expect("шаг: в строке есть счётчики цитат и корней", "корней" in r.stdout and "без id" in r.stdout, r.stdout)
    open(os.path.join(d, "01-review.md"), "a", encoding="utf-8").write("Почта клиента: test.person@example.com\n")
    r = run([cs, d, "01-review.md", "--since", since])
    expect("шаг: ошибка одной проверки видна и в строке, и в коде", r.returncode == 1 and "check_private — ОШИБКИ" in r.stdout, r.stdout)


def log_sources_tests(root):
    cl = os.path.join(HERE, "check_log_sources.py")
    d = os.path.join(root, "tasks", "ls")
    os.makedirs(d)
    good = ("# Лог\n\nШАГ 1 — b2b-consultant\nДыра: постановка\n\n"
            "ШАГ 2 — market-analyze\nДыра: GAP 1\nВопрос:   что клиенты называют причиной; веб; ≥5 причин со словами клиента; 12 запросов\n"
            "Зачем:    без этого генератор угадает причину\nУже известно: F-002 — утверждение команды, проверяется\nРезультат: совпал\n\n"
            "ШАГ 3 — hypothesis-generator\nДыра: гипотезы\n")
    open(os.path.join(d, "log.md"), "w", encoding="utf-8").write(good)
    r = run([cl, d])
    expect("лог: шаг-источник с вопросом, зачем и известным проходит", r.returncode == 0, r.stdout)
    open(os.path.join(d, "log.md"), "w", encoding="utf-8").write(good.replace("Зачем:    без этого генератор угадает причину\n", "Зачем:    —\n"))
    r = run([cl, d])
    expect("лог: пустое «Зачем» у источника поймано", r.returncode == 1 and "Зачем" in r.stdout, r.stdout)
    open(os.path.join(d, "log.md"), "w", encoding="utf-8").write(good.replace("Уже известно: F-002 — утверждение команды, проверяется\n", ""))
    r = run([cl, d])
    expect("лог: нет «Уже известно» у источника — поймано", r.returncode == 1 and "Уже известно" in r.stdout, r.stdout)


def publish_tests(root):
    cp = os.path.join(HERE, "check_publish.py")
    repo = os.path.join(root, "pubrepo")
    os.makedirs(os.path.join(repo, "tasks", "t1"))
    g = lambda *a: subprocess.run(["git", "-C", repo] + list(a), capture_output=True, text=True)
    g("init", "-q")
    g("config", "user.email", "t@example.com")
    g("config", "user.name", "t")
    open(os.path.join(repo, ".gitignore"), "w", encoding="utf-8").write("tasks/*\n")
    open(os.path.join(repo, "tasks", "t1", "private.txt"), "w", encoding="utf-8").write("# имена\nМарина\n")
    open(os.path.join(repo, "tasks", "t1", "closed-web.txt"), "w", encoding="utf-8").write("ПартнёрКо\n")
    open(os.path.join(repo, "a.md"), "w", encoding="utf-8").write("Собрать максимум источников. Пример: Ольга.\n")
    g("add", "-A")
    g("commit", "-q", "-m", "чистый коммит")
    r = subprocess.run([PY, cp, "--all"], capture_output=True, text=True, cwd=repo)
    expect("публикация: чистый репозиторий проходит", r.returncode == 0, r.stdout + r.stderr)
    open(os.path.join(repo, "a.md"), "a", encoding="utf-8").write("Сказала Марине про акцию партнёрко.\n")
    g("commit", "-q", "-am", "добавил пример")
    r = subprocess.run([PY, cp, "--all"], capture_output=True, text=True, cwd=repo)
    expect("публикация: имя в падеже и закрытое слово пойманы", r.returncode == 1 and "Марин" in r.stdout and "ПартнёрКо" in r.stdout, r.stdout)
    g("commit", "-q", "--allow-empty", "-m", "по задаче Марины")
    head = g("rev-parse", "HEAD").stdout.strip()
    r = subprocess.run([PY, cp, "--pre-push"], input="refs/heads/main %s refs/heads/main %s\n" % (head, "0" * 40),
                       capture_output=True, text=True, cwd=repo)
    expect("публикация: хук перед отправкой ловит имя в сообщении коммита", r.returncode == 1 and "сообщение коммита" in r.stdout, r.stdout)


def readers_tests(root):
    import zipfile
    add = os.path.join(HERE, "add_source.py")
    d = os.path.join(root, "tasks", "rdr")
    os.makedirs(d)
    xl = os.path.join(root, "context", "table.xlsx")
    with zipfile.ZipFile(xl, "w") as z:
        z.writestr("xl/sharedStrings.xml", '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>Воронка</t></si><si><t>Шаг</t></si></sst>')
        z.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row><c t="s"><v>1</v></c><c t="s"><v>0</v></c></row><row><c><v>42</v></c></row></sheetData></worksheet>')
    r = run([add, "--task", d, "--kind", "context", "--location", xl, "--ctx-type", "claim"])
    expect("чтение xlsx", r.returncode == 0, r.stderr)
    raw = open(os.path.join(d, "sources", "raw", r.stdout.strip() + ".txt"), encoding="utf-8").read()
    expect("xlsx: ячейки и общие строки на месте", "Шаг\tВоронка" in raw and "42" in raw, raw)
    px = os.path.join(root, "context", "deck.pptx")
    with zipfile.ZipFile(px, "w") as z:
        z.writestr("ppt/slides/slide1.xml", '<p:sld xmlns:p="p" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:p><a:r><a:t>Онбординг клиентов</a:t></a:r></a:p></p:sld>')
        z.writestr("ppt/slides/slide2.xml", '<p:sld xmlns:p="p" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:p><a:r><a:t>Результаты опроса</a:t></a:r></a:p></p:sld>')
    r = run([add, "--task", d, "--kind", "context", "--location", px, "--ctx-type", "claim"])
    expect("чтение pptx", r.returncode == 0, r.stderr)
    raw = open(os.path.join(d, "sources", "raw", r.stdout.strip() + ".txt"), encoding="utf-8").read()
    expect("pptx: слайды по порядку", raw.index("Слайд 1:") < raw.index("Онбординг клиентов") < raw.index("Слайд 2:") < raw.index("Результаты опроса"), raw)
    pdf = os.path.join(root, "context", "broken.pdf")
    open(pdf, "wb").write(b"%PDF-1.4\n%%EOF\n")
    r = run([add, "--task", d, "--kind", "context", "--location", pdf, "--ctx-type", "claim"])
    expect("битый PDF даёт понятную ошибку, а не пустой источник", r.returncode != 0 and ("check_env" in r.stderr + r.stdout or "текстового слоя" in r.stderr + r.stdout), r.stderr + r.stdout)
    e = run([os.path.join(HERE, "check_env.py")])
    expect("check_env печатает отчёт", e.returncode == 0 and "Чтение PDF с текстом" in e.stdout, e.stdout + e.stderr)


def main():
    root = tempfile.mkdtemp(prefix="polygon-selftest-")
    try:
        task = os.path.join(root, "tasks", "demo")
        os.makedirs(task)
        os.makedirs(os.path.join(root, "context"))
        add = os.path.join(HERE, "add_source.py")

        r1 = run([add, "--task", task, "--kind", "web", "--location", "https://a.ru/x", "--level", "1", "--pub-date", "2025-11-02"],
                 "Рынок вырос на 12% за 2025 год.\nВладельцы: «Прибыль по бумагам есть, а денег на счетах — нет».\n")
        expect("регистрация веба", r1.stdout.strip() == "F-001", r1.stderr)
        r2 = run([add, "--task", task, "--kind", "web", "--location", "https://b.ru/y", "--level", "3", "--root", "F-001"],
                 "Перепечатка: рынок вырос на 12% за 2025 год.\n")
        expect("перепечатка с корнем", r2.stdout.strip() == "F-002", r2.stderr)
        tr = os.path.join(root, "context", "ivanov.md")
        open(tr, "w", encoding="utf-8").write("Интервьюер: Как сверяете?\nИванов: Ёлки, вручную в Excel, каждую пятницу.\n")
        r3 = run([add, "--task", task, "--kind", "interview", "--location", tr, "--ctx-type", "voice", "--pub-date", "2026-08"])
        expect("регистрация транскрипта", r3.stdout.strip() == "F-003", r3.stderr)
        r4 = run([add, "--task", task, "--kind", "web", "--location", "https://c.ru", "--level", "3", "--read", "not-read"], "")
        expect("непрочитанный источник", r4.stdout.strip() == "F-004", r4.stderr)
        cprv = os.path.join(HERE, "check_private.py")
        open(os.path.join(task, "private.txt"), "w", encoding="utf-8").write("# имена\nБорис\nМарин\n")
        pa = os.path.join(task, "src-priv.md")
        open(pa, "w", encoding="utf-8").write(
            "Респондент Бориса: +7 (999) 123-45-67, ИНН 7701234567, почта ivan@example.ru.\n"
            "Сказала Марина. Чисто: Интервью 3, сегмент ВВ.\n")
        pv = run([cprv, task])
        expect("персональные данные пойманы", pv.returncode == 1 and "телефон" in pv.stdout and "e-mail" in pv.stdout
               and "ИНН" in pv.stdout and "термин из private.txt: Борис" in pv.stdout and "термин из private.txt: Марин" in pv.stdout, pv.stdout)
        expect("найденное в отчёт не копируется",
               "123-45-67" not in pv.stdout and "7701234567" not in pv.stdout and "ivan@" not in pv.stdout, pv.stdout)
        os.remove(pa)
        pv2 = run([cprv, task])
        expect("без персональных данных проверка чистая", pv2.returncode == 0, pv2.stdout)
        os.remove(os.path.join(task, "private.txt"))
        brief = os.path.join(root, "context", "brief.md")
        open(brief, "w", encoding="utf-8").write("Мы знаем, что клиенты уходят из-за цены.\n")
        r6 = run([add, "--task", task, "--kind", "context", "--location", brief, "--ctx-type", "claim"])
        expect("регистрация утверждения команды", r6.stdout.strip() == "F-005", r6.stderr)
        import zipfile
        dx = os.path.join(root, "context", "interview.docx")
        with zipfile.ZipFile(dx, "w") as z:
            z.writestr("word/document.xml",
                       '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
                       '<w:p><w:r><w:t>Спикер 2: [00:01]</w:t></w:r></w:p>'
                       '<w:p><w:r><w:t>Мы сверяем вручную в Excel</w:t></w:r><w:r><w:tab/><w:t>каждую пятницу.</w:t></w:r></w:p>'
                       '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>ячейка таблицы</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
                       '</w:body></w:document>')
        rd = run([add, "--task", task, "--kind", "interview", "--location", dx, "--ctx-type", "voice"])
        expect("docx читается как текст", rd.returncode == 0, rd.stderr)
        rawd = open(os.path.join(task, "sources", "raw", rd.stdout.strip() + ".txt"), encoding="utf-8").read()
        expect("в тексте docx нет бинарного мусора, есть абзацы и таблица",
               not rawd.startswith("PK") and "вручную в Excel" in rawd and "ячейка таблицы" in rawd, rawd[:120])
        junk = os.path.join(root, "context", "junk.bin")
        open(junk, "wb").write(b"\x00\x01" * 400)
        expect("бинарный не-docx отклонён",
               run([add, "--task", task, "--kind", "context", "--location", junk, "--ctx-type", "other"]).returncode == 2)
        r5 = run([add, "--task", task, "--kind", "web", "--location", "https://a.ru/x", "--level", "1"],
                 "Рынок вырос на 12% за 2025 год.\nВладельцы: «Прибыль по бумагам есть, а денег на счетах — нет».\n")
        expect("повтор не плодит id", r5.stdout.strip() == "F-001", r5.stdout + r5.stderr)
        expect("веб без уровня отклонён", run([add, "--task", task, "--kind", "web", "--location", "https://d.ru"], "x").returncode == 2)
        expect("пустой текст как прочитанный отклонён",
               run([add, "--task", task, "--kind", "web", "--location", "https://e.ru", "--level", "2"], "").returncode == 2)
        expect("пересказ как полное чтение отклонён",
               run([add, "--task", task, "--kind", "web", "--location", "https://f.ru", "--level", "2", "--method", "summary"], "x").returncode == 2)

        good = os.path.join(task, "src-good.md")
        open(good, "w", encoding="utf-8").write(
            "Боль: «прибыль по бумагам есть, а денег на счетах - нет» [F-001]. "
            "Рост: «рынок вырос на 12% … 2025 год» [F-002]. Вопрос: «Как сверяете?» → «елки, вручную в excel» [F-003].\n"
            "| Куда ушёл | Причина | Источник |\n| Excel | «вручную в Excel, каждую пятницу» | [F-003] |\n"
            "Подробнее: https://a.ru/x\n")
        cq = os.path.join(HERE, "check_quotes.py")
        g = run([cq, task, "src-good.md"])
        expect("верные цитаты проходят", g.returncode == 0, g.stdout)
        expect("корни считаются по реестру", "независимых корней: 2" in g.stdout, g.stdout)
        expect("цитата в таблице связана с id", "цитат проверено: 4" in g.stdout and "без id" not in g.stdout, g.stdout)
        expect("ссылка из реестра не вызывает замечания", "вне реестра" not in g.stdout, g.stdout)

        bad = os.path.join(task, "src-bad.md")
        open(bad, "w", encoding="utf-8").write(
            "Подмена: «вручную в Excel» [F-001]. Непрочитанное: «что угодно» [F-004]. Фантом: «текст» [F-099].\n"
            "Без id: «это длинная цитата без всякого указания на источник вообще».\n"
            "Команда: «клиенты уходят из-за цены» [F-005]. Ссылка: https://fake.example/report\n")
        b = run([cq, task, "src-bad.md"])
        expect("ошибки дают код 1", b.returncode == 1, b.stdout)
        expect("подмена источника поймана", "[F-001] не найдено" in b.stdout, b.stdout)
        expect("непрочитанное поймано", "[F-004] источник не прочитан" in b.stdout, b.stdout)
        expect("ссылка вне реестра поймана", "[F-099] нет в реестре" in b.stdout, b.stdout)
        expect("цитата без id замечена", "цитат без id источника — 1" in b.stdout, b.stdout)
        expect("опора на утверждение команды замечена", "утверждения команды (F-005)" in b.stdout, b.stdout)
        expect("ссылка вне реестра замечена", "ссылок вне реестра — 1" in b.stdout, b.stdout)

        rv = os.path.join(task, "review-src-good.md")
        open(rv, "w", encoding="utf-8").write(
            "Артефакт: src-good.md\n\nС-01 [блок] Сила — шире по охвату\nВ тексте: «рынок вырос на 12%» [A]\n"
            "Источник: «Рынок вырос на 12% за 2025 год» [F-001]\n\nС-02 [замечание] Логика — повтор\nВ тексте: «этого в тексте нет» [A]\n")
        r_ok = run([cq, task, "review-src-good.md"])
        expect("цитаты [A] без флага не проверяются", r_ok.returncode == 0, r_ok.stdout)
        r_a = run([cq, task, "review-src-good.md", "--check-a"])
        expect("выдуманная цитата артефакта поймана", r_a.returncode == 1 and "[A] нет в артефакте" in r_a.stdout
               and r_a.stdout.count("[A] нет") == 1, r_a.stdout)

        lu = run([os.path.join(HERE, "list_unused.py"), task, "src-good.md"])
        expect("неиспользованные источники перечислены", "[F-005]" in lu.stdout and "[F-001]" not in lu.stdout
               and "[F-004]" not in lu.stdout, lu.stdout)

        ca = os.path.join(HERE, "check_artifact.py")
        fixed = os.path.join(task, "src-fixed.md")
        body = "Вывод. " * 80
        open(fixed, "w", encoding="utf-8").write(body + "\nПО ПРОВЕРКЕ СМЫСЛА\nС-01 — оспорено:\n")
        f1 = run([ca, task, "src-fixed.md", "--review", "review-src-good.md"])
        expect("оспорено без причины поймано", f1.returncode == 1 and "без причины" in f1.stdout, f1.stdout)
        open(fixed, "w", encoding="utf-8").write(body + "\nПО ПРОВЕРКЕ СМЫСЛА\n")
        f2 = run([ca, task, "src-fixed.md", "--review", "review-src-good.md"])
        expect("нет ответа на блокирующее поймано", f2.returncode == 1 and "С-01" in f2.stdout, f2.stdout)
        open(fixed, "w", encoding="utf-8").write(body + "\nПО ПРОВЕРКЕ СМЫСЛА\nС-01 — исправлено: ослаблено до «в 2025 году»\n")
        f3 = run([ca, task, "src-fixed.md", "--review", "review-src-good.md"])
        expect("ответ на замечание принят", f3.returncode == 0, f3.stdout)
        os.remove(fixed)
        t0 = time.time() - 1
        open(os.path.join(task, "02-h.md"), "w", encoding="utf-8").write("Сигнал оркестратору: готово\n")
        open(os.path.join(task, "stray.txt"), "w", encoding="utf-8").write("чужой файл\n")
        a = run([ca, task, "02-h.md", "--since", str(t0)])
        expect("резюме вместо артефакта поймано", a.returncode == 1 and "короче" in a.stdout, a.stdout)
        expect("файл вне периметра пойман", "stray.txt" in a.stdout, a.stdout)
        os.remove(os.path.join(task, "stray.txt"))
        open(os.path.join(task, "02-h.md"), "w", encoding="utf-8").write("ГИПОТЕЗА 1\n" + "Текст гипотезы. " * 40)
        a2 = run([ca, task, "02-h.md", "--since", str(time.time() + 1)])
        expect("полный артефакт проходит", a2.returncode == 0, a2.stdout)

        an = os.path.join(HERE, "add_number.py")
        cn = os.path.join(HERE, "check_numbers.py")
        n1 = run([an, "--task", task, "--kind", "fact", "--key", "growth", "--what", "рост рынка", "--value", "12", "--unit", "%",
                  "--base", "к 2024", "--period", "2025", "--source", "F-001", "--fragment", "Рынок вырос на 12% за 2025 год"])
        expect("число-факт зарегистрировано", n1.stdout.strip() == "N-001", n1.stderr)
        n2 = run([an, "--task", task, "--kind", "assumption", "--key", "share", "--what", "доля", "--value", "0.5", "--unit", "доля",
                  "--base", "от сегмента", "--note", "нет данных"])
        n3 = run([an, "--task", task, "--kind", "derived", "--key", "half", "--what", "половина роста", "--formula", "N-001 * N-002", "--value", "6", "--unit", "%"])
        expect("производное по формуле принято", n3.stdout.strip() == "N-003", n3.stderr)
        expect("производное с неверным значением отклонено",
               run([an, "--task", task, "--kind", "derived", "--key", "bad", "--what", "x", "--formula", "N-001 * N-002", "--value", "7", "--unit", "%"]).returncode == 2)
        expect("фрагмент вне источника отклонён",
               run([an, "--task", task, "--kind", "fact", "--key", "k", "--what", "x", "--value", "3", "--unit", "шт", "--source", "F-001", "--fragment", "числа три нет"]).returncode == 2)
        expect("допущение без причины отклонено",
               run([an, "--task", task, "--kind", "assumption", "--key", "k2", "--what", "x", "--value", "3", "--unit", "шт"]).returncode == 2)
        expect("число из непрочитанного источника отклонено",
               run([an, "--task", task, "--kind", "fact", "--key", "k3", "--what", "x", "--value", "1", "--unit", "шт", "--source", "F-004", "--fragment", "x"]).returncode == 2)
        run([an, "--task", task, "--kind", "fact", "--key", "growth", "--what", "рост рынка", "--value", "15", "--unit", "%",
             "--base", "к 2023", "--period", "2024", "--source", "F-002", "--fragment", "рынок вырос на 12%", "--as-written", "12%"])
        open(os.path.join(task, "src-num.md"), "w", encoding="utf-8").write("Рост 12% [N-001]. Половина 6% [N-003]. Неверно: 99% [N-001]. Фантом [N-077].\n")
        c1 = run([cn, task])
        expect("число рядом со ссылкой проверяется", "рядом с [N-001] нет числа" in c1.stdout and c1.stdout.count("рядом с") == 1, c1.stdout)
        expect("ссылка вне реестра чисел поймана", "[N-077] нет в реестре" in c1.stdout, c1.stdout)
        expect("разные условия — не противоречие", "growth" in c1.stdout and "разные условия" in c1.stdout and "настоящее противоречие" not in c1.stdout, c1.stdout)
        run([an, "--task", task, "--kind", "fact", "--key", "growth", "--what", "рост рынка", "--value", "9", "--unit", "%",
             "--base", "к 2024", "--period", "2025", "--source", "F-001", "--fragment", "Рынок вырос на 12% за 2025 год", "--as-written", "12%"])
        c2 = run([cn, task])
        expect("пересечение в value не мешает: настоящее противоречие поймано", "настоящее противоречие" in c2.stdout, c2.stdout)
        os.remove(os.path.join(task, "src-num.md"))

        tm = run([os.path.join(HERE, "trust_map.py"), task])
        expect("счёт опор считается", "независимых корней:" in tm.stdout and "Чисел:" in tm.stdout and "Проверки смысла:" in tm.stdout, tm.stdout)
        expect("счёт опор: допущения перечислены", "допущение [N-002]" in tm.stdout, tm.stdout)
        expect("счёт опор: утверждения команды видны", "утверждения команды" in tm.stdout, tm.stdout)
        rep_path = os.path.join(task, "06-research.md")
        trust = open(os.path.join(task, "checks", "trust.md"), encoding="utf-8").read()
        open(rep_path, "w", encoding="utf-8").write("ОТВЕТ\n" + "Текст отчёта. " * 40 + "\n\n" + trust)
        t1 = run([ca, task, "06-research.md", "--contains", "checks/trust.md"])
        expect("блок счёта перенесён дословно — принято", t1.returncode == 0, t1.stdout)
        open(rep_path, "w", encoding="utf-8").write("ОТВЕТ\n" + "Текст отчёта. " * 40 + "\n\nСЧЁТ ОПОР: примерно 12 источников, всё хорошо\n")
        t2 = run([ca, task, "06-research.md", "--contains", "checks/trust.md"])
        expect("пересказанный блок счёта отклонён", t2.returncode == 1 and "дословного блока" in t2.stdout, t2.stdout)
        os.remove(rep_path)

        # --- проверка периметра: пачка по маске и записи оркестратора в log.md ---
        ca2 = os.path.join(HERE, "check_artifact.py")
        time.sleep(1.1)
        t_batch = time.time()
        for n in (1, 2):
            open(os.path.join(task, "src-b-%d.md" % n), "w", encoding="utf-8").write("Разбор. " * 80)
        open(os.path.join(task, "log.md"), "a", encoding="utf-8").write("запись оркестратора\n")
        pb = run([ca2, task, "src-b-*.md", "--since", str(t_batch)])
        expect("пачка по маске: соседи и log.md чужими не считаются", pb.returncode == 0 and "2 файлов" in pb.stdout, pb.stdout)
        open(os.path.join(task, "alien.txt"), "w", encoding="utf-8").write("чужой файл")
        pb2 = run([ca2, task, "src-b-*.md", "--since", str(t_batch)])
        expect("чужой файл по-прежнему ловится", pb2.returncode == 1 and "alien.txt" in pb2.stdout, pb2.stdout)
        pb3 = run([ca2, task, "src-b-*.md", "--since", str(t_batch), "--allow", "alien.*"])
        expect("--allow принимает маски", pb3.returncode == 0, pb3.stdout)
        os.remove(os.path.join(task, "alien.txt"))

        # --- ответы автора: гибкий формат и общий счёт замечаний ---
        open(os.path.join(task, "review-src-fmt.md"), "w", encoding="utf-8").write(
            "Артефакт: src-fmt.md\n\nС-01 [блок] Сила — шире\nВ тексте: «х» [A]\n\nС-02 [замечание] Логика — повтор\n\n"
            "С-03 [замечание] Опора — не про то\n\nИтог: блокирующих 1, замечаний 2\n"
            "Не проверено: цифры в разделе 2 не пересчитаны по сырому тексту.\n")
        body_fmt = "Вывод. " * 80
        fmt = os.path.join(task, "src-fmt.md")
        open(fmt, "w", encoding="utf-8").write(
            body_fmt + "\nПО ПРОВЕРКЕ СМЫСЛА\n- С-01 [блок] — исправлено: ослабил формулировку\n* **С-02** — снято\n"
            "С-03 – оспорено: фрагмент говорит об этом прямо\n")
        fr = run([ca2, task, "src-fmt.md", "--review", "review-src-fmt.md"])
        expect("ответы с маркерами списка и [блок] принимаются без правки вручную", fr.returncode == 0, fr.stdout)
        open(fmt, "w", encoding="utf-8").write(body_fmt + "\nПО ПРОВЕРКЕ СМЫСЛА\nС-01 — оспорено\n")
        fr2 = run([ca2, task, "src-fmt.md", "--review", "review-src-fmt.md"])
        expect("оспорено без причины отклонено", fr2.returncode == 1 and "без причины" in fr2.stdout, fr2.stdout)
        open(fmt, "w", encoding="utf-8").write(
            body_fmt + "\nПО ПРОВЕРКЕ СМЫСЛА\n- С-01 [блок] — исправлено: ослабил формулировку\n* **С-02** — снято\n"
            "С-03 – оспорено: фрагмент говорит об этом прямо\n")
        tm2 = run([os.path.join(HERE, "trust_map.py"), task])
        expect("счёт: блокирующие и обычные замечания по ответам",
               "блокирующих 1 (исправлено 1, снято 0, оспорено 0, без ответа 0); замечаний 2 (исправлено 0, снято 1, оспорено 1, без ответа 0)" in tm2.stdout, tm2.stdout)
        expect("в карту доверия попадает то, что проверяющий не сверил",
               "проверяющий не сверил: цифры в разделе 2" in tm2.stdout, tm2.stdout)
        for f in ("src-b-1.md", "src-b-2.md", "src-fmt.md", "review-src-fmt.md"):
            os.remove(os.path.join(task, f))

        # --- основы имён выводятся сами ---
        open(os.path.join(task, "private.txt"), "w", encoding="utf-8").write("Ольга\nМарина\n")
        stem_art = os.path.join(task, "src-stem.md")
        open(stem_art, "w", encoding="utf-8").write("Спросили Ольгу. Ответила Марине? Нет, Марины. Чисто: Интервью 4.\n")
        stp = run([os.path.join(HERE, "check_private.py"), task])
        expect("падежи имён ловятся, даже если в private.txt полная форма",
               stp.returncode == 1 and stp.stdout.count("термин из private.txt: Ольга") == 1 and stp.stdout.count("термин из private.txt: Марина") == 1, stp.stdout)
        os.remove(stem_art)
        os.remove(os.path.join(task, "private.txt"))

        # --- хуки не блокируют всё, если скрипта нет; блокируют, когда он есть ---
        import json as _json
        cfg = _json.load(open(os.path.join(os.path.dirname(HERE), ".claude", "settings.json"), encoding="utf-8"))
        proj = tempfile.mkdtemp(prefix="polygon-hooks-")
        os.makedirs(os.path.join(proj, "scripts", "hooks"))
        for hn in ("guard_writes.py", "stop_check.py"):
            shutil.copy(os.path.join(HERE, "hooks", hn), os.path.join(proj, "scripts", "hooks", hn))
        pre_cmd = cfg["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        stop_cmd = cfg["hooks"]["Stop"][0]["hooks"][0]["command"]
        forbidden = _json.dumps({"tool_name": "Write", "tool_input": {"file_path": "methodology/x.md"}})
        lost = subprocess.run(["sh", "-c", pre_cmd], input=forbidden, capture_output=True, text=True,
                              env=dict(os.environ, CLAUDE_PROJECT_DIR="/нет/такой/папки"))
        expect("хук записи: скрипта нет — запись не блокируется", lost.returncode == 0, lost.stderr)
        lost2 = subprocess.run(["sh", "-c", stop_cmd], input="{}", capture_output=True, text=True,
                               env=dict(os.environ, CLAUDE_PROJECT_DIR="/нет/такой/папки"))
        expect("стоп-хук: скрипта нет — ответ не блокируется", lost2.returncode == 0, lost2.stderr)
        found = subprocess.run(["sh", "-c", pre_cmd], input=forbidden, capture_output=True, text=True,
                               env=dict(os.environ, CLAUDE_PROJECT_DIR=proj))
        expect("хук записи: скрипт на месте — запись в систему блокируется", found.returncode == 2, found.stderr)
        shutil.rmtree(proj, ignore_errors=True)

        hook = os.path.join(HERE, "hooks", "guard_writes.py")
        env = dict(os.environ, CLAUDE_PROJECT_DIR=root)

        def hook_code(payload):
            return run([hook], json.dumps(payload), env=env).returncode

        expect("хук: правка методологии запрещена", hook_code({"tool_name": "Write", "tool_input": {"file_path": "methodology/x.md"}}) == 2)
        expect("хук: правка реестра запрещена", hook_code({"tool_name": "Edit", "tool_input": {"file_path": "tasks/demo/sources.csv"}}) == 2)
        expect("хук: артефакт разрешён", hook_code({"tool_name": "Write", "tool_input": {"file_path": "tasks/demo/02-h.md"}}) == 0)
        expect("хук: лог от подагента запрещён",
               hook_code({"tool_name": "Write", "tool_input": {"file_path": "tasks/demo/log.md"}, "agent_id": "a1"}) == 2)
        expect("хук: лог от оркестратора разрешён", hook_code({"tool_name": "Write", "tool_input": {"file_path": "tasks/demo/log.md"}}) == 0)
        expect("хук: context/ от подагента запрещён",
               hook_code({"tool_name": "Write", "tool_input": {"file_path": "context/brief.md"}, "agent_id": "a1"}) == 2)
        expect("хук: context/ от основной сессии разрешён", hook_code({"tool_name": "Write", "tool_input": {"file_path": "context/brief.md"}}) == 0)
        expect("хук: from-tasks разрешён", hook_code({"tool_name": "Write", "tool_input": {"file_path": "context/from-tasks/src-x.md"}}) == 0)
        stop = os.path.join(HERE, "hooks", "stop_check.py")
        os.makedirs(os.path.join(root, "scripts"))
        shutil.copy(cq, os.path.join(root, "scripts", "check_quotes.py"))
        shutil.copy(cn, os.path.join(root, "scripts", "check_numbers.py"))
        shutil.copy(an, os.path.join(root, "scripts", "add_number.py"))
        shutil.copy(cq, os.path.join(root, "scripts", "check_quotes.py"))
        os.remove(os.path.join(task, "src-bad.md"))
        open(os.path.join(task, "src-n.md"), "w", encoding="utf-8").write("Фантом числа [N-077]. Рост 12% [N-001].\n")
        sn = run([stop], json.dumps({"stop_hook_active": False}), env=env)
        expect("стоп-хук: ошибки чисел не дают закончить", sn.returncode == 2 and "числа:" in sn.stderr and "N-077" in sn.stderr, sn.stderr)
        os.remove(os.path.join(task, "src-n.md"))
        open(bad, "w", encoding="utf-8").write("Подмена: «вручную в Excel» [F-001].\n")
        s1 = run([stop], json.dumps({"stop_hook_active": False}), env=env)
        expect("стоп-хук: ошибки цитат не дают закончить", s1.returncode == 2 and "src-bad.md" in s1.stderr, s1.stderr)
        s2 = run([stop], json.dumps({"stop_hook_active": True}), env=env)
        expect("стоп-хук: второй раз подряд не блокирует", s2.returncode == 0, s2.stderr)
        os.remove(bad)
        open(os.path.join(task, "src-n.md"), "w", encoding="utf-8").write("ok\n")
        os.remove(os.path.join(task, "src-n.md"))
        s3 = run([stop], json.dumps({"stop_hook_active": False}), env=env)
        expect("стоп-хук: без ошибок не мешает", s3.returncode == 0, s3.stderr)

        open(os.path.join(root, ".polygon-dev"), "w").close()
        expect("хук: режим правки системы", hook_code({"tool_name": "Write", "tool_input": {"file_path": "AGENTS.md"}}) == 0)
        closed_web_tests(root)
        readable_tests(root)
        step_tests(root)
        log_sources_tests(root)
        publish_tests(root)
        readers_tests(root)
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print()
    if fails:
        print("Провалов: {}".format(len(fails)))
        for f in fails:
            print(" - " + f)
        sys.exit(1)
    print("Все проверки прошли.")


if __name__ == "__main__":
    main()
