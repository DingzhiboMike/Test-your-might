#!/usr/bin/env python3
"""Проверяет, что каждый шаг-источник в логе поставлен, а не взят «для полноты», и что вопрос шага — тот же, что в ТЗ.

  python3 scripts/check_log_sources.py tasks/<папка>

Шаг-источник — заголовок «ШАГ N — <скилл>», где скилл один из восьми источников данных. В его блоке (до следующего
«ШАГ» или конца лога) должны быть строки:
- «Вопрос:»       — вопрос, канал, критерий ответа до поиска, бюджет запросов;
- «Зачем:»        — что без этого ответа генератору или проверке по сути пришлось бы угадывать;
- «Уже известно:» — что по вопросу уже лежит в контексте и реестре; утверждения команды — с пометкой «проверяется»;
- «Пункт GAP:»    — пункт GAP из ТЗ дословно, с номером («GAP 3 — …»). Текст сверяется с `00-tz.md`.

Строка «Инструмент:» — инструмент методологии из раздела «Подбирать инструмент» указателя (`methodology/tools-index.md`)
и почему; «—», если подходящего нет. Её отсутствие — предупреждение (старые логи её не знают); указанная строка,
которой нет в указателе, — ошибка.

Вопрос шага не уже пункта GAP. Если в пункте несколько частей («где искать / как отбирать / как строить», части
через « / » или «;»), каждая часть должна быть видна в строке «Вопрос:» — или в блоке есть строка «Сужение:»: что
убрано и почему. Части сверяются по основам слов, поэтому перефразировать можно, терять часть — нельзя.

Канал «веб» в строке «Вопрос:» допустим, только если у пункта GAP в ТЗ пометка `{ответ: …}` содержит «веб» — или в
блоке есть строка «Пересмотр:» с причиной (оркестратор после разбора материалов решил иначе, чем диспетчер).

Каждый блок «Запрос данных D-N» в логе — со строкой «Если данных не будет:»: дешёвая замена (метод, выборка, срок)
и чего она не покажет; и со строками «Метрика:», «Одна строка:», «Сверка:» (методология, Д · Шаблон запроса).

Линзы до генератора. В типах «гипотезы», «план проверки», «ТЗ на доработку» перед первым шагом hypothesis-generator
должен стоять блок «ЛИНЗЫ» со строками «Когда», «Вместо нас», «Кто», «Что болит»: в каждой «зову <источник>» или
«не нужно: <причина>». «Ответ во внутренних данных», «условия не выполнены», «экономия шагов» причиной не считаются —
линза ищет сырьё, а не ответ. При «ВЕБ: да» хотя бы одна линза — «зову».

Пустое значение («Зачем: —», «Зачем:») не засчитывается. Ошибка — код возврата 1. Отчёт: tasks/<папка>/checks/log-sources.md.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_path import ANSWER, gap_answers, gap_items  # noqa: E402

SOURCES = ("interview-analyst", "interview-synthesis", "market-analyze", "target-audience-analyst",
           "alternatives-analyst", "customer-path", "market-sizing", "experiment-review")
FIELDS = ("Вопрос", "Зачем", "Уже известно", "Пункт GAP")
STEP = re.compile(r"^ШАГ\s+(\d+)\s*[—-]\s*([\w-]+)", re.M)
# Пачка разборов интервью идёт по файлам контекста, а не по вопросу пункта GAP — для неё пункт GAP не сверяется.
NO_GAP_TEXT = ("interview-analyst",)


def norm(s):
    s = ANSWER.sub(" ", s)
    s = re.sub(r"\[[^\]]*\]", " ", s)
    s = s.replace("ё", "е").replace("Ё", "Е").lower()
    s = re.sub(r"[«»\"“”„*_`]", "", s)
    return re.sub(r"\s+", " ", s).strip(" .;:—-")


def stems(text):
    return {w[:5] for w in re.findall(r"[а-яa-z]{5,}", norm(text))}


def parts(item):
    ps = [p for p in re.split(r"\s/\s|;", norm(item)) if p.strip()]
    return ps if len(ps) > 1 else []


INDEX = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "methodology", "tools-index.md")


def index_places():
    """Все строки «Где» из таблиц указателя (ячейка делится по «;»), в нормализованном виде."""
    if not os.path.exists(INDEX):
        return set()
    places = set()
    for line in open(INDEX, encoding="utf-8"):
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and re.match(r"^(?:M\d+|[ЭДКОПЖС]\s·|Приложение)", cells[1]):
            for part in cells[1].split(";"):
                places.add(norm(part))
    return places


def field(block, name):
    f = re.search(r"^\s*%s:[ \t]*(.*)$" % re.escape(name), block, re.M)
    return f.group(1).strip(" —-–\t") if f else ""


LENSES = ("Когда", "Вместо нас", "Кто", "Что болит")
GENERATIVE = re.compile(r"ТИП ВЫХОДА\W*(гипотезы|план проверки|ТЗ на доработку)", re.I)
BAD_REASON = re.compile(r"внутренн\w* данн|данн\w* компании|условия\s*(1|\d)|не выполн|экономи\w* шаг|бюджет", re.I)


def lenses(text, tz, heads, errors):
    """Блок ЛИНЗЫ перед первым генератором в генеративных типах."""
    if not GENERATIVE.search(tz):
        return
    gen = next((m for m in heads if m.group(2) == "hypothesis-generator"), None)
    if not gen:
        return
    before = text[:gen.start()]
    m = None
    for m in re.finditer(r"^\s*\**ЛИНЗЫ\b.*$", before, re.M):
        pass
    if not m:
        errors.append("ЛИНЗЫ: перед генератором нет блока «ЛИНЗЫ» — когда, вместо нас, кто, что болит: зову или не нужно")
        return
    block = before[m.end():]
    stop = re.search(r"^ШАГ\s+\d", block, re.M)
    block = block[:stop.start()] if stop else block
    called = 0
    for name in LENSES:
        lm = re.search(r"^\s*[-*]?\s*%s\s*[—:-]\s*(.*)$" % re.escape(name), block, re.M | re.I)
        if not lm:
            errors.append("ЛИНЗЫ: нет решения по линзе «%s»" % name)
            continue
        val = lm.group(1).strip()
        if re.match(r"зов\w*\s+[\w-]+", val, re.I):
            called += 1
        elif re.match(r"не нужн\w*\s*:", val, re.I):
            reason = val.split(":", 1)[1].strip()
            if len(reason) < 10:
                errors.append("ЛИНЗЫ: «%s — не нужно» без причины" % name)
            elif BAD_REASON.search(reason):
                errors.append("ЛИНЗЫ: «%s — не нужно: %s» — не причина: линза ищет сырьё в открытом поле, а не ответ "
                              "во внутренних данных" % (name, reason[:60]))
        else:
            errors.append("ЛИНЗЫ: по линзе «%s» нет решения — ни хода к источнику, ни причины отказа" % name)
    if called == 0 and re.search(r"^\**ВЕБ\**:\s*да", tz, re.M | re.I):
        errors.append("ЛИНЗЫ: при «ВЕБ: да» ни одна линза не вызвана — генератор построит всё из одного корня")


def main():
    if len(sys.argv) < 2:
        sys.stderr.write(__doc__)
        return 2
    task = sys.argv[1].rstrip("/")
    path = os.path.join(task, "log.md")
    if not os.path.exists(path):
        print("Лога нет: проверять нечего.")
        return 0
    text = open(path, encoding="utf-8").read()
    tz_path = os.path.join(task, "00-tz.md")
    tz = open(tz_path, encoding="utf-8").read() if os.path.exists(tz_path) else ""
    items = {n: norm(t) for n, t in gap_items(tz).items()}
    raw_items = gap_items(tz)
    answers = gap_answers(tz)
    heads = list(STEP.finditer(text))
    errors, warns, checked = [], [], 0
    for i, m in enumerate(heads):
        skill = m.group(2)
        if skill not in SOURCES:
            continue
        checked += 1
        where = "ШАГ %s — %s" % (m.group(1), skill)
        block = text[m.end():heads[i + 1].start() if i + 1 < len(heads) else len(text)]
        for name in FIELDS:
            if name == "Пункт GAP" and skill in NO_GAP_TEXT:
                continue
            if not field(block, name):
                errors.append("%s: нет строки «%s:» или она пустая" % (where, name))
        tool = re.search(r"^\s*Инструмент:[ \t]*(.*)$", block, re.M)
        if not tool:
            warns.append("%s: нет строки «Инструмент:» (инструмент методологии или «—»)" % where)
        elif tool.group(1).strip() and not tool.group(1).strip().startswith(("—", "-", "–")):
            places = index_places()
            val = norm(tool.group(1))
            if places and not any(pl in val for pl in places):
                errors.append("%s: «Инструмент:» не найден в указателе методологии (раздел «Подбирать инструмент» или другие "
                              "таблицы): %s" % (where, tool.group(1).strip()[:80]))
        point = field(block, "Пункт GAP")
        if not point or skill in NO_GAP_TEXT or not items:
            continue
        nums = [int(n) for n in re.findall(r"GAP\s*(\d+)", point)]
        if not nums:
            errors.append("%s: в «Пункт GAP:» нет номера («GAP k — текст пункта»)" % where)
            continue
        npoint = norm(re.sub(r"GAP\s*\d+\s*[—–:-]?", " ", point))
        question = field(block, "Вопрос")
        narrowed = field(block, "Сужение")
        for n in nums:
            if n not in items:
                errors.append("%s: GAP %d нет в ТЗ" % (where, n))
                continue
            if items[n] not in npoint:
                errors.append("%s: «Пункт GAP:» не совпадает с GAP %d в ТЗ дословно — скопируй пункт целиком, "
                              "с подпунктами" % (where, n))
            lost = [p for p in parts(raw_items[n]) if not (stems(p) & stems(question))]
            if lost and not narrowed:
                errors.append("%s: в «Вопрос:» не видно частей GAP %d: %s — добавь их или строку «Сужение:» "
                              "(что убрано и почему)" % (where, n, " | ".join(lost)))
            if re.search(r"\bвеб\b", question, re.I) and answers.get(n) is not None and "веб" not in answers[n] \
                    and not field(block, "Пересмотр"):
                errors.append("%s: канал «веб» по GAP %d, а в ТЗ ответ помечен «%s» — нет строки «Пересмотр:» с "
                              "причиной" % (where, n, ", ".join(sorted(answers[n]))))

    lenses(text, tz, heads, errors)

    requests = 0
    for m in re.finditer(r"^\s*Запрос данных\s+(D-\d+)", text, re.M):
        requests += 1
        rest = text[m.end():].split("\n", 1)[-1]
        stop = re.search(r"^[ \t]*$|^ШАГ\s+\d|^\s*Запрос данных\s+D-\d", rest, re.M)
        block = rest[:stop.start()] if stop else rest
        if not field(block, "Если данных не будет"):
            errors.append("%s: нет строки «Если данных не будет:» — дешёвая замена и чего она не покажет" % m.group(1))
        for name, hint in (("Метрика", "формула, числитель, знаменатель, окно; не про метрику — «не применимо» с причиной"),
                           ("Одна строка", "что означает одна строка выгрузки"),
                           ("Сверка", "контрольное число и какая выгрузка главнее")):
            if not field(block, name):
                errors.append("%s: нет строки «%s:» — %s (методология, Д · Шаблон запроса)" % (m.group(1), name, hint))

    os.makedirs(os.path.join(task, "checks"), exist_ok=True)
    out = ["# Шаги-источники в логе: " + os.path.basename(task), "",
           "Шагов-источников: %d, запросов данных: %d" % (checked, requests), "", "## Ошибки"]
    out += ["- " + e for e in errors] or ["- нет"]
    out += ["", "## Предупреждения"] + (["- " + w for w in warns] or ["- нет"])
    open(os.path.join(task, "checks", "log-sources.md"), "w", encoding="utf-8").write("\n".join(out) + "\n")
    for e in errors:
        print("лог: " + e)
    for w in warns:
        print("лог (внимание): " + w)
    if not errors:
        print("Шаги-источники: %d, запросов данных: %d, ошибок нет." % (checked, requests))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
