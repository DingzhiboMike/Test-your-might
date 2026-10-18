#!/usr/bin/env python3
"""Самопроверка скриптов: запускай после любой правки в scripts/.

  python3 scripts/selftest.py

Собирает временную задачу и проверяет, что проверки ловят то, что должны, и не ругаются на верное:
русский текст, ё/е, тире, пропуск «…», подмену источника, непрочитанный источник, цитату без id,
пустой артефакт, файл вне периметра, хук записи, стоп-хук, проверку смысла (цитаты [A], ответы автора), реестр чисел (пересчёт, период, противоречия). Сеть не нужна.
"""
import json
import os
import re
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
    open(os.path.join(cw, "log.md"), "w", encoding="utf-8").write("ШАГ 1\nЗапросы:   WebSearch «требования к рекламе»\nПроверки: ок\nЗамечание: проект ПартнёрКо одобрен\n")
    open(os.path.join(cw, "src-a.md"), "w", encoding="utf-8").write("Проект ПартнёрКо — чисто для артефакта.\n")
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
        "07b-editor.md": "# Бриф\n\n## Онбординг\nСлова клиентов: «%s» (опрос клиентов)\n" % q,
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
    expect("читаемость: модуль методологии, слот, D-1 и Г-2 в документе валидации пойманы", r.returncode == 1 and "номер гипотезы" in r.stdout and "слово системы" in r.stdout, r.stdout)
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
    open(os.path.join(d, "00-tz.md"), "w", encoding="utf-8").write(
        "ТЗ\n\nGAP:\n  1. Почему клиенты бросают пробный период [ключевой] {ответ: контекст, веб}\n"
        "  2. Отзывы о сервисах: где искать / как отбирать / как строить выборку {ответ: веб}\n"
        "  3. Доля бросивших по тарифам {ответ: данные}\n\nВЕБ: да\n")
    good = ("# Лог\n\nШАГ 1 — b2b-consultant\nДыра: постановка\n\n"
            "ШАГ 2 — market-analyze\nПункт GAP: GAP 1 — Почему клиенты бросают пробный период\n"
            "Вопрос:   что клиенты называют причиной; веб; ≥5 причин со словами клиента; 12 запросов\n"
            "Зачем:    без этого генератор угадает причину\nУже известно: F-002 — утверждение команды, проверяется\nРезультат: совпал\n\n"
            "ШАГ 3 — alternatives-analyst\nПункт GAP: GAP 2 — Отзывы о сервисах: где искать / как отбирать / как строить выборку\n"
            "Вопрос:   где искать отзывы, как их отбирать и как построить выборку; веб; три площадки и правило отбора; 10 запросов\n"
            "Зачем:    без этого проверка по сути опирается на случайные отзывы\nУже известно: нет\n\n"
            "Запрос данных D-1\nВопрос:      доля бросивших по тарифам\nЧто снять:   выгрузка\n"
            "Метрика:     доля бросивших = бросили / начали пробный; окно 30 дней\nОдна строка: один клиент\n"
            "Сверка:      итог около 4 000 клиентов; главнее отчёт подписок\n"
            "Если данных не будет: 10 звонков бросившим за неделю; не покажет долю, только причины\n\n"
            "ШАГ 4 — hypothesis-generator\nДыра: гипотезы\n")
    w = lambda t: open(os.path.join(d, "log.md"), "w", encoding="utf-8").write(t)
    w(good)
    r = run([cl, d])
    expect("лог: шаги-источники с дословным пунктом GAP и запрос данных с заменой проходят", r.returncode == 0, r.stdout)
    r = run([cl, d])
    expect("лог: нет строки «Инструмент» — только предупреждение", r.returncode == 0 and "Инструмент" in r.stdout, r.stdout)
    tool_line = "Инструмент: Э · Чувствительность: что тест мог увидеть — пункт про то, мог ли тест увидеть эффект\n"
    w(good.replace("Зачем:    без этого генератор угадает причину\n", tool_line + "Зачем:    без этого генератор угадает причину\n"))
    r = run([cl, d])
    expect("лог: «Инструмент» из указателя принят", r.returncode == 0 and "указателе" not in r.stdout, r.stdout)
    tz0 = open(os.path.join(d, "00-tz.md"), encoding="utf-8").read()
    open(os.path.join(d, "00-tz.md"), "w", encoding="utf-8").write(tz0 + "ТИП ВЫХОДА: гипотезы\n")
    r = run([cl, d])
    expect("линзы: тип «гипотезы» без блока ЛИНЗЫ перед генератором — поймано", r.returncode == 1 and "ЛИНЗЫ" in r.stdout, r.stdout)
    lens = ("ЛИНЗЫ\nКогда — зову customer-path: момент, когда бросают\nВместо нас — зову alternatives-analyst: чем заменяют\n"
            "Кто — не нужно: карта знания отвечает, GAP 1, роли в двух интервью\nЧто болит — не нужно: шаг 2 market-analyze уже собрал слова\n\n")
    w(good.replace("ШАГ 4 — hypothesis-generator", lens + "ШАГ 4 — hypothesis-generator"))
    r = run([cl, d])
    expect("линзы: блок с вызовами и причинами проходит", r.returncode == 0, r.stdout)
    w(good.replace("ШАГ 4 — hypothesis-generator", lens.replace("зову customer-path: момент, когда бросают", "не нужно: ответ во внутренних данных компании") + "ШАГ 4 — hypothesis-generator"))
    r = run([cl, d])
    expect("линзы: «не нужно — внутренние данные» не принято", r.returncode == 1 and "Когда" in r.stdout, r.stdout)
    nolens = lens.replace("зову customer-path: момент, когда бросают", "не нужно: линза не касается вопроса, он про цену").replace("зову alternatives-analyst: чем заменяют", "не нужно: альтернативы разобраны в прошлом квартале")
    w(good.replace("ШАГ 4 — hypothesis-generator", nolens + "ШАГ 4 — hypothesis-generator"))
    r = run([cl, d])
    expect("линзы: при «ВЕБ: да» ни одной вызванной — поймано", r.returncode == 1 and "ни одна линза" in r.stdout, r.stdout)
    open(os.path.join(d, "00-tz.md"), "w", encoding="utf-8").write(tz0)
    for ref in ("Д · Шаблон запроса", "К · Паспорт источника", "О · Оценка Ферми: порядок величины", "П · Окупаемость акции",
                "Ж · Этапы: по состоянию, а не по календарю", "С · Граница категории"):
        w(good.replace("Зачем:    без этого генератор угадает причину\n", "Инструмент: %s — почему\nЗачем:    без этого генератор угадает причину\n" % ref))
        r = run([cl, d])
        expect("лог: «Инструмент» %s принят" % ref[:1], r.returncode == 0 and "указателе" not in r.stdout, r.stdout)
    w(good.replace("Зачем:    без этого генератор угадает причину\n", "Инструмент: M99 · Выдуманный раздел\nЗачем:    без этого генератор угадает причину\n"))
    r = run([cl, d])
    expect("лог: «Инструмент» не из указателя — ошибка", r.returncode == 1 and "указателе" in r.stdout, r.stdout)
    w(good.replace("Зачем:    без этого генератор угадает причину\n", "Инструмент: — подходящего нет\nЗачем:    без этого генератор угадает причину\n"))
    r = run([cl, d])
    expect("лог: «Инструмент: —» принят", r.returncode == 0, r.stdout)
    w(good.replace("Зачем:    без этого генератор угадает причину\n", "Зачем:    —\n"))
    r = run([cl, d])
    expect("лог: пустое «Зачем» у источника поймано", r.returncode == 1 and "Зачем" in r.stdout, r.stdout)
    w(good.replace("Уже известно: F-002 — утверждение команды, проверяется\n", ""))
    r = run([cl, d])
    expect("лог: нет «Уже известно» у источника — поймано", r.returncode == 1 and "Уже известно" in r.stdout, r.stdout)
    w(good.replace("GAP 1 — Почему клиенты бросают пробный период", "GAP 1 — почему бросают"))
    r = run([cl, d])
    expect("лог: пересказ пункта GAP вместо дословного — пойман", r.returncode == 1 and "дословно" in r.stdout, r.stdout)
    narrow = good.replace("где искать отзывы, как их отбирать и как построить выборку", "где искать отзывы")
    w(narrow)
    r = run([cl, d])
    expect("лог: вопрос уже пункта GAP — потерянные части пойманы", r.returncode == 1 and "как отбирать" in r.stdout, r.stdout)
    w(narrow.replace("Зачем:    без этого проверка", "Сужение: отбор и выборку задаёт проверка по сути — убраны\nЗачем:    без этого проверка"))
    r = run([cl, d])
    expect("лог: сужение с причиной засчитано", r.returncode == 0, r.stdout)
    w(good.replace("Пункт GAP: GAP 1 — Почему клиенты бросают пробный период\n", "Пункт GAP: GAP 3 — Доля бросивших по тарифам\n"))
    r = run([cl, d])
    expect("лог: веб по пункту с ответом во внутренних данных — пойман", r.returncode == 1 and "Пересмотр" in r.stdout, r.stdout)
    w(good.replace("Если данных не будет: 10 звонков бросившим за неделю; не покажет долю, только причины\n", ""))
    r = run([cl, d])
    expect("лог: запрос данных без дешёвой замены — пойман", r.returncode == 1 and "D-1" in r.stdout, r.stdout)
    for field_name in ("Метрика", "Одна строка", "Сверка"):
        lines = [ln for ln in good.split("\n") if ln.startswith(field_name)]
        w(good.replace("\n".join(lines) + "\n", "") if lines else good)
        r = run([cl, d])
        expect("лог: запрос данных без строки «%s» — пойман" % field_name,
               r.returncode == 1 and field_name in r.stdout, r.stdout)


def fresh_tests(root):
    cf = os.path.join(HERE, "check_fresh.py")
    d = os.path.join(root, "tasks", "frs")
    os.makedirs(d)
    open(os.path.join(d, "sources.csv"), "w", encoding="utf-8").write(
        "id,kind,location,pub_date,data_date\nF-001,web,https://a.example,2015-05-01,unknown\n"
        "F-002,web,https://b.example,2026-03-01,unknown\nF-003,web,https://c.example,unknown,unknown\n"
        "F-004,context,context/a.md,2010,unknown\n")
    w = lambda t: open(os.path.join(d, "src-x.md"), "w", encoding="utf-8").write(t)
    w("«свежий тариф» [F-002]. Бриф: «старое» [F-004].\nНа форуме в 2015 году жаловались: «долго» [F-001].\n")
    r = run([cf, d, "src-x.md", "--today", "2026-10-01"])
    expect("свежесть: старый источник с годом в тексте проходит", r.returncode == 0, r.stdout)
    w("Вывод.\n\nСЧЁТ ОПОР (считает scripts/trust_map.py)\n\nПроверки смысла: отчётов нет\n  не сверено: источник [F-001]\n\n**Проверить вручную**\n")
    r = run([cf, d, "src-x.md", "--today", "2026-10-01"])
    expect("свежесть: блок СЧЁТ ОПОР не разбирается", r.returncode == 0, r.stdout)
    w("Клиенты жалуются: «долго» [F-001].\n«без даты» [F-003]\n")
    r = run([cf, d, "src-x.md", "--today", "2026-10-01"])
    expect("свежесть: старый источник без года пойман, без даты — предупреждение",
           r.returncode == 1 and "F-001" in r.stdout and "F-003 без даты" in r.stdout, r.stdout)


def long_list_tests(root):
    cl = os.path.join(HERE, "check_long_list.py")
    d = os.path.join(root, "tasks", "lng")
    os.makedirs(d)
    open(os.path.join(d, "00-tz.md"), "w", encoding="utf-8").write(
        "ТЗ\n\nРЕШЕНИЕ: что запускать; варианты: А — письмо; Б — звонок; критерий: ответы\n")
    head = "| № | Ход | Кому | Вариант решения | Опора | Дешёвая проверка | Дней до сигнала |\n| --- | --- | --- | --- | --- | --- | --- |\n"
    body = ""
    for i in range(1, 17):
        support = "«жалоба» [F-00%d] [F-01%d]" % (i % 9 + 1, i % 9) if i % 3 == 0 else "нет"
        body += "| %d | Ход номер %d для малых команд | малые команды | %s | %s | 10 звонков | %d |\n" % (
            i, i, "А" if i % 2 else "Б", support, 7 + i)
    body += "| 17 | Ход без варианта | все | — | нет | опрос | 5 |\n"
    body += "| 18 | Долгий ход | все | А | нет | пилот | 60 |\n"
    open(os.path.join(d, "02-long-list.md"), "w", encoding="utf-8").write(head + body)
    r = run([cl, d])
    rep = open(os.path.join(d, "checks", "long-list.md"), encoding="utf-8").read()
    expect("длинный список: отсев по правилам, опоры выше", r.returncode == 0 and "отсеян — не сдвигает решение" in rep
           and "отсеян — дороже месяца" in rep and "в глубину 3, 6, 9, 12, 15" in r.stdout, r.stdout + rep)
    open(os.path.join(d, "02-long-list.md"), "w", encoding="utf-8").write(head + body.split("| 6 |")[0])
    r = run([cl, d])
    expect("длинный список: меньше 15 строк — ошибка", r.returncode == 1 and "15–25" in r.stdout, r.stdout)


def backlog_tests(root):
    cr = os.path.join(HERE, "check_readable.py")
    d = os.path.join(root, "tasks", "bkl")
    os.makedirs(d)
    open(os.path.join(d, "00-tz.md"), "w", encoding="utf-8").write("ТИП ВЫХОДА: гипотезы\n")
    open(os.path.join(d, "02e-position.md"), "w", encoding="utf-8").write("# Позиция\n\nЗапускать письмо малым командам.\n")
    r = run([cr, d])
    expect("бэклог: финиш «гипотезы» без бэклога — ошибка", r.returncode == 1 and "03-backlog.md" in r.stdout, r.stdout)
    row = "| 1 | малые команды, в выгрузке: нет входа 14 дней | «отчёт за минуту» | письмо, маркетолог | доля ответов | ≥8%% из 200 | <3%% | 2 недели, бесплатно | %s |\n"
    head = "| № | Кому и как найти | Что говорим | Где и кто | Метрика | Успех | Отсечение | Срок и цена | Что решит |\n| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
    open(os.path.join(d, "03-backlog.md"), "w", encoding="utf-8").write(head + row % "запускать ли письмо всем")
    r = run([cr, d])
    expect("бэклог: полная таблица проходит", r.returncode == 0, r.stdout)
    open(os.path.join(d, "03-backlog.md"), "w", encoding="utf-8").write(head + row % "—")
    r = run([cr, d])
    expect("бэклог: пустая колонка поймана", r.returncode == 1 and "не заполнены" in r.stdout, r.stdout)
    open(os.path.join(d, "03-backlog.md"), "w", encoding="utf-8").write(head + row % "закрывает П-1")
    r = run([cr, d])
    expect("бэклог: внутренний номер пункта пути пойман", r.returncode == 1 and "П-1" in r.stdout, r.stdout)
    open(os.path.join(d, "03-backlog.md"), "w", encoding="utf-8").write(head + row % "запускать ли письмо всем")
    open(os.path.join(d, "08-handoff.md"), "w", encoding="utf-8").write(
        "# Сдача\n\nЗапускаем письмо; ответ аналитика по выгрузке — до пятницы.\n\n## Служебное\n\nП-1 | GAP 1 | закрыт; D-4\n")
    r = run([cr, d])
    expect("сдача: служебная часть не проверяется", r.returncode == 0, r.stdout)
    open(os.path.join(d, "08-handoff.md"), "w", encoding="utf-8").write("# Сдача\n\nСм. D-4 и Г-3.\n\n## Служебное\n")
    r = run([cr, d])
    expect("сдача: номера в части для человека пойманы", r.returncode == 1 and "D-4" in r.stdout and "номер гипотезы" in r.stdout, r.stdout)
    open(os.path.join(d, "00-tz.md"), "w", encoding="utf-8").write("ТИП ВЫХОДА: гипотезы\nЁМКОСТЬ:    2 проверки за 2 недели\n")
    os.remove(os.path.join(d, "08-handoff.md"))
    open(os.path.join(d, "03-backlog.md"), "w", encoding="utf-8").write(head + "".join(
        (row % "запускать ли письмо всем").replace("| 1 |", "| %d |" % i) for i in range(1, 5)))
    r = run([cr, d])
    expect("бэклог: тестов больше, чем ёмкость + 1, — поймано", r.returncode == 1 and "лимите 3" in r.stdout, r.stdout)
    open(os.path.join(d, "03-backlog.md"), "w", encoding="utf-8").write(head + "".join(
        (row % "запускать ли письмо всем").replace("| 1 |", "| %d |" % i) for i in range(1, 4)) + "\nВ очереди: письмо бухгалтерам.\n")
    r = run([cr, d])
    expect("бэклог: ёмкость + 1 тестов и строка «В очереди» проходят", r.returncode == 0, r.stdout)


def effort_tests(root):
    ce = os.path.join(HERE, "check_effort.py")
    d = os.path.join(root, "tasks", "eff")
    os.makedirs(d)
    tz = ("ТЗ\n\nGAP:\n  1. Как выбрать момент письма [ключевой] {ответ: контекст, веб}\n  2. Что пишут конкуренты {ответ: веб}\n\n"
          "ВЕБ:        да — пункты 1, 2\nТИП ВЫХОДА: гипотезы\nЁМКОСТЬ:    2 проверки за 2 недели\n")
    open(os.path.join(d, "00-tz.md"), "w", encoding="utf-8").write(tz)
    log = lambda t: open(os.path.join(d, "log.md"), "w", encoding="utf-8").write("# Лог задачи: eff\n\n" + t)
    log("ШАГ 1 — b2b-consultant\n")
    r = run([ce, d])
    expect("усилие: ключевой пункт с ответом в вебе без хода — поймано", r.returncode == 1 and "GAP 1" in r.stdout and "GAP 2" not in r.stdout, r.stdout)
    log("ШАГ 1 — b2b-consultant\nБез хода: GAP 1 — мало данных в открытых источниках\n")
    r = run([ce, d])
    expect("усилие: «мало данных» причиной не считается", r.returncode == 1 and "не принимается" in r.stdout, r.stdout)
    log("ШАГ 1 — b2b-consultant\nБез хода: GAP 1 — момент виден целиком в выгрузке событий, которую человек приложил\n")
    r = run([ce, d])
    expect("усилие: пропуск с содержательной причиной принят", r.returncode == 0, r.stdout)
    log("ШАГ 2 — customer-path\nПункт GAP: GAP 1 — Как выбрать момент письма\n")
    r = run([ce, d])
    expect("усилие: ход к источнику по ключевому пункту засчитан", r.returncode == 0, r.stdout)
    log("ШАГ 5 — hypothesis-validator\nОстаток: свободных вызовов нет: дальше только резерв и финиш\n")
    r = run([ce, d])
    expect("усилие: без свободных вызовов пропуск — предупреждение, не ошибка", r.returncode == 0 and "предупреждение" in r.stdout, r.stdout)
    open(os.path.join(d, "02c-validation.md"), "w", encoding="utf-8").write("ГИПОТЕЗА 1 — а\nВердикт:    сузить\n")
    hand = lambda t: open(os.path.join(d, "08-handoff.md"), "w", encoding="utf-8").write(t)
    hand("# Сдача\n\n## Что запускать\nПисьмо.\n\n## Служебное\n")
    r = run([ce, d])
    expect("усилие: всё «сузить», а сдача не с запроса данных — поймано", r.returncode == 1 and "двигаться дальше" in r.stdout, r.stdout)
    more = "## А ещё есть идеи\n1. Бухгалтеру\n2. Календарь\n3. Кнопка\n4. Чат\n"
    hand("# Сдача\n\n## Что нужно, чтобы двигаться дальше\nВыгрузка событий.\n\n" + more + "\n## Служебное\n")
    r = run([ce, d])
    expect("усилие: идей в сдаче больше ёмкости + 1 — поймано", r.returncode == 1 and "4 идей" in r.stdout, r.stdout)
    hand("# Сдача\n\n## Что нужно, чтобы двигаться дальше\nВыгрузка событий.\n\n" + more.replace("4. Чат\n", "В очереди: чат.\n") + "\n## Служебное\n")
    r = run([ce, d])
    expect("усилие: сдача с запроса данных и ёмкостью + 1 идей проходит", r.returncode == 0, r.stdout)
    open(os.path.join(d, "00-tz.md"), "w", encoding="utf-8").write(tz.replace("ТИП ВЫХОДА: гипотезы", "ТИП ВЫХОДА: валидация"))
    r = run([ce, d])
    expect("усилие: валидация не проверяется", r.returncode == 0 and "не из проверяемых" in r.stdout, r.stdout)


def knowledge_links_tests(root):
    ck = os.path.join(HERE, "check_knowledge.py")
    d = os.path.join(root, "tasks", "knl")
    os.makedirs(d)
    open(os.path.join(d, "00-tz.md"), "w", encoding="utf-8").write("ТЗ\n\nGAP:\n  1. Почему упали продажи\n\nНА ВХОДЕ: идея\n")
    open(os.path.join(d, "sources.csv"), "w", encoding="utf-8").write("id,kind,location\nF-001,context,context/a.md\n")
    base = ("1. ПОКРЫТИЕ ФАЙЛОВ\n\n| Файл | Тип | Прочитан | К каким пунктам GAP относится | Фрагментов взято |\n| --- | --- | --- | --- | --- |\n"
            "| F-001 · таблица | данные | целиком | 1 | 2 |\n\n2. ПО ПУНКТАМ GAP\n\nGAP 1 — Почему упали продажи\nУже известно:\n%s"
            "Чего нет:\n  - связи падения с ценой: данных нет\n")
    w = lambda t: open(os.path.join(d, "00k-knowledge.md"), "w", encoding="utf-8").write(base % t)
    w("  - «заказы за квартал» [F-001] — период таблицы\n")
    r = run([ck, d])
    expect("материалы: фрагмент без выводов и «связь» в «Чего нет» проходят", r.returncode == 0, r.stdout)
    w("  - «заказы за квартал» [F-001] — совпадает с обновлением сайта\n")
    r = run([ck, d])
    expect("материалы: выведенное совпадение поймано", r.returncode == 1 and "совпадает" in r.stdout, r.stdout)
    w("  - «заказы за квартал» [F-001] и «новая версия сайта» [F-001] [рядом, связь не проверена]\n")
    r = run([ck, d])
    expect("материалы: два фрагмента рядом с пометкой — допустимо", r.returncode == 0, r.stdout)


def publish_tests(root):
    cp = os.path.join(HERE, "check_publish.py")
    repo = os.path.join(root, "pubrepo")
    os.makedirs(os.path.join(repo, "tasks", "t1"))
    g = lambda *a: subprocess.run(["git", "-C", repo] + list(a), capture_output=True, text=True)
    g("init", "-q")
    g("config", "user.email", "t@example.com")
    g("config", "user.name", "t")
    open(os.path.join(repo, ".gitignore"), "w", encoding="utf-8").write("tasks/*\n")
    open(os.path.join(repo, "tasks", "t1", "private.txt"), "w", encoding="utf-8").write("# имена\nТестина\n")
    open(os.path.join(repo, "tasks", "t1", "closed-web.txt"), "w", encoding="utf-8").write("ПартнёрКо\n")
    open(os.path.join(repo, "a.md"), "w", encoding="utf-8").write("Собрать максимум источников. Пример: Пробна.\n")
    g("add", "-A")
    g("commit", "-q", "-m", "чистый коммит")
    r = subprocess.run([PY, cp, "--all"], capture_output=True, text=True, cwd=repo)
    expect("публикация: чистый репозиторий проходит", r.returncode == 0, r.stdout + r.stderr)
    open(os.path.join(repo, "a.md"), "a", encoding="utf-8").write("Сказала Тестине про проект партнёрко.\n")
    g("commit", "-q", "-am", "добавил пример")
    r = subprocess.run([PY, cp, "--all"], capture_output=True, text=True, cwd=repo)
    expect("публикация: имя в падеже и закрытое слово пойманы", r.returncode == 1 and "Тестин" in r.stdout and "ПартнёрКо" in r.stdout, r.stdout)
    g("commit", "-q", "--allow-empty", "-m", "по задаче Тестины")
    head = g("rev-parse", "HEAD").stdout.strip()
    r = subprocess.run([PY, cp, "--pre-push"], input="refs/heads/main %s refs/heads/main %s\n" % (head, "0" * 40),
                       capture_output=True, text=True, cwd=repo)
    expect("публикация: хук перед отправкой ловит имя в сообщении коммита", r.returncode == 1 and "сообщение коммита" in r.stdout, r.stdout)


def path_tests(root):
    cp = os.path.join(HERE, "check_path.py")
    d = os.path.join(root, "tasks", "pth")
    os.makedirs(d)
    open(os.path.join(d, "00-tz.md"), "w", encoding="utf-8").write(
        "ТЗ\n\nGAP:\n  1. Держится ли идея чек-листа [ключевой] {ответ: контекст, живая}\n  2. Кто бросает пробный период {ответ: данные}\n"
        "  3. Сколько таких компаний {ответ: веб}\n\nНА ВХОДЕ: идея\nВЕБ: да — пункт 3\n"
        "ЦЕНА:       ~20 вызовов исполнителей (свободная часть 8, резерв 12, потолок 26), ~1,7 млн токенов\n")
    review = ("ПУТЬ\nП-1. Что должно стать известно: почему бросают пробный период\n     Закрывает GAP: 1, 2  [ключевой] [проверка допущения]\n"
              "     Сдвигает: А, Б\n     Чего не хватает в карте: причин ухода нет\n"
              "П-2. Что должно стать известно: хватит ли компаний\n     Закрывает GAP: 3\n     Сдвигает: Б\n     Чего не хватает в карте: числа компаний нет\n")
    open(os.path.join(d, "01-review.md"), "w", encoding="utf-8").write(review)
    log = "# Лог\n\nПУТЬ — ИСХОДЫ\nП-1 | GAP 1, 2 | закрыт: src-market.md\nП-2 | GAP 3 | запрос данных D-1\n"
    open(os.path.join(d, "log.md"), "w", encoding="utf-8").write(log)
    r = run([cp, d])
    expect("путь: всё привязано и у каждого пункта исход", r.returncode == 0, r.stdout)
    open(os.path.join(d, "01-review.md"), "w", encoding="utf-8").write(review.replace("Закрывает GAP: 3", "Закрывает GAP: —"))
    r = run([cp, d])
    expect("путь: пункт GAP без привязки пойман", r.returncode == 1 and "GAP 3" in r.stdout, r.stdout)
    open(os.path.join(d, "01-review.md"), "w", encoding="utf-8").write(review.replace("Закрывает GAP: 3", "Закрывает GAP: —") + "Вне пути: GAP 3 — не влияет на решение\n")
    r = run([cp, d])
    expect("путь: «вне пути» с причиной засчитан", r.returncode == 0, r.stdout)
    open(os.path.join(d, "log.md"), "w", encoding="utf-8").write(log.replace("П-2 | GAP 3 | запрос данных D-1\n", "П-2 | GAP 3 | —\n"))
    r = run([cp, d])
    expect("путь: пункт без исхода пойман", r.returncode == 1 and "П-2" in r.stdout, r.stdout)
    open(os.path.join(d, "log.md"), "w", encoding="utf-8").write("# Лог\n")
    r = run([cp, d])
    expect("путь: нет раздела «ПУТЬ — ИСХОДЫ» — ошибка", r.returncode == 1 and "ПУТЬ — ИСХОДЫ" in r.stdout, r.stdout)
    r = run([cp, d, "--plan"])
    expect("план: без исходов в логе проверка плана проходит", r.returncode == 0, r.stdout)
    open(os.path.join(d, "00-tz.md"), "a", encoding="utf-8").write("РЕШЕНИЕ: запускать ли чек-лист; варианты: А — на всех; Б — только на новых; В — не запускать\n")
    r = run([cp, d, "--plan"])
    expect("план: вариант решения без пункта пути пойман", r.returncode == 1 and "«В»" in r.stdout, r.stdout)
    open(os.path.join(d, "01-review.md"), "w", encoding="utf-8").write(review.replace(" [проверка допущения]", "").replace("Сдвигает: Б\n", "Сдвигает: Б, В\n"))
    r = run([cp, d, "--plan"])
    expect("план: нет пункта на проверку допущения — пойман", r.returncode == 1 and "проверка допущения" in r.stdout, r.stdout)
    r = run([cp, d, "--tz"])
    expect("ТЗ: пометки, где ответ, и ВЕБ согласованы", r.returncode == 0, r.stdout)
    tz = open(os.path.join(d, "00-tz.md"), encoding="utf-8").read()
    open(os.path.join(d, "00-tz.md"), "w", encoding="utf-8").write(tz.replace(" {ответ: данные}", ""))
    r = run([cp, d, "--tz"])
    expect("ТЗ: пункт без пометки, где ответ, пойман", r.returncode == 1 and "GAP 2" in r.stdout, r.stdout)
    open(os.path.join(d, "00-tz.md"), "w", encoding="utf-8").write(tz.replace("ВЕБ: да — пункт 3", "ВЕБ: нет — сеть закрыта"))
    r = run([cp, d, "--tz"])
    expect("ТЗ: «ВЕБ: нет» при пункте с ответом в вебе — пойман", r.returncode == 1 and "ВЕБ: нет" in r.stdout, r.stdout)
    open(os.path.join(d, "00-tz.md"), "w", encoding="utf-8").write(re.sub(r"ЦЕНА:.*\n", "", tz))
    r = run([cp, d, "--tz"])
    expect("ТЗ: без строки ЦЕНА — поймано", r.returncode == 1 and "ЦЕНА" in r.stdout, r.stdout)


def polygon_more_tests(root):
    """Полигон: полнота тегов карты и сверка разбора интервью по заложенным сигналам."""
    pg = os.path.join(HERE, "polygon.py")
    r = run([pg, "map-recall", "--seed", "1", "--min", "0.9"])
    expect("полигон карты: полнота тегов не ниже порога CI, ложных тегов нет", r.returncode == 0 and "ложных тегов на нейтральных строках: 0" in r.stdout, r.stdout)
    out, key = os.path.join(root, "iv"), os.path.join(root, "iv-key.json")
    r = run([pg, "make-interviews", "--seed", "3", "--n", "4", "--out", out, "--key-out", key])
    k = json.load(open(key, encoding="utf-8"))
    expect("полигон интервью: транскрипты и ключ отдельно", r.returncode == 0 and len(k) == 4 and len(os.listdir(out)) == 4, r.stdout)
    ans = os.path.join(root, "iv-answer.md")
    open(ans, "w", encoding="utf-8").write("СВЕРКА\n" + "".join("%s | сигналы=%s\n" % (i, ",".join(v)) for i, v in k.items()))
    r = run([pg, "score-interviews", "--key", key, "--answer", ans, "--min", "0.99"])
    expect("полигон интервью: точный ответ — F1 1,00", r.returncode == 0 and "1.00" in r.stdout.split("Средний")[1], r.stdout)
    open(ans, "w", encoding="utf-8").write("СВЕРКА\nИ-01 | сигналы=цена\n")
    r = run([pg, "score-interviews", "--key", key, "--answer", ans, "--min", "0.7"])
    expect("полигон интервью: пропуски сигналов снижают F1 ниже порога", r.returncode == 1, r.stdout)


def message_tests():
    """Сообщения проверок называют нарушение и место, а не текст, которым его закрыть (защита от подгонки)."""
    import re as _re
    bad = []
    tmpl = _re.compile(r"<[а-яё][^>]{0,30}>|или «не найдено|нужно «|поставь год|процитируй или|«…»\s*\[F-id\]")
    for name in sorted(os.listdir(HERE)):
        if not (name.startswith("check_") and name.endswith(".py")):
            continue
        src = open(os.path.join(HERE, name), encoding="utf-8").read()
        for m in _re.finditer(r"(?:errors|problems|warns)\.append\((.*?)\)\n", src, _re.S):
            if tmpl.search(m.group(1)):
                bad.append("%s: %s" % (name, m.group(1)[:80]))
    expect("сообщения проверок без шаблонов для подгонки", not bad, "; ".join(bad))


def audit_tests(root):
    """Выборочный аудит: воспроизводимый план из мест с опорами, каждое место закрыто оценкой из блока данных."""
    d = os.path.join(root, "tasks", "aud")
    os.makedirs(d)
    au = os.path.join(HERE, "audit_sample.py")
    lines = ["ГИПОТЕЗА %d — х\nВердикт:    сузить\nОснование: «клиенты платят по счёту и карту не берут» [F-00%d]\n" % (i, i) for i in range(1, 6)]
    open(os.path.join(d, "02c-validation.md"), "w", encoding="utf-8").write("\n".join(lines))
    r = run([au, d, "--check"])
    expect("аудит: без плана — ошибка", r.returncode == 1 and "audit-plan.md" in r.stdout, r.stdout)
    r = run([au, d])
    plan1 = open(os.path.join(d, "audit-plan.md"), encoding="utf-8").read()
    run([au, d])
    expect("аудит: план воспроизводим — три места на артефакт",
           "мест 3" in r.stdout and plan1 == open(os.path.join(d, "audit-plan.md"), encoding="utf-8").read(), r.stdout)
    import re as _re
    marks = [(a, int(n)) for a, n in _re.findall(r"^- (\S+), строка (\d+):", plan1, _re.M)]
    rep = lambda items: open(os.path.join(d, "audit.md"), "w", encoding="utf-8").write(
        "```данные\n" + json.dumps({"аудит": items}, ensure_ascii=False) + "\n```\n")
    rep([{"артефакт": a, "строка": n, "оценка": "держит", "почему": "фрагмент прямо об этом"} for a, n in marks[:2]])
    r = run([au, d, "--check"])
    expect("аудит: неоценённое место поймано", r.returncode == 1 and "не оценено" in r.stdout, r.stdout)
    rep([{"артефакт": a, "строка": n, "оценка": "держит" if i else "подогнано", "почему": "…"} for i, (a, n) in enumerate(marks)])
    r = run([au, d, "--check"])
    expect("аудит: все места оценены — строка для сдачи", r.returncode == 0 and "подогнано 1" in r.stdout and "держит 2" in r.stdout, r.stdout)


def rules_tests():
    """Реестр правил: id в тексте и в реестре совпадают; новое правило без прогона не проходит; срабатывания по логам."""
    r = run([os.path.join(HERE, "rules.py"), "--check"])
    expect("правила: id в тексте системы и реестр совпадают", r.returncode == 0, r.stdout[-600:])
    proj = tempfile.mkdtemp(prefix="polygon-rules-")
    try:
        os.makedirs(os.path.join(proj, ".claude", "skills", "orchestrator", "routes"))
        os.makedirs(os.path.join(proj, "methodology"))
        open(os.path.join(proj, "AGENTS.md"), "w", encoding="utf-8").write(
            "# А\n\n## Принципы\n\n- **Знание не аксиома.** Проверяется.\n- **Мало данных — не ответ.** Версия нужна.\n\n## Где\n\n- не правило\n")
        open(os.path.join(proj, ".claude", "skills", "orchestrator", "SKILL.md"), "w", encoding="utf-8").write(
            "# Ядро\n\n**Без повтора на том же входе.** Нельзя.\n\n**Кто:** не правило\n")
        rp = [os.path.join(HERE, "rules.py"), "--root", proj]
        r = run(rp + ["--check"])
        expect("правила: правило без id поймано", r.returncode == 1 and "без id" in r.stdout, r.stdout)
        r = run(rp + ["--assign"])
        expect("правила: id расставлены только правилам", "Новых правил с id: 3" in r.stdout, r.stdout)
        expect("правила: после расстановки всё сходится", run(rp + ["--check"]).returncode == 0)
        reg = os.path.join(proj, "methodology", "rules.csv")
        lines = open(reg, encoding="utf-8").read().splitlines()
        cells = lines[1].split(",")
        cells[3] = "2099-01-01"
        lines[1] = ",".join(cells)
        open(reg, "w", encoding="utf-8").write("\n".join(lines) + "\n")
        r = run(rp + ["--check"])
        expect("правила: новое правило без прогона и регрессии не проходит", r.returncode == 1 and "R-001" in r.stdout and "прогон" in r.stdout, r.stdout)
        for i in range(5):
            t = os.path.join(proj, "tasks", "t%d" % i)
            os.makedirs(t)
            open(os.path.join(t, "00-tz.md"), "w", encoding="utf-8").write("ТИП ВЫХОДА: гипотезы\n")
            open(os.path.join(t, "log.md"), "w", encoding="utf-8").write("ШАГ 1\nПравило:  R-002 — сходил за данными вместо сдачи\n" if i == 0 else "ШАГ 1\n")
        r = run(rp + ["--usage"])
        expect("правила: без срабатываний за пять прогонов — кандидат на удаление, сработавшее — нет",
               "Кандидаты на удаление" in r.stdout and "R-003" in r.stdout.split("Кандидаты")[1] and "R-002" not in r.stdout.split("Кандидаты")[1], r.stdout)
    finally:
        shutil.rmtree(proj, ignore_errors=True)


def data_block_tests(root):
    """Блоки данных: проверяются по схеме и разбираются теми же проверками, что и текст."""
    d = os.path.join(root, "tasks", "dbk")
    os.makedirs(d)
    blk = lambda obj: "Текст для людей.\n\n```данные\n" + json.dumps(obj, ensure_ascii=False, indent=1) + "\n```\n"
    open(os.path.join(d, "02f-forecast.md"), "w", encoding="utf-8").write(
        "## НОВЫЕ ИДЕИ\n1. Писать бухгалтеру\n   Суть: …\n2. Календарь\n   Суть: …\n\nРАМКА\nСовпадает: да\n")
    idea = lambda n, v: {"n": n, "суть": "идея %d" % n, "вердикт": v, "убивает": "нет",
                         "возражения": "«бухгалтер не заходит в банк» [F-003] — ослабляет", "новая": "да",
                         "первый_шаг_различает": "да — поддержит: треть звонков; убьёт: ни одного",
                         "первый_шаг_выполним": "да — поле роли в реестре", "один_источник": "нет",
                         "данные_следующего_раунда": "роль пользователя"}
    ci = os.path.join(HERE, "check_ideas.py")
    open(os.path.join(d, "02g-ideas-check.md"), "w", encoding="utf-8").write(blk({"отсев_идей": [idea(1, "кажется валидной"), idea(2, "кажется валидной")]}))
    r = run([ci, d])
    expect("блок данных: отсев идей по схеме проходит", r.returncode == 0, r.stdout)
    open(os.path.join(d, "02g-ideas-check.md"), "w", encoding="utf-8").write(blk({"отсев_идей": [idea(1, "кажется валидной"), idea(2, "наверное да")]}))
    r = run([ci, d])
    expect("блок данных: вердикт не из списка пойман по полю", r.returncode == 1 and "отсев_идей[2].вердикт" in r.stdout, r.stdout)
    open(os.path.join(d, "02g-ideas-check.md"), "w", encoding="utf-8").write("```данные\n{\"отсев_идей\": [\n```\n")
    r = run([ci, d])
    expect("блок данных: битый JSON — ошибка, а не тишина", r.returncode == 1 and "не JSON" in r.stdout, r.stdout)

    ca = os.path.join(HERE, "check_artifact.py")
    open(os.path.join(d, "review-src-x.md"), "w", encoding="utf-8").write("С-01 [блок] Вывод сильнее фрагмента — …\nС-02 [блок] Круг — …\n")
    art = "# Разбор\n\n" + "Разрыв логики между первым запуском и регулярным использованием продукта. " * 8 + "\n\n"
    ans = [{"замечание": "С-01", "ответ": "исправлено", "что": "сузил вывод до группы"},
           {"замечание": "С-02", "ответ": "оспорено", "что": "второй фрагмент из другого корня [F-004]"}]
    open(os.path.join(d, "src-x.md"), "w", encoding="utf-8").write(art + blk({"по_проверке_смысла": ans}))
    r = run([ca, d, "src-x.md", "--review", "review-src-x.md"])
    expect("блок данных: ответы на проверку смысла засчитаны", r.returncode == 0, r.stdout)
    open(os.path.join(d, "src-x.md"), "w", encoding="utf-8").write(art + blk({"по_проверке_смысла": ans[:1]}))
    r = run([ca, d, "src-x.md", "--review", "review-src-x.md"])
    expect("блок данных: нет ответа на блокирующее — поймано", r.returncode == 1 and "С-02" in r.stdout, r.stdout)

    cr = os.path.join(HERE, "check_rehearsal.py")
    row = "| %d | новые клиенты | «вот что проверяет банк» | пуш, CRM | переходы | ≥20%% | <10%% | 6 недель | берём ли |\n"
    backlog = ("| № | Кому | Что говорим | Где | Метрика | Успех | Отсечение | Срок | Что решит |\n"
               "| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n" + row % 1 + row % 2)
    sl = {"для_эксперимента": [{"тест": "Строка 1", "статус": "как есть"},
                               {"тест": "Строка 2", "статус": "после правки", "что": "убрать наводящий вопрос"}],
          "для_решения": "решение не меняется, но тест 2 короче", "что_подсказали_персоны": "путают выписку и отчёт"}
    open(os.path.join(d, "03c-rehearsal.md"), "w", encoding="utf-8").write(blk({"следствия": sl}))
    open(os.path.join(d, "03-backlog.md"), "w", encoding="utf-8").write(backlog + "\n" + blk({"по_пробному_прогону": [
        {"тест": "Строка 2", "ответ": "применено", "что": "вопрос переписан"}]}))
    r = run([cr, d])
    expect("блок данных: следствия пробного прогона и ответы на них проходят", r.returncode == 0, r.stdout)
    open(os.path.join(d, "03-backlog.md"), "w", encoding="utf-8").write(backlog)
    r = run([cr, d])
    expect("блок данных: следствие без ответа в бэклоге поймано", r.returncode == 1 and "ПО ПРОБНОМУ ПРОГОНУ" in r.stdout, r.stdout)


def route_tests():
    """Маршрут в коде: state.json, периметр шага по хэшам, хук записи по шагу, возврат ошибок исполнителю."""
    proj = tempfile.mkdtemp(prefix="polygon-route-")
    try:
        open(os.path.join(proj, "AGENTS.md"), "w", encoding="utf-8").write("#\n")
        t = os.path.join(proj, "tasks", "rt")
        os.makedirs(t)
        rt = os.path.join(HERE, "route.py")
        open(os.path.join(t, "00-tz.md"), "w", encoding="utf-8").write("ТЗ\nТИП ВЫХОДА: вердикты по проверке\n")
        r = run([rt, "init", t])
        expect("маршрут: без СОГЛАСОВАНО не заводится", r.returncode == 1 and "СОГЛАСОВАНО" in r.stdout, r.stdout)
        open(os.path.join(t, "00-tz.md"), "a", encoding="utf-8").write("СОГЛАСОВАНО: да\n")
        r = run([rt, "init", t])
        expect("маршрут: заведён по типу выхода", r.returncode == 0 and "вердикты по проверке" in r.stdout, r.stdout)
        body = "# Вердикты\n\n" + "Гипотеза о письме малым командам: критерий успеха не достигнут, отсекаем. " * 8 + "\n"
        hook = os.path.join(HERE, "hooks", "guard_writes.py")

        def write_code(name):
            d = {"cwd": proj, "tool_name": "Write", "agent_id": "a1", "agent_type": "results-reviewer",
                 "tool_input": {"file_path": os.path.join(t, name)}}
            return run([hook], json.dumps(d)).returncode

        expect("хук: без зарегистрированного шага подагенту в задачу нельзя", write_code("04-results.md") == 2)
        r = run([rt, "start", t, "results-reviewer", "04-results.md"])
        expect("маршрут: шаг зарегистрирован", r.returncode == 0 and "Шаг 1" in r.stdout, r.stdout)
        expect("хук: в артефакт идущего шага можно", write_code("04-results.md") == 0)
        expect("хук: в чужой файл при идущем шаге нельзя", write_code("02-hypotheses.md") == 2)
        open(os.path.join(t, "04-results.md"), "w", encoding="utf-8").write(body)
        open(os.path.join(t, "02-hypotheses.md"), "w", encoding="utf-8").write("чужое\n")
        r = run([rt, "done", t])
        expect("маршрут: чужой файл пойман по хэшу", r.returncode == 1 and "02-hypotheses.md" in r.stdout and "Проверки:" in r.stdout, r.stdout)
        r = run([rt, "ready", t])
        expect("готовность: шаг с ошибками не даёт сдать", r.returncode == 1 and "закрыт с ошибками" in r.stdout, r.stdout)
        os.remove(os.path.join(t, "02-hypotheses.md"))
        r = run([rt, "start", t, "results-reviewer", "04-results.md"])
        open(os.path.join(t, "04-results.md"), "a", encoding="utf-8").write("Дополнение.\n")
        r = run([rt, "done", t])
        expect("маршрут: только свой артефакт — шаг закрыт", r.returncode == 0 and "ок" in r.stdout, r.stdout)
        st = json.load(open(os.path.join(t, "state.json"), encoding="utf-8"))
        st["steps"][0]["status"] = "done"
        open(os.path.join(t, "state.json"), "w", encoding="utf-8").write(json.dumps(st))
        r = run([rt, "ready", t])
        expect("готовность: артефакты и проверки типа на месте", r.returncode == 0, r.stdout)
        r = run([rt, "status", t])
        expect("маршрут: статус для продолжения после обрыва", "Шаг 2 — results-reviewer" in r.stdout and "Обязательные впереди" in r.stdout, r.stdout)

        gate = os.path.join(HERE, "hooks", "step_gate.py")
        tr = os.path.join(proj, "agent.jsonl")
        open(tr, "w", encoding="utf-8").write(json.dumps({"type": "user", "timestamp": "2026-10-18T10:00:00Z",
            "message": {"role": "user", "content": "Сверь результаты, артефакт tasks/rt/04-results.md"}}) + "\n")
        run([rt, "start", t, "results-reviewer", "04-results.md"])
        open(os.path.join(t, "04-results.md"), "w", encoding="utf-8").write("коротко\n")
        ev = {"hook_event_name": "SubagentStop", "cwd": proj, "agent_id": "a2", "agent_type": "results-reviewer",
              "agent_transcript_path": tr, "stop_hook_active": False}
        g = run([gate], json.dumps(ev))
        expect("ворота: артефакт с ошибками возвращается исполнителю", g.returncode == 2 and "04-results.md" in g.stderr, g.stderr)
        ev["stop_hook_active"] = True
        expect("ворота: второй раз подряд не держат", run([gate], json.dumps(ev)).returncode == 0)
        ev["stop_hook_active"] = False
        open(os.path.join(t, "04-results.md"), "w", encoding="utf-8").write(body)
        expect("ворота: исправленный артефакт пропускают", run([gate], json.dumps(ev)).returncode == 0)
    finally:
        shutil.rmtree(proj, ignore_errors=True)


def roles_tests():
    """Описания агентов совпадают с таблицей ролей; хук держит Bash и сеть подагентов."""
    r = run([os.path.join(HERE, "check_size.py")])
    expect("размер: ядро, маршруты, скиллы и загрузка оркестратора на тип в пределах порогов", r.returncode == 0, r.stdout[-800:])
    r = run([os.path.join(HERE, "roles.py"), "--check"])
    expect("роли: описания агентов в .claude/agents совпадают с таблицей", r.returncode == 0, r.stdout)
    proj = tempfile.mkdtemp(prefix="polygon-roles-")
    try:
        open(os.path.join(proj, "AGENTS.md"), "w", encoding="utf-8").write("#\n")
        hook = os.path.join(HERE, "hooks", "guard_writes.py")

        def code(tool, agent_type, command=None, agent_id="a1"):
            d = {"cwd": proj, "tool_name": tool, "tool_input": {"command": command} if command else {}}
            if agent_id:
                d.update(agent_id=agent_id, agent_type=agent_type)
            return run([hook], json.dumps(d)).returncode

        expect("хук: скрипт системы подагенту разрешён", code("Bash", "document-mapper", "python3 scripts/check_map.py tasks/x") == 0)
        expect("хук: python3 -c подагенту запрещён", code("Bash", "document-mapper", "python3 -c 'import os'") == 2)
        expect("хук: запись перенаправлением запрещена", code("Bash", "nostradamus", "cat a > tasks/x/02f.md") == 2)
        expect("хук: чтение с 2>/dev/null разрешено", code("Bash", "nostradamus", "ls tasks 2>/dev/null | head") == 0)
        expect("хук: rm подагенту запрещён", code("Bash", "meaning-review", "rm -rf tasks") == 2)
        expect("хук: curl роли без сети запрещён", code("Bash", "nostradamus", "curl -s https://example.com") == 2)
        expect("хук: curl роли с сетью разрешён", code("Bash", "customer-path", "curl -s https://example.com | trafilatura") == 0)
        expect("хук: WebSearch роли без сети запрещён", code("WebSearch", "meaning-review") == 2)
        expect("хук: WebSearch источнику данных разрешён", code("WebSearch", "market-analyze") == 0)
        expect("хук: агент общего типа сеть не теряет", code("WebSearch", "general-purpose") == 0)
        expect("хук: основная сессия Bash не ограничена", code("Bash", "", "rm -rf x", agent_id=None) == 0)
    finally:
        shutil.rmtree(proj, ignore_errors=True)


def trace_tests():
    """Хук трассы, сводка расхода, цена маршрута и остаток — на выдуманных транскриптах."""
    proj = tempfile.mkdtemp(prefix="polygon-trace-")
    try:
        open(os.path.join(proj, "AGENTS.md"), "w", encoding="utf-8").write("#\n")
        for sk in ("hypothesis-validator", "document-mapper", "nostradamus"):
            os.makedirs(os.path.join(proj, ".claude", "skills", sk))
            open(os.path.join(proj, ".claude", "skills", sk, "SKILL.md"), "w", encoding="utf-8").write("#\n")
        task = os.path.join(proj, "tasks", "trc")
        os.makedirs(task)
        open(os.path.join(task, "log.md"), "w", encoding="utf-8").write("# Лог задачи: trc\n")

        def line(**kw):
            return json.dumps(kw, ensure_ascii=False) + "\n"

        def asst(mid, ts, out, model="model-strong"):
            u = {"input_tokens": 10, "cache_creation_input_tokens": 1000, "cache_read_input_tokens": 50000,
                 "output_tokens": out}
            return line(type="assistant", timestamp=ts, message={"id": mid, "model": model, "usage": u})

        call = ("Прочитай .claude/skills/hypothesis-validator/SKILL.md, режим «отсев идей». "
                "Вход: tasks/trc/02f-forecast.md, ТЗ, nostradamus не передавать.")
        sub = os.path.join(proj, "agent-a1.jsonl")
        open(sub, "w", encoding="utf-8").write(
            line(type="user", timestamp="2026-10-18T10:00:00Z", message={"role": "user", "content": call})
            + asst("m1", "2026-10-18T10:00:30Z", 200) + asst("m1", "2026-10-18T10:00:31Z", 200)
            + asst("m2", "2026-10-18T10:03:00Z", 300))
        hook = os.path.join(HERE, "hooks", "trace.py")
        ev = {"hook_event_name": "SubagentStop", "cwd": proj, "agent_id": "a1", "agent_transcript_path": sub,
              "agent_type": "general-purpose"}
        r = run([hook], json.dumps(ev))
        rows = [json.loads(x) for x in open(os.path.join(task, "trace.jsonl"), encoding="utf-8")]
        rec = rows[0] if rows else {}
        expect("трасса: подагент записан, ответ с одним id посчитан один раз",
               r.returncode == 0 and len(rows) == 1 and rec.get("out") == 500 and rec.get("responses") == 2, str(rows))
        expect("трасса: роль по пути к SKILL.md, режим и фактическая модель",
               rec.get("role") == "hypothesis-validator" and rec.get("mode") == "отсев идей"
               and rec.get("model") == "model-strong" and rec.get("sec") == 180, str(rec))
        run([hook], json.dumps(ev))
        rows = open(os.path.join(task, "trace.jsonl"), encoding="utf-8").read().splitlines()
        expect("трасса: повторное событие того же агента заменяет строку", len(rows) == 1, str(rows))
        expect("трасса: битый вход хука — молча выход 0", run([hook], "не json").returncode == 0)

        main = os.path.join(proj, "main.jsonl")
        open(main, "w", encoding="utf-8").write(
            asst("p0", "2026-10-18T09:00:00Z", 999)
            + line(type="user", timestamp="2026-10-18T09:10:00Z", message={"role": "user", "content": "диспетчер, задача tasks/trc"})
            + asst("p1", "2026-10-18T09:11:00Z", 100)
            + line(type="assistant", timestamp="2026-10-18T09:12:00Z", isSidechain=True,
                   message={"id": "p2", "model": "x", "usage": {"output_tokens": 7777}}))
        run([hook], json.dumps({"hook_event_name": "Stop", "cwd": proj, "session_id": "s1", "transcript_path": main}))
        m = json.load(open(os.path.join(task, "trace-main.json"), encoding="utf-8")).get("s1", {})
        expect("трасса: основная сессия — с первого упоминания задачи и без побочных веток", m.get("out") == 100, str(m))

        ts = os.path.join(HERE, "trace_summary.py")
        r = run([ts, task, "--since", "0"])
        expect("сводка: строка «Расход» за шаг", r.stdout.startswith("Расход: 1 вызов,") and "model-strong" in r.stdout, r.stdout)
        r = run([ts, task])
        expect("сводка: таблица по ролям с основной сессией", "hypothesis-validator · отсев идей" in r.stdout
               and "основная сессия" in r.stdout, r.stdout)
        expect("сводка: вызов подагента до согласования ТЗ виден", "до согласования ТЗ — 1 вызов" in r.stdout, r.stdout)
        open(os.path.join(task, "00-tz.md"), "w", encoding="utf-8").write("ТЗ\nСОГЛАСОВАНО: да\n")
        run([hook], json.dumps(ev))
        r = run([ts, task])
        expect("сводка: после согласования предупреждения нет", "до согласования" not in r.stdout, r.stdout)

        cst = os.path.join(proj, "tasks", "cst")
        os.makedirs(cst)
        open(os.path.join(cst, "sources.csv"), "w", encoding="utf-8").write(
            "id,kind\n" + "".join("F-%03d,context\n" % i for i in range(14)) + "F-100,interview\nF-101,interview\nF-102,interview\nF-200,web\n")
        open(os.path.join(cst, "00d-map.md"), "w", encoding="utf-8").write("#\n")
        tz = "ТИР:        Tier 1 — и бюджет шагов: 8\nТИП ВЫХОДА: гипотезы\nРЕЖИМ:      обычный\n            пробный прогон: нет\n"
        open(os.path.join(cst, "00-tz.md"), "w", encoding="utf-8").write(tz)
        ce = os.path.join(HERE, "cost_estimate.py")
        r = run([ce, cst, "--detail"])
        expect("цена: вызовы по структуре маршрута — свободная часть 10, резерв 26, потолок 47",
               r.returncode == 0 and "~36 вызовов" in r.stdout and "резерв 26" in r.stdout and "потолок 47" in r.stdout, r.stdout)
        expect("цена: токены по трассе прошлой задачи, основная сессия оценена",
               "по 1 прогону" in r.stdout and "основная сессия — ещё" in r.stdout, r.stdout)
        open(os.path.join(cst, "00-tz.md"), "w", encoding="utf-8").write(tz.replace("ТИП ВЫХОДА: гипотезы", "ТИП ВЫХОДА: разбор / гипотезы"))
        open(os.path.join(cst, "00-tz.md"), "w", encoding="utf-8").write(tz + "            новые идеи: да\n")
        r = run([ce, cst])
        expect("цена: с заказом новых идей — плюс вызов на отсев", "~37 вызовов" in r.stdout and "резерв 27" in r.stdout, r.stdout)
        open(os.path.join(cst, "00-tz.md"), "w", encoding="utf-8").write(tz.replace("ТИП ВЫХОДА: гипотезы", "ТИП ВЫХОДА: разбор / гипотезы"))
        r = run([ce, cst])
        expect("цена: тип выхода не выбран — отказ, а не догадка", r.returncode == 1 and "ТИП ВЫХОДА" in r.stdout, r.stdout)
        open(os.path.join(cst, "00-tz.md"), "w", encoding="utf-8").write(tz)
        price = run([ce, cst]).stdout
        open(os.path.join(cst, "00-tz.md"), "w", encoding="utf-8").write(tz + price)
        open(os.path.join(cst, "trace.jsonl"), "w", encoding="utf-8").write(
            "".join(line(ts=1, agent_id="d%d" % i, role="document-mapper", out=10) for i in range(3)))
        r = run([ce, cst, "--left"])
        expect("остаток: потрачено 3, резерв впереди 23, свободных 21",
               "Потрачено: 3 вызова" in r.stdout and "резерв впереди 23" in r.stdout and "до потолка 21" in r.stdout, r.stdout + price)
        r = run([os.path.join(HERE, "trace_summary.py"), cst, "--save"])
        c = json.load(open(os.path.join(cst, "checks", "cost.json"), encoding="utf-8"))
        expect("сдача: cost.json с оценкой и фактом", c.get("estimate_calls") == 36 and c.get("calls") == 3
               and "из ~36" in r.stdout, r.stdout)
        open(os.path.join(cst, "01-review.md"), "w", encoding="utf-8").write("# Разбор\n\n" + "Разрыв логики между первым запуском и использованием. " * 10 + "\n")
        r = run([os.path.join(HERE, "check_step.py"), cst, "01-review.md", "--since", "0"])
        expect("шаг: под строкой проверок — строка «Расход»", "\nРасход: 3 вызова" in r.stdout, r.stdout)
        r = run([os.path.join(HERE, "trace_summary.py"), "--version"])
        expect("версия системы для шапки лога", r.stdout.startswith("Система: "), r.stdout)
    finally:
        shutil.rmtree(proj, ignore_errors=True)


def forecast_tests(root):
    cf = os.path.join(HERE, "check_forecast.py")
    d = os.path.join(root, "tasks", "fct")
    os.makedirs(d)
    open(os.path.join(d, "00-tz.md"), "w", encoding="utf-8").write(
        "ТЗ\n\nGAP:\n  1. Как разделить клиентов для рассылок [ключевой] {ответ: контекст}\n  2. Каким признаком определить группу [ключевой] {ответ: данные}\n"
        "  3. Что делают другие сервисы {ответ: веб}\n\nНА ВХОДЕ: идея\nРЕЖИМ:      обычный\n            новые идеи: да\n")
    sec = ("## GAP %d — вопрос\nЛучшая версия [оценка]: делить по тому, как часто клиент выводит деньги\n"
           "Уверенность: низкая — опор: 1\nНа чём стоит:\n  - рассуждение: так говорили в звонках\nАльтернативы:\n  - делить по стажу в банке\n"
           "Что различит: доля повторных выводов за 90 дней\nСледующий шаг: менеджер — 10 звонков — неделя — бесплатно\n"
           "Если версия неверна: оставить текст по событию\n\n")
    good = ("РАМКА\nВопрос человека: как разделить клиентов\nНужная форма ответа: схема на всю базу\nЧто построено: пары групп\n"
            "Совпадает: нет — пары не покрывают базу\nЧерновик ответа нужной формы: три части — регулярные выводы, разовый всплеск, без событий [оценка]\n\n"
            + sec % 1 + sec % 2 +
            "")
    idea = ("%d. Идея %d\n   Суть: делить по тому, кто проводит платежи\n   Почему может сработать: рассуждение: решает бухгалтер\n"
            "   Не повторяет: срок в банке — другая ось\n   Уточнит: вопрос «кто проводит платежи» в интерфейсе\n"
            "   Первый шаг: 10 звонков\n   На чём: новый сбор: 10 звонков клиентам\n   Убьёт: везде платит владелец\n")
    versions = "РЕЖИМ: только версии\n\n" + good
    good = "РЕЖИМ: версии и новые идеи\n\n## НОВЫЕ ИДЕИ\n" + "".join(idea % (i, i) for i in range(1, 6)) + "\n" + good
    w = lambda t: open(os.path.join(d, "02f-forecast.md"), "w", encoding="utf-8").write(t)
    r = run([cf, d])
    expect("нострадамус: нет файла — проверять нечего", r.returncode == 0, r.stdout)
    w(good)
    r = run([cf, d])
    expect("нострадамус: полная форма проходит", r.returncode == 0, r.stdout)
    w(good.replace(sec % 2, ""))
    r = run([cf, d])
    expect("нострадамус: ключевой вопрос без раздела пойман", r.returncode == 1 and "GAP 2" in r.stdout, r.stdout)
    w(good.replace("Лучшая версия [оценка]: делить по тому, как часто клиент выводит деньги\n", "Лучшая версия [оценка]: нет данных, нужна выгрузка\n", 1))
    r = run([cf, d])
    expect("нострадамус: «нет данных» вместо версии пойман", r.returncode == 1 and "отказ" in r.stdout, r.stdout)
    w(good.replace("Лучшая версия [оценка]:", "Лучшая версия:", 1))
    r = run([cf, d])
    expect("нострадамус: версия без пометки «оценка» поймана", r.returncode == 1 and "оценка" in r.stdout, r.stdout)
    w(good.replace("Следующий шаг: менеджер — 10 звонков — неделя — бесплатно\n", "Следующий шаг:\n", 1))
    r = run([cf, d])
    expect("нострадамус: пустой следующий шаг пойман", r.returncode == 1 and "Следующий шаг" in r.stdout, r.stdout)
    w(good.replace("Черновик ответа нужной формы: три части — регулярные выводы, разовый всплеск, без событий [оценка]\n", ""))
    r = run([cf, d])
    expect("нострадамус: рамка не совпала без черновика — поймано", r.returncode == 1 and "черновик" in r.stdout, r.stdout)
    w(good.replace("   Уточнит: вопрос «кто проводит платежи» в интерфейсе\n", "", 1))
    r = run([cf, d])
    expect("нострадамус: идея без «уточнит» поймана", r.returncode == 1 and "идея 1" in r.stdout and "уточнит" in r.stdout, r.stdout)
    w(good.replace("   Не повторяет: срок в банке — другая ось\n", "", 1))
    r = run([cf, d])
    expect("нострадамус: идея без «не повторяет» поймана", r.returncode == 1 and "не повторяет" in r.stdout, r.stdout)
    w(good.replace(idea % (5, 5), ""))
    r = run([cf, d])
    expect("нострадамус: меньше пяти новых идей — поймано", r.returncode == 1 and "идей 4" in r.stdout, r.stdout)
    w(good.replace("   На чём: новый сбор: 10 звонков клиентам\n", "", 1))
    r = run([cf, d])
    expect("нострадамус: идея без «На чём» поймана", r.returncode == 1 and "На чём" in r.stdout, r.stdout)
    w(good.replace("   На чём: новый сбор: 10 звонков клиентам\n", "   На чём: реестр звонков, поле формы\n", 1))
    r = run([cf, d])
    expect("нострадамус: «На чём» без поля из источника и без нового сбора — поймано", r.returncode == 1 and "идея 1" in r.stdout, r.stdout)
    w(good.replace("   На чём: новый сбор: 10 звонков клиентам\n", "   На чём: «Сегмент» [F-007]\n", 1))
    r = run([cf, d])
    expect("нострадамус: «На чём» с полем из источника проходит", r.returncode == 0, r.stdout)
    w(versions)
    r = run([cf, d])
    expect("нострадамус: новые идеи заказаны, а режим «только версии» — поймано", r.returncode == 1 and "заказаны" in r.stdout, r.stdout)
    tz = open(os.path.join(d, "00-tz.md"), encoding="utf-8").read()
    open(os.path.join(d, "00-tz.md"), "w", encoding="utf-8").write(tz.replace("новые идеи: да", "новые идеи: нет"))
    r = run([cf, d])
    expect("нострадамус: «только версии» без заказа проходит", r.returncode == 0, r.stdout)
    w(good)
    r = run([cf, d])
    expect("нострадамус: новые идеи без заказа и без сплошного «сузить» — пойманы", r.returncode == 1 and "не заказаны" in r.stdout, r.stdout)
    open(os.path.join(d, "02c-validation.md"), "w", encoding="utf-8").write(
        "ГИПОТЕЗА 1 — а\nВердикт:    сузить\n\nГИПОТЕЗА 2 — б\nВердикт:    не держится\n")
    r = run([cf, d])
    expect("нострадамус: все вердикты «сузить / не держится» — новые идеи обязательны и проходят", r.returncode == 0, r.stdout)
    w(versions)
    r = run([cf, d])
    expect("нострадамус: все «сузить», а режим «только версии» — поймано", r.returncode == 1 and "сузить" in r.stdout, r.stdout)
    open(os.path.join(d, "02d-validation2.md"), "w", encoding="utf-8").write("ГИПОТЕЗА 1 — а\nВердикт:    держится на бумаге\n")
    r = run([cf, d])
    expect("нострадамус: условие берётся по второму проходу проверки", r.returncode == 0, r.stdout)


def rehearsal_tests(root):
    cr = os.path.join(HERE, "check_rehearsal.py")
    d = os.path.join(root, "tasks", "rhs")
    os.makedirs(d)
    row = "| %d | новые клиенты, по дате открытия | «вот что проверяет банк» | пуш, CRM | переходы за 14 дней | ≥20%% | <10%% | 6 недель | берём ли деление |\n"
    backlog = ("# Бэклог\n\n| № | Кому и как найти в данных | Что говорим | Где и кто | Метрика | Успех | Отсечение | Срок и цена | Что решит |\n"
               "| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n" + row % 1 + row % 2)
    open(os.path.join(d, "03-backlog.md"), "w", encoding="utf-8").write(backlog)
    reh = ("# Пробный прогон\n\n## СЛЕДСТВИЯ\n\n### Для эксперимента\nСтрока 1 — статус: как есть\n  Почему: дефектов нет\n"
           "Строка 2 — статус: не запускать: ветки отличаются двумя вещами сразу\n  Правка: убрать пример из ветки А\n\n"
           "### Для решения\n- первым идёт строка 1, строка 2 после переделки ветки\n\n"
           "### Что подсказали персоны\n- новички путают уровень и лимит [синтетика] — проверит: 5 пересказов\n")
    w = lambda t: open(os.path.join(d, "03c-rehearsal.md"), "w", encoding="utf-8").write(t)
    r = run([cr, d])
    expect("пробный прогон: нет файла — проверять нечего", r.returncode == 0, r.stdout)
    w(reh)
    r = run([cr, d, "--rehearsal-only"])
    expect("пробный прогон: следствия по всем строкам проходят", r.returncode == 0, r.stdout)
    w(reh.replace("Строка 1 — статус: как есть\n  Почему: дефектов нет\n", ""))
    r = run([cr, d, "--rehearsal-only"])
    expect("пробный прогон: строка бэклога без статуса поймана", r.returncode == 1 and "Строка 1" in r.stdout, r.stdout)
    w(reh.split("## СЛЕДСТВИЯ")[0])
    r = run([cr, d, "--rehearsal-only"])
    expect("пробный прогон без раздела «СЛЕДСТВИЯ» пойман", r.returncode == 1 and "СЛЕДСТВИЯ" in r.stdout, r.stdout)
    w(reh.replace("- первым идёт строка 1, строка 2 после переделки ветки\n", ""))
    r = run([cr, d, "--rehearsal-only"])
    expect("пробный прогон: пустое «Для решения» поймано", r.returncode == 1 and "Для решения" in r.stdout, r.stdout)
    w(reh)
    r = run([cr, d])
    expect("пробный прогон: следствие не применено в бэклоге — поймано", r.returncode == 1 and "ПО ПРОБНОМУ ПРОГОНУ" in r.stdout, r.stdout)
    open(os.path.join(d, "03-backlog.md"), "w", encoding="utf-8").write(backlog + "\nПО ПРОБНОМУ ПРОГОНУ\nСтрока 2 — применено: ветка А без примера; критерии не менялись\n")
    r = run([cr, d])
    expect("пробный прогон: ответ на каждое следствие проходит", r.returncode == 0, r.stdout)
    open(os.path.join(d, "03-backlog.md"), "w", encoding="utf-8").write(backlog + "\nПО ПРОБНОМУ ПРОГОНУ\nСтрока 2 — отклонено:\n")
    r = run([cr, d])
    expect("пробный прогон: «отклонено» без причины не засчитано", r.returncode == 1 and "Строка 2" in r.stdout, r.stdout)


def ideas_tests(root):
    ci = os.path.join(HERE, "check_ideas.py")
    d = os.path.join(root, "tasks", "ids")
    os.makedirs(d)
    open(os.path.join(d, "02f-forecast.md"), "w", encoding="utf-8").write(
        "## НОВЫЕ ИДЕИ\n1. Писать бухгалтеру\n   Суть: …\n2. Налоговый календарь\n   Суть: …\n3. Кнопка «это…»\n   Суть: …\n\nРАМКА\nСовпадает: да\n")
    blk = {1: "Идея 1 — писать бухгалтеру\nВердикт: кажется валидной\nУбивает: нет\nВозражения: «бухгалтер не заходит в банк» [F-003] — ослабляет\nНовая: да\n"
              "Первый шаг различает: да — поддержит: треть звонков с бухгалтером; убьёт: ни одного\nПервый шаг выполним: да — поле роли в реестре\nОдин источник: нет\n"
              "Данные для следующего раунда: роль пользователя в интернет-банке\n\n",
           2: "Идея 2 — налоговый календарь\nВердикт: переделать первый шаг\nУбивает: нет\nВозражения: не найдено — искал: исследование ценности, звонки\nНовая: да\n"
              "Первый шаг различает: нет — нужен разбор дат уплаты против фактора\nПервый шаг выполним: нет — в реестре нет дат\nОдин источник: нет\nДанные для следующего раунда: даты налоговых платежей\n\n",
           3: "Идея 3 — кнопка\nВердикт: снять\nУбивает: «клиенты не хотят ничего заполнять сами» [F-002] — прямо против\nВозражения: не найдено — искал: звонки\nНовая: да\n"
              "Первый шаг различает: да\nОдин источник: нет\nДанные для следующего раунда: —\n\n"}
    w = lambda t: open(os.path.join(d, "02g-ideas-check.md"), "w", encoding="utf-8").write("## ОТСЕВ ИДЕЙ\n" + t)
    r = run([ci, d])
    expect("отсев идей: нет файла — проверять нечего", r.returncode == 0, r.stdout)
    w("".join(blk.values()))
    r = run([ci, d])
    expect("отсев идей: полный отсев проходит", r.returncode == 0, r.stdout)
    w(blk[1] + blk[3])
    r = run([ci, d])
    expect("отсев идей: идея без вердикта поймана", r.returncode == 1 and "идея 2" in r.stdout, r.stdout)
    w(blk[1].replace("Данные для следующего раунда: роль пользователя в интернет-банке\n", "") + blk[2] + blk[3])
    r = run([ci, d])
    expect("отсев идей: живая идея без данных для следующего раунда поймана", r.returncode == 1 and "идея 1" in r.stdout, r.stdout)
    w(blk[1] + blk[2] + blk[3].replace("«клиенты не хотят ничего заполнять сами» [F-002] — прямо против", "нет опор"))
    r = run([ci, d])
    expect("отсев идей: снята за «нет опор» — поймано", r.returncode == 1 and "идея 3" in r.stdout, r.stdout)
    w(blk[1].replace("Возражения: «бухгалтер не заходит в банк» [F-003] — ослабляет\n", "") + blk[2] + blk[3])
    r = run([ci, d])
    expect("отсев идей: нет поля «Возражения» — поймано", r.returncode == 1 and "возражения не указаны" in r.stdout, r.stdout)
    w(blk[1] + blk[2].replace("Вердикт: переделать первый шаг", "Вердикт: кажется валидной") + blk[3])
    r = run([ci, d])
    expect("отсев идей: невыполнимый шаг при «кажется валидной» — пойман", r.returncode == 1 and "идея 2" in r.stdout and "невыполним" in r.stdout, r.stdout)
    w(blk[1].replace("Возражения: «бухгалтер не заходит в банк» [F-003] — ослабляет", "Возражения: не найдено — искал: звонки") + blk[2] + blk[3])
    r = run([ci, d])
    expect("отсев идей: возражений не найдено ни у одной — предупреждение по полю «Возражения»", r.returncode == 0 and "ни у одной" in r.stdout, r.stdout)


def knowledge_tests(root):
    ck = os.path.join(HERE, "check_knowledge.py")
    d = os.path.join(root, "tasks", "knw")
    os.makedirs(d)
    open(os.path.join(d, "00-tz.md"), "w", encoding="utf-8").write("ТЗ\n\nGAP:\n  1. Почему бросают пробный период\n  2. Кто решает о покупке\n\nНА ВХОДЕ: идея\n")
    open(os.path.join(d, "sources.csv"), "w", encoding="utf-8").write(
        "id,kind,location\nF-001,context,context/a.md\nF-002,context,context/b.md\nF-003,web,https://x.ru\n")
    good = ("1. ПОКРЫТИЕ ФАЙЛОВ\n\n| Файл | Тип | Прочитан | К каким пунктам GAP относится | Фрагментов взято |\n| --- | --- | --- | --- | --- |\n"
            "| F-001 · интервью | прямая речь клиента | целиком | 1 | 4 |\n| F-002 · бриф | утверждение команды | целиком | — не относится: описание тарифов | 0 |\n\n"
            "2. ПО ПУНКТАМ GAP\n\nGAP 1 — Почему бросают пробный период\nУже известно:\n  - «не нашли, где настроить отчёт» [F-001]\nЧего нет:\n  - доли бросивших по причинам\n\n"
            "GAP 2 — Кто решает о покупке\nУже известно:\n  - нет\nЧего нет:\n  - кто подписывает оплату в малых командах\n")
    open(os.path.join(d, "00k-knowledge.md"), "w", encoding="utf-8").write(good)
    r = run([ck, d])
    expect("материалы: полное покрытие проходит", r.returncode == 0, r.stdout)
    open(os.path.join(d, "00k-knowledge.md"), "w", encoding="utf-8").write(good.replace("| F-002 · бриф | утверждение команды | целиком | — не относится: описание тарифов | 0 |\n", ""))
    r = run([ck, d])
    expect("материалы: пропущенный файл контекста пойман", r.returncode == 1 and "F-002" in r.stdout, r.stdout)
    open(os.path.join(d, "00k-knowledge.md"), "w", encoding="utf-8").write(good.replace("Чего нет:\n  - кто подписывает оплату в малых командах\n", "Чего нет:\n"))
    r = run([ck, d])
    expect("материалы: пустое «Чего нет» поймано", r.returncode == 1 and "GAP 2" in r.stdout, r.stdout)


def polygon_tests(root):
    import json as _json
    pg = os.path.join(HERE, "polygon.py")
    d = os.path.join(root, "pg")
    os.makedirs(d)
    r = run([pg, "make", "--seed", "1", "--reports", os.path.join(d, "r"), "--key-out", os.path.join(d, "key.json")])
    expect("полигон: отчёты генерируются", r.returncode == 0 and len(os.listdir(os.path.join(d, "r"))) == 11, r.stdout + r.stderr)
    expect("полигон: ключ вне папки отчётов", not os.path.exists(os.path.join(d, "r", "key.json")))
    key = _json.load(open(os.path.join(d, "key.json"), encoding="utf-8"))
    r2 = run([pg, "make", "--seed", "1", "--reports", os.path.join(d, "r2"), "--key-out", os.path.join(d, "key2.json")])
    expect("полигон: тот же seed даёт тот же ключ", _json.load(open(os.path.join(d, "key2.json"), encoding="utf-8")) == key, r2.stderr)
    perfect = "\n".join("%s | поле=%s | исход=%s | флаги=%s" % (
        fid, v["поле"] or "—", v["исход"][0], ",".join(v["флаги"]) or "—") for fid, v in sorted(key.items()))
    open(os.path.join(d, "good.md"), "w", encoding="utf-8").write("СВЕРКА\n" + perfect + "\n")
    s = run([pg, "score", "--key", os.path.join(d, "key.json"), "--answer", os.path.join(d, "good.md"), "--min", "0.9"])
    expect("полигон: точный ответ получает 100% по исходу", s.returncode == 0 and "100%" in s.stdout, s.stdout + s.stderr)
    bad = perfect.replace("исход=", "исход=нет_данных_", 3)
    open(os.path.join(d, "bad.md"), "w", encoding="utf-8").write(bad + "\n")
    s2 = run([pg, "score", "--key", os.path.join(d, "key.json"), "--answer", os.path.join(d, "bad.md"), "--min", "0.9"])
    expect("полигон: ошибки в ответе снижают точность и дают код 1", s2.returncode == 1 and "МИМО" in s2.stdout, s2.stdout)
    open(os.path.join(d, "empty.md"), "w", encoding="utf-8").write("нет блока\n")
    s3 = run([pg, "score", "--key", os.path.join(d, "key.json"), "--answer", os.path.join(d, "empty.md")])
    expect("полигон: пустой ответ — ноль, а не падение", s3.returncode == 0 and "0%" in s3.stdout, s3.stdout + s3.stderr)


def sensitivity_tests(root):
    sv = os.path.join(HERE, "sensitivity.py")
    an = os.path.join(HERE, "add_number.py")
    d = os.path.join(root, "tasks", "sens")
    os.makedirs(d)
    for key, val in (("total", "4200"), ("f1", "0.325"), ("f2", "0.65")):
        run([an, "--task", d, "--kind", "assumption", "--key", key, "--what", key, "--value", val, "--unit", "шт", "--note", "тест"])
    r = run([sv, "--task", d, "--formula", "N-001 * N-002 * N-003", "--range", "N-002=0.25..0.40",
             "--range", "N-003=0.55..0.75", "--threshold", "800"])
    expect("чувствительность: параметры упорядочены по размаху", r.returncode == 0 and "N-002 > N-003" in r.stdout, r.stdout + r.stderr)
    expect("чувствительность: итог при базовых значениях посчитан", "887.25" in r.stdout, r.stdout)
    expect("чувствительность: порог пересекается внутри диапазона", "вывод меняется внутри диапазона" in r.stdout, r.stdout)
    expect("чувствительность: параметра нет в реестре — ошибка",
           run([sv, "--task", d, "--formula", "N-001 * N-002", "--range", "N-009=1..2"]).returncode != 0)
    expect("чувствительность: неверная формула — ошибка, а не падение",
           "формула не считается" in run([sv, "--task", d, "--formula", "N-001 / 0", "--range", "N-002=1..2"]).stderr)


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
    mh = os.path.join(root, "context", "page.mhtml")
    open(mh, "w", encoding="utf-8").write(
        "From: <Saved by test>\nMIME-Version: 1.0\nContent-Type: multipart/related; boundary=\"BND\"\n\n--BND\n"
        "Content-Type: text/html; charset=utf-8\nContent-Transfer-Encoding: quoted-printable\n\n"
        "<html><body><p>=D0=9F=D1=80=D0=BE=D0=B1=D0=BD=D0=B0=D1=8F =D1=81=D1=82=D1=80=D0=B0=D0=BD=D0=B8=D1=86=D0=B0 =D0=BF=D1=80=D0=BE =D1=82=D0=B0=D1=80=D0=B8=D1=84: =D1=82=D0=B5=D0=BA=D1=81=D1=82 =D0=BD=D0=B0=D0=BF=D0=B8=D1=81=D0=B0=D0=BD =D1=82=D0=BE=D0=BB=D1=8C=D0=BA=D0=BE =D0=B4=D0=BB=D1=8F =D0=BF=D1=80=D0=BE=D0=B2=D0=B5=D1=80=D0=BA=D0=B8 =D1=87=D1=82=D0=B5=D0=BD=D0=B8=D1=8F =D1=81=D0=BE=D1=85=D1=80=D0=B0=D0=BD=D1=91=D0=BD=D0=BD=D1=8B=D1=85 =D1=81=D1=82=D1=80=D0=B0=D0=BD=D0=B8=D1=86.</p></body></html>\n--BND--\n")
    r = run([add, "--task", d, "--kind", "context", "--location", mh, "--ctx-type", "result"])
    raw = open(os.path.join(d, "sources", "raw", r.stdout.strip() + ".txt"), encoding="utf-8").read() if r.returncode == 0 else ""
    expect(".mhtml: кириллица декодирована, теги убраны", "Пробная страница про тариф" in raw and "=D0" not in raw and "<p>" not in raw, r.stderr + raw)
    sx = os.path.join(root, "context", "secret.txt")
    open(sx, "w", encoding="utf-8").write("Файл с расчётом.\nпароль: abc12345\n")
    r = run([add, "--task", d, "--kind", "context", "--location", sx, "--ctx-type", "claim"])
    expect("пароль в тексте: предупреждение с номером строки, без значения",
           r.returncode == 0 and "строках 2" in r.stderr and "abc12345" not in r.stderr, r.stderr)
    e = run([os.path.join(HERE, "check_env.py")])
    expect("check_env печатает отчёт", e.returncode == 0 and "Чтение PDF с текстом" in e.stdout, e.stdout + e.stderr)


def map_tests(root):
    import json as _json
    md = os.path.join(HERE, "map_docs.py")
    ck = os.path.join(HERE, "check_map.py")
    d = os.path.join(root, "tasks", "mapd")
    os.makedirs(os.path.join(d, "sources", "raw"))
    open(os.path.join(d, "sources.csv"), "w", encoding="utf-8").write(
        "id,kind,location,read\nF-001,context,context/a.md,full\nF-002,interview,context/b.md,full\nF-003,web,https://x.ru,full\n")
    raw1 = ("Тест бонуса в сегменте малых команд\nГруппа A: 331 / 1733 = 19.09%\nГруппа B: 337 / 1757 = 19.18%\n"
            "p-value 0.95, различий нет\nБонус начисляется баллами программы лояльности\n"
            "Ограничение: мощность теста низкая\nКонверсия 4,5% против 3,9%\nОтток 12% за 2 недели\n"
            "В тесте 120 клиентов\n<table><tr><td>Группа C</td><td>9 / 5 264 = 0.17%</td></tr></table>\n")
    open(os.path.join(d, "sources", "raw", "F-001.txt"), "w", encoding="utf-8").write(raw1)
    open(os.path.join(d, "sources", "raw", "F-002.txt"), "w", encoding="utf-8").write(
        "Респондент 1: Мы платим по счёту, сервис не берём.\nИнтервьюер: Почему?\n")
    r = run([md, d])
    expect("карта: строится для context и interview, web пропущен", r.returncode == 0 and "документов 2" in r.stdout, r.stdout + r.stderr)
    data = _json.load(open(os.path.join(d, "map", "F-001.json"), encoding="utf-8"))
    byt = {l["text"]: l["tags"] for l in data["lines"]}
    expect("карта: теги число, продукт, срез", "число" in byt.get("Группа A: 331 / 1733 = 19.09%", [])
           and "продукт" in byt.get("Бонус начисляется баллами программы лояльности", [])
           and "срез" in byt.get("Тест бонуса в сегменте малых команд", []), str(byt))
    expect("карта: строка HTML-таблицы собрана по ячейкам", "Группа C | 9 / 5 264 = 0.17%" in byt, str(list(byt)))
    r = run([md, d])
    expect("карта: неизменившийся документ берётся из кэша", "из кэша 2" in r.stdout, r.stdout)
    terms = os.path.join(root, "map-terms.txt")
    open(terms, "w", encoding="utf-8").write("продукт: стрелк\nсрез: дальн\\w* клиент\\w*\nмусор без двоеточия\n")
    probe = ("import sys; sys.path.insert(0, %r); import map_docs as m; "
             "print(m.tags('Стрелка включена у дальних клиентов'), m.tags('Стрелка включена'))" % HERE)
    env = dict(os.environ, MAP_TERMS=terms)
    r = subprocess.run([PY, "-c", probe], capture_output=True, text=True, env=env)
    r0 = subprocess.run([PY, "-c", probe], capture_output=True, text=True, env=dict(os.environ, MAP_TERMS=terms + ".нет"))
    expect("карта: слова своего продукта из локального .map-terms размечаются, без файла — нет",
           "'срез', 'продукт'" in r.stdout and "['продукт']" in r.stdout and "[] []" in r0.stdout, r.stdout + r.stderr + r0.stdout)
    ms = os.path.join(HERE, "map_summary.py")
    r = run([ms, d])
    expect("сводка карты: строка на документ, срезы и строки про продукт без модели",
           r.returncode == 0 and "| F-001 | a.md |" in r.stdout and "- сегменте — 1" in r.stdout and "F-001 L" in r.stdout
           and "Бонус начисляется баллами" in r.stdout and os.path.exists(os.path.join(d, "map", "summary.md")), r.stdout)
    expect("сводка карты: прочитанные целиком не попадают в «не читается»", "## Не читается или частично\n- нет" in r.stdout, r.stdout)
    num = [l["n"] for l in data["lines"] if "число" in l["tags"]]
    n = {l["text"]: l["n"] for l in data["lines"]}
    la, lb = n["Группа A: 331 / 1733 = 19.09%"], n["Бонус начисляется баллами программы лояльности"]
    lr = n["Респондент 1: Мы платим по счёту, сервис не берём."] if "Респондент 1: Мы платим по счёту, сервис не берём." in n else 1
    d2 = os.path.join(d, "..")
    f2 = _json.load(open(os.path.join(d, "map", "F-002.json"), encoding="utf-8"))["lines"][0]["n"]
    cover = ", ".join("L%d" % x for x in num)

    def dossier(num_refs=cover, key="L%d: «Бонус начисляется баллами программы лояльности»" % lb, extra="", f2status="прочитан",
                drop_field=None, second=True):
        b1 = ("### F-001 — тест бонуса\n- Тип: отчёт о тесте\n- Про кого: сегмент малых команд, L1\n- Сколько: 120 клиентов, L%d\n"
              "- Что измерено: результат теста\n- Дата: не указана\n- Выводы документа:\n  - различий нет, L%d\n"
              "- Числа и срезы: %s\n- Про продукт: бонус баллами, L%d\n- Риски и ограничения команды: мощность низкая\n"
              "- Ключевая цитата: %s\n- Сверх схемы: нет\n- Отброшено: нет\n- Статус чтения: прочитан\n%s" % (
                  n["В тесте 120 клиентов"], n["p-value 0.95, различий нет"], num_refs, lb, key, extra))
        if drop_field:
            b1 = "\n".join(x for x in b1.split("\n") if not x.startswith("- " + drop_field + ":")) + "\n"
        b2 = ("### F-002 — интервью\n- Тип: интервью\n- Про кого: респондент\n- Сколько: 1\n- Что измерено: слова\n"
              "- Дата: не указана\n- Выводы документа: платит по счёту, L%d\n- Числа и срезы: в документе нет\n"
              "- Про продукт: нет\n- Риски и ограничения команды: нет\n- Ключевая цитата: L%d: «Мы платим по счёту»\n"
              "- Сверх схемы: нет\n- Отброшено: нет\n- Статус чтения: %s\n" % (f2, f2, f2status)) if second else ""
        open(os.path.join(d, "00d-map.md"), "w", encoding="utf-8").write(b1 + "\n" + b2)

    dossier()
    r = run([ck, d])
    expect("досье: верное проходит", r.returncode == 0, r.stdout)
    dossier(second=False)
    r = run([ck, d])
    expect("досье: пропущенный документ пойман", r.returncode == 1 and "F-002" in r.stdout, r.stdout)
    dossier(key="L%d: «Кешбэк начисляется рублями на счёт»" % lb)
    r = run([ck, d])
    expect("досье: цитата не из строки поймана", r.returncode == 1 and "не найдена" in r.stdout, r.stdout)
    dossier(key="«Бонус начисляется баллами программы лояльности»")
    r = run([ck, d])
    expect("досье: цитата без адреса строки поймана", r.returncode == 1 and "без адреса" in r.stdout, r.stdout)
    dossier(key="L999: «Бонус начисляется баллами программы лояльности»")
    r = run([ck, d])
    expect("досье: несуществующая строка поймана", r.returncode == 1 and "нет строки" in r.stdout, r.stdout)
    dossier(drop_field="Про продукт")
    r = run([ck, d])
    expect("досье: пропущенное поле поймано", r.returncode == 1 and "нет поля" in r.stdout and "Про продукт" in r.stdout, r.stdout)
    dossier(extra="- Влияние: Г=да\n")
    r = run([ck, d])
    expect("досье: оценка важности запрещена", r.returncode == 1 and "Влияние" in r.stdout, r.stdout)
    dossier(num_refs="L%d" % la)
    r = run([ck, d])
    expect("досье: неучтённые числа пойманы", r.returncode == 1 and "не учтено" in r.stdout, r.stdout)
    dossier(num_refs="L%d" % la, extra="")
    txt = open(os.path.join(d, "00d-map.md"), encoding="utf-8").read().replace("- Отброшено: нет\n- Статус чтения: прочитан\n\n### F-002",
                                                                              "- Отброшено: L1-L%d (оговорки)\n- Статус чтения: прочитан\n\n### F-002" % max(num + [1]), 1)
    open(os.path.join(d, "00d-map.md"), "w", encoding="utf-8").write(txt)
    r = run([ck, d])
    expect("досье: «Отброшено» закрывает числа", r.returncode == 0, r.stdout)
    open(os.path.join(d, "sources", "raw", "F-001.txt"), "a", encoding="utf-8").write("Группа A: 331 / 1733 = 19.09%\nГруппа B: 337 / 1757 = 19.18%\n")
    run([md, d, "--force"])
    dd = _json.load(open(os.path.join(d, "map", "F-001.json"), encoding="utf-8"))
    n = {}
    for l in dd["lines"]:
        n.setdefault(l["text"], l["n"])
    cover = ", ".join("L%d" % x for x in sorted(set(n[l["text"]] for l in dd["lines"] if "число" in l["tags"])))
    dossier(num_refs=cover)
    r = run([ck, d])
    expect("досье: дубль блока считается учтённым", r.returncode == 0, r.stdout)
    dossier(key="L%d: «Группа A: 331 / 1733 = 19.09%%»" % la)
    r = run([ck, d])
    expect("досье: ключевая цитата-строка с числами — предупреждение, не ошибка", r.returncode == 0, r.stdout)
    dossier(f2status="не читается")
    r = run([ck, d])
    expect("досье: «не читается» принимается", r.returncode == 0, r.stdout)


def model_tests(root):
    md = os.path.join(HERE, "map_docs.py")
    bm = os.path.join(HERE, "build_model.py")
    ri = os.path.join(HERE, "rank_impact.py")
    cc = os.path.join(HERE, "check_chain.py")
    cr = os.path.join(HERE, "check_rank.py")
    d = os.path.join(root, "tasks", "mdl")
    os.makedirs(os.path.join(d, "sources", "raw"))
    open(os.path.join(d, "sources.csv"), "w", encoding="utf-8").write(
        "id,kind,location,read,root\nF-001,context,context/a.md,full,\nF-002,interview,context/b.md,full,\nF-003,context,context/c.md,full,\n")
    open(os.path.join(d, "sources", "raw", "F-001.txt"), "w", encoding="utf-8").write(
        "Тест бонуса в сегменте малых команд\nГруппа A: 331 / 1733 = 19.09%\nГруппа B: 337 / 1757 = 19.18%\n"
        "Размер теста 5264 клиента\nБонус начисляется баллами программы лояльности\n")
    open(os.path.join(d, "sources", "raw", "F-002.txt"), "w", encoding="utf-8").write("Респондент 1: платим по счёту, сервис не берём\n")
    open(os.path.join(d, "sources", "raw", "F-003.txt"), "w", encoding="utf-8").write("Мы считаем, что клиенты уходят из-за цены.\n")
    run([md, d])
    open(os.path.join(d, "00m-schema.txt"), "w", encoding="utf-8").write(
        "row: Малые команды\nrow: Новые\nfeature: Размер группы\nfeature: Причины\nfeature: Что вместо сервиса\n")
    head = "row,feature,value,quote,source,lines,group_match,group_note,n,type,date\n"
    good = ("Малые команды,Размер группы,5264 клиента,Размер теста 5264 клиента,F-001,L4,точная,,5264,результат теста,2026-04\n"
            "Малые команды,Причины,платят по счёту,\"платим по счёту, сервис не берём\",F-002,L1,соседняя,,1,слова,2026\n"
            "Новые,Причины,команда: цена,клиенты уходят из-за цены,F-003,L1,соседняя,,не указано,утверждение команды,2024\n"
            "Новые,Что вместо сервиса,бонус баллами,Бонус начисляется баллами программы лояльности,F-001,L5,соседняя,,5264,описание,2026-04\n")
    cells = os.path.join(d, "00m-cells.csv")
    open(cells, "w", encoding="utf-8").write(head + good)
    r = run([bm, d, "--today", "2026-10-18"])
    expect("модель: надёжность посчитана по правилам", r.returncode == 0 and "значение 1, версия 1, идея 2, нет данных 2" in r.stdout, r.stdout)
    mdl = open(os.path.join(d, "00m-model.md"), encoding="utf-8").read()
    expect("модель: пустые клетки и старые данные перечислены", "Новые × Размер группы" in mdl and "Новые × Причины" in mdl.split("старше года")[-1], mdl[-400:])
    open(cells, "w", encoding="utf-8").write(head + good.replace("Размер теста 5264 клиента", "Размер теста 9999 клиента"))
    r = run([bm, d])
    expect("модель: цитата не из строки поймана", r.returncode == 1 and "не найдена" in r.stdout, r.stdout)
    open(cells, "w", encoding="utf-8").write(head + good.replace("Малые команды,Причины", "Средние команды,Причины"))
    r = run([bm, d])
    expect("модель: строка вне схемы поймана", r.returncode == 1 and "вне схемы" in r.stdout, r.stdout)
    open(cells, "w", encoding="utf-8").write(head + good.replace("результат теста", "мнение"))
    r = run([bm, d])
    expect("модель: недопустимый тип источника пойман", r.returncode == 1 and "type" in r.stdout, r.stdout)
    open(cells, "w", encoding="utf-8").write(head + good)
    run([bm, d, "--today", "2026-10-18"])
    dos = ("### F-001 — тест\n- Тип: отчёт о тесте\n- Про кого: сегмент малых команд\n- Про продукт: бонус баллами\n- Статус чтения: прочитан\n\n"
           "### F-002 — интервью\n- Тип: интервью\n- Про кого: респондент\n- Про продукт: нет\n- Статус чтения: прочитан\n\n"
           "### F-003 — утверждение\n- Тип: утверждение команды\n- Про кого: не указано\n- Про продукт: нет\n- Статус чтения: не читается\n")
    open(os.path.join(d, "00d-map.md"), "w", encoding="utf-8").write(dos)
    r = run([ri, d, "--limit", "1"])
    imp = open(os.path.join(d, "00i-impact.md"), encoding="utf-8").read()
    expect("важность: кандидат на углубление выбран по формуле, нечитаемый — в расшифровку",
           r.returncode == 0 and "Углубить: F-001" in r.stdout and "F-003" in imp.split("Нужна расшифровка")[1].split("##")[0], r.stdout + imp[:300])
    lim = open(os.path.join(d, "00r-limits.md"), "w", encoding="utf-8")
    lim.write("| № | статус | что | доказательство | кто подтвердил |\n| --- | --- | --- | --- | --- |\n"
              "| R-1 | есть | бонус баллами | «Бонус начисляется баллами программы лояльности» [F-001 L5] | документы |\n"
              "| R-2 | нет | денежного бонуса нет | — | человек |\n")
    lim.close()
    hyp = ("### Г-1. Сообщение о баллах\n- **Клетка:** Малые команды × Причины\n- **Рамка продукта:** R-1\n- **Размер группы:** 5264 [F-001]\n\n"
           "### Г-2. Другая\n- **Клетка:** Новые × Размер группы\n- **Рамка продукта:** R-1\n- **Размер группы:** 3000 [допущение: оценка]\n")
    hp = os.path.join(d, "02-hypotheses.md")
    open(hp, "w", encoding="utf-8").write(hyp)
    r = run([cc, d])
    expect("цепочка: верная проходит, пустая клетка — предупреждение", r.returncode == 0 and "пуста" in r.stdout, r.stdout)
    open(hp, "w", encoding="utf-8").write(hyp.replace("R-1\n- **Размер группы:** 3000", "R-2\n- **Размер группы:** 3000"))
    r = run([cc, d])
    expect("цепочка: механики нет в продукте — ошибка", r.returncode == 1 and "нет в продукте" in r.stdout, r.stdout)
    open(hp, "w", encoding="utf-8").write(hyp.replace("- **Рамка продукта:** R-1\n- **Размер группы:** 5264 [F-001]", "- **Размер группы:** 5264 [F-001]"))
    r = run([cc, d])
    expect("цепочка: нет рамки продукта — ошибка", r.returncode == 1 and "рамка продукта" in r.stdout, r.stdout)
    open(hp, "w", encoding="utf-8").write(hyp.replace("Малые команды × Причины", "Средние команды × Причины"))
    r = run([cc, d])
    expect("цепочка: клетки нет в модели — ошибка", r.returncode == 1 and "нет в модели" in r.stdout, r.stdout)
    open(hp, "w", encoding="utf-8").write(hyp.replace("5264 [F-001]", "по оценке"))
    r = run([cc, d])
    expect("цепочка: размер группы без числа — ошибка", r.returncode == 1 and "Размер группы" in r.stdout, r.stdout)
    open(hp, "w", encoding="utf-8").write(hyp)
    limp = os.path.join(d, "00r-limits.md")
    open(limp, "a", encoding="utf-8").write("| R-3 | есть | лимит | «Лимит 50 тыс.» [F-001 L5] | документы |\n")
    r = run([cc, d])
    expect("цепочка: рамка с цитатой не из строки — ошибка", r.returncode == 1 and "R-3" in r.stdout, r.stdout)
    tr = os.path.join(d, "02e-trace.md")
    good_tr = ("1. Клетка: Малые команды × Размер группы; надёжность: значение; гипотеза: Г-1\n"
               "2. Клетка: Новые × Что вместо сервиса; надёжность: версия; гипотеза: Г-2\n"
               "3. Клетка: Малые команды × Причины; надёжность: идея; гипотеза: Г-3\n"
               "4. Клетка: Новые × Размер группы; надёжность: нет данных; гипотеза: Г-4; не ранжируется\n")
    open(tr, "w", encoding="utf-8").write(good_tr)
    r = run([cr, d])
    expect("порядок: следующий из надёжности проходит", r.returncode == 0, r.stdout)
    open(tr, "w", encoding="utf-8").write(good_tr.replace("надёжность: версия", "надёжность: значение"))
    r = run([cr, d])
    expect("порядок: надёжность не по модели — ошибка", r.returncode == 1 and "по модели" in r.stdout, r.stdout)
    lines = good_tr.splitlines()
    open(tr, "w", encoding="utf-8").write("\n".join([lines[0], lines[2], lines[1], lines[3]]) + "\n")
    r = run([cr, d])
    expect("порядок: надёжность растёт вниз без причины — ошибка", r.returncode == 1 and "выше" in r.stdout, r.stdout)
    open(tr, "w", encoding="utf-8").write("\n".join([lines[0], lines[2], lines[1] + "; расхождение: быстрый тест", lines[3]]) + "\n")
    r = run([cr, d])
    expect("порядок: «расхождение» с причиной разрешает", r.returncode == 0, r.stdout)
    open(tr, "w", encoding="utf-8").write(good_tr.replace("; не ранжируется", ""))
    r = run([cr, d])
    expect("порядок: «нет данных» без «не ранжируется» — ошибка", r.returncode == 1 and "не ранжируется" in r.stdout, r.stdout)
    open(tr, "w", encoding="utf-8").write("\n".join([lines[3], lines[0], lines[1], lines[2]]) + "\n")
    r = run([cr, d])
    expect("порядок: ранжированное после «не ранжируется» — ошибка", r.returncode == 1 and "после" in r.stdout, r.stdout)


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
        tr = os.path.join(root, "context", "interview-01.md")
        open(tr, "w", encoding="utf-8").write("Интервьюер: Как сверяете?\nРеспондент: Ёлки, вручную в Excel, каждую пятницу.\n")
        r3 = run([add, "--task", task, "--kind", "interview", "--location", tr, "--ctx-type", "voice", "--pub-date", "2026-08"])
        expect("регистрация транскрипта", r3.stdout.strip() == "F-003", r3.stderr)
        r4 = run([add, "--task", task, "--kind", "web", "--location", "https://c.ru", "--level", "3", "--read", "not-read"], "")
        expect("непрочитанный источник", r4.stdout.strip() == "F-004", r4.stderr)
        cprv = os.path.join(HERE, "check_private.py")
        open(os.path.join(task, "private.txt"), "w", encoding="utf-8").write("# имена\nТестор\nТестин\n")
        pa = os.path.join(task, "src-priv.md")
        open(pa, "w", encoding="utf-8").write(
            "Респондент Тестора: +7 (999) 123-45-67, ИНН 7701234567, почта ivan@example.ru.\n"
            "Сказала Тестина. Чисто: Интервью 3, сегмент ВВ.\n")
        pv = run([cprv, task])
        expect("персональные данные пойманы", pv.returncode == 1 and "телефон" in pv.stdout and "e-mail" in pv.stdout
               and "ИНН" in pv.stdout and "термин из private.txt: Тестор" in pv.stdout and "термин из private.txt: Тестин" in pv.stdout, pv.stdout)
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

        n4 = run([an, "--task", task, "--kind", "derived", "--key", "root", "--what", "корень из 4", "--formula", "sqrt(N-001 - N-001 + 4) + N-001 ** 2 - N-001 ** 2",
                  "--value", "2", "--unit", "шт"])
        expect("формула: sqrt и степень принимаются", n4.returncode == 0, n4.stderr)
        n5 = run([an, "--task", task, "--kind", "derived", "--key", "z", "--what", "квантиль", "--formula", "ppf(0.975)", "--value", "1.96", "--unit", "z"])
        expect("формула: обратная функция нормального распределения принимается", n5.returncode == 0, n5.stderr)
        expect("формула: степень больше предела отклонена",
               run([an, "--task", task, "--kind", "derived", "--key", "big", "--what", "x", "--formula", "N-001 ** 99", "--value", "1", "--unit", "шт"]).returncode == 2)
        expect("add_number -h работает (знак процента в справке)", run([an, "-h"]).returncode == 0)
        open(os.path.join(task, "src-blk.md"), "w", encoding="utf-8").write(
            "Вывод.\n\nСЧЁТ ОПОР (считает scripts/trust_map.py)\n\nЧисел: 3\n  допущение [N-002] доля = 0.5 доля — причина\n\nПроверки смысла: отчётов нет\n\n**Проверить вручную**\nРост [N-001] 99%.\n")
        cb = run([cn, task])
        expect("блок СЧЁТ ОПОР не разбирается проверкой чисел, текст за блоком — разбирается",
               "src-blk.md: рядом с [N-002]" not in cb.stdout and "src-blk.md: рядом с [N-001]" in cb.stdout, cb.stdout)
        os.remove(os.path.join(task, "src-blk.md"))

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
        open(os.path.join(task, "private.txt"), "w", encoding="utf-8").write("Пробна\nТестина\n")
        stem_art = os.path.join(task, "src-stem.md")
        open(stem_art, "w", encoding="utf-8").write("Спросили Пробну. Ответила Тестине? Нет, Тестины. Чисто: Интервью 4.\n")
        stp = run([os.path.join(HERE, "check_private.py"), task])
        expect("падежи имён ловятся, даже если в private.txt полная форма",
               stp.returncode == 1 and stp.stdout.count("термин из private.txt: Пробна") == 1 and stp.stdout.count("термин из private.txt: Тестина") == 1, stp.stdout)
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
        empty = tempfile.mkdtemp(prefix="polygon-empty-")
        lost = subprocess.run(["sh", "-c", pre_cmd], input=forbidden, capture_output=True, text=True, cwd=empty,
                              env=dict(os.environ, CLAUDE_PROJECT_DIR="/нет/такой/папки"))
        expect("хук записи: скрипта нет — запись не блокируется", lost.returncode == 0, lost.stderr)
        lost2 = subprocess.run(["sh", "-c", stop_cmd], input="{}", capture_output=True, text=True, cwd=empty,
                               env=dict(os.environ, CLAUDE_PROJECT_DIR="/нет/такой/папки"))
        expect("стоп-хук: скрипта нет — ответ не блокируется", lost2.returncode == 0, lost2.stderr)
        found = subprocess.run(["sh", "-c", pre_cmd], input=forbidden, capture_output=True, text=True, cwd=empty,
                               env=dict(os.environ, CLAUDE_PROJECT_DIR=proj))
        expect("хук записи: скрипт на месте — запись в систему блокируется", found.returncode == 2, found.stderr)
        open(os.path.join(proj, "AGENTS.md"), "w", encoding="utf-8").write("# проект\n")
        no_env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
        found2 = subprocess.run(["sh", "-c", pre_cmd], input=forbidden, capture_output=True, text=True, cwd=proj,
                                env=no_env)
        expect("хук записи: переменной нет — скрипт найден по рабочей папке", found2.returncode == 2, found2.stderr)
        stale = subprocess.run(["sh", "-c", pre_cmd],
                               input=_json.dumps({"tool_name": "Write", "tool_input": {"file_path": "methodology/x.md"}, "cwd": proj}),
                               capture_output=True, text=True, cwd=proj, env=dict(os.environ, CLAUDE_PROJECT_DIR=empty))
        expect("хук записи: устаревшая переменная — корень берётся из рабочей папки сессии", stale.returncode == 2, stale.stderr)
        shutil.rmtree(empty, ignore_errors=True)
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
        shutil.copy(os.path.join(HERE, "trust_block.py"), os.path.join(root, "scripts", "trust_block.py"))
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
        polygon_tests(root)
        sensitivity_tests(root)
        path_tests(root)
        trace_tests()
        roles_tests()
        route_tests()
        data_block_tests(root)
        rules_tests()
        audit_tests(root)
        message_tests()
        polygon_more_tests(root)
        effort_tests(root)
        knowledge_tests(root)
        map_tests(root)
        model_tests(root)
        knowledge_links_tests(root)
        forecast_tests(root)
        rehearsal_tests(root)
        ideas_tests(root)
        fresh_tests(root)
        long_list_tests(root)
        backlog_tests(root)
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
