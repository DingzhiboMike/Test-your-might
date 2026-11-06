#!/usr/bin/env python3
"""«Нет данных» — не ответ и в валидации: у каждого такого утверждения есть лучшая догадка и путь к конкретике.

  python3 scripts/check_concrete.py tasks/<папка>             # всё: проверка по сути, документ валидации, сдача
  python3 scripts/check_concrete.py tasks/<папка> --step      # после шага: только 02c и 06
  python3 scripts/check_concrete.py tasks/<папка> --handoff   # после записи сдачи: только 08-handoff.md

Тип «валидация», любой уровень профиля. Проверяет форму, а не смысл:
1. `02c-validation.md`: у каждого утверждения «У-k» с исходом «нет данных» есть поля «Версии», «Скорее»,
   «Что даст ответ», «Где посмотреть». «Скорее» — одна версия с уверенностью (низкая / средняя / высокая),
   а не отказ («нет данных», «не различимы», «зависит от» …). «Где посмотреть» — три ступени от дешёвой к дорогой:
   «у вас —», «открыто —», «живая проверка —»; ступень, которой нет, пишется «нет — почему».
2. `06-validation.md`: в таблице утверждений есть столбец «Скорее», и у строк с исходом «нет данных» он заполнен
   версией, а не отказом.
3. `02c-validation.md` в типах на гипотезы (блоки «ГИПОТЕЗА N»): у вердикта «сузить» или «нет данных» — те же поля
   «Скорее», «Что даст ответ», «Где посмотреть»; у «не держится» — «Скорее»: что верно вместо.
4. `06-directions.md` (тип «карта направлений»): разделы «КАК ДЕЛИТЬ» и «С ЧЕГО НАЧАТЬ», не меньше трёх
   «НАПРАВЛЕНИЕ N», у каждого — «На чём стоит», «Скорее» с уверенностью, «Что различит», «Первый шаг», «Убьёт».
5. `08-handoff.md`, любой тип выхода [R-077 «Тупик — не вывод»]: пункт списка или абзац с тупиковой формулировкой
   («не измерен», «нет данных», «на границе случайности», «спорит», «не верит», «сужены», «эффекта нет» …) несёт
   версию или действие: «→ скорее: … (уверенность …)», «→ шаг: …», «вероятно», «значит», «следующий шаг»,
   «проверить» … Строка «В очереди» / «В запасе» называет, при каком результате к ней вернуться («если …»,
   «вернуться, когда …»), иначе ей место в `08-service.md`. Не проверяются: вводный абзац до первого раздела и
   разделы «Что нужно…», «Чего не покрыл…», «Обещано…», «Вопрос вам», «Что лежит в папке», «Перенесено…».
Держит ли догадка смысл, скрипт не видит: это проверка смысла и аудит.
Ошибка — код возврата 1. Отчёт: tasks/<папка>/checks/concrete.md.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_forecast import REFUSAL, fields, meaningful  # noqa: E402

NO_DATA = re.compile(r"нет\s+данных|не\s+проверено", re.I)
FIELDS = ("Версии", "Что косвенно за каждую", "Что каждая значит для идеи", "Скорее", "Что даст ответ",
          "Где посмотреть", "Опор", "Что не так", "Причина исхода", "Из контекста", "Из сети", "Исход")
REQUIRED = ("Версии", "Скорее", "Что даст ответ", "Где посмотреть")
NOT_SURE = re.compile(r"^\W*(не\s+различим|равновероятн|50\s*/\s*50|непонятно|сложно сказать)", re.I)
CONFIDENCE = re.compile(r"уверенност\w*\s*[:—–-]?\s*(низк|средн|высок)", re.I)
RUNGS = (("у вас", r"у\s+вас\s*[—–:-]"), ("открыто", r"открыт\w*\s*[—–:-]"),
         ("живая проверка", r"живая\s+проверка\s*[—–:-]"))


def read(path):
    return open(path, encoding="utf-8").read() if os.path.exists(path) else ""


def refusal(value):
    v = re.sub(r"\[оценка\]|^\W*оценка\W*", "", value.strip(), flags=re.I)
    return bool(REFUSAL.match(v) or NOT_SURE.match(v))


def claims(text):
    """[(номер, текст блока)] — блоки «У-k — …» до следующего утверждения или заголовка."""
    heads = list(re.finditer(r"^\s*(?:#{1,4}\s*)?\**У-(\d+)\b(?!\+)", text, re.M))
    out = []
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        stop = re.search(r"^#{1,3}\s*(Приложение|ПРИЛОЖЕНИЕ)", text[m.end():end], re.M)
        if stop:
            end = m.end() + stop.start()
        out.append((m.group(1), text[m.start():end]))
    return out


def check_fields(where, got, required):
    """Ошибки одного блока: обязательные поля, «Скорее» — версия с уверенностью, «Где посмотреть» — три ступени."""
    errors = []
    for f in required:
        if f not in got or not meaningful(got[f][1]):
            errors.append("%s: поля «%s» нет или оно пустое" % (where, f))
    if "Скорее" in got and meaningful(got["Скорее"][1]):
        value = got["Скорее"][1]
        if refusal(value):
            errors.append("%s: в «Скорее» отказ («%s…»), а нужна одна версия с уверенностью" % (where, value[:40].strip()))
        elif not CONFIDENCE.search(value):
            errors.append("%s: в «Скорее» нет уверенности (низкая / средняя / высокая)" % where)
    if "Что даст ответ" in got and refusal(got["Что даст ответ"][1]):
        errors.append("%s: в «Что даст ответ» отказ, а нужны данные и какой ответ на что укажет" % where)
    if "Где посмотреть" in got and meaningful(got["Где посмотреть"][1]):
        value = got["Где посмотреть"][1]
        for label, pat in RUNGS:
            m = re.search(pat + r"\s*(.*)", value, re.I)
            if not m or not meaningful(m.group(1)):
                errors.append("%s: в «Где посмотреть» нет ступени «%s —» (если её нет — «нет — почему»)" % (where, label))
    return errors


def check_validation(text):
    errors, n_open = [], 0
    for num, block in claims(text):
        got = fields(block, FIELDS)
        outcome = got.get("Исход", ("", ""))[1].split("\n")[0]
        if not NO_DATA.search(outcome):
            continue
        n_open += 1
        errors += [e.replace("поля", "исход «нет данных», а поля", 1) if "поля «" in e else e
                   for e in check_fields("У-%s" % num, got, REQUIRED)]
    return n_open, errors


HYP_FIELDS = ("Вердикт", "Методология", "Сверка", "Уверенность", "Сузить до", "Основание", "Скорее", "Что даст ответ",
              "Где посмотреть", "Чего не хватает")
NARROW = re.compile(r"сузить|нет\s+данных", re.I)
FAIL = re.compile(r"не\s+держится", re.I)


def hypotheses(text):
    """[(номер, блок)] — блоки «ГИПОТЕЗА N» проверки по сути в типах на гипотезы."""
    heads = list(re.finditer(r"^\s*(?:#{1,4}\s*)?\**ГИПОТЕЗА\s+(\d+)\b", text, re.M))
    out = []
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        tail = re.search(r"^\s*(?:#{1,4}\s*)?\**(?:расхождения|дыры для исследования)", text[m.end():end], re.M | re.I)
        if tail:
            end = m.end() + tail.start()
        out.append((m.group(1), text[m.start():end]))
    return out


def check_hypotheses(text):
    """«Сузить» и «нет данных» — версия, что даст ответ и где посмотреть; «не держится» — версия, что верно вместо."""
    errors, n_open = [], 0
    for num, block in hypotheses(text):
        got = fields(block, HYP_FIELDS)
        verdict = got.get("Вердикт", ("", ""))[1].split("\n")[0]
        where = "Гипотеза %s (%s)" % (num, verdict.strip()[:20])
        if NARROW.search(verdict):
            n_open += 1
            errors += check_fields(where, got, REQUIRED_HYP)
        elif FAIL.search(verdict):
            n_open += 1
            errors += check_fields(where, got, ("Скорее",))
    return n_open, errors


REQUIRED_HYP = ("Скорее", "Что даст ответ", "Где посмотреть")

DIR_FIELDS = ("Суть", "Кому", "На чём стоит", "Скорее", "Что различит", "Первый шаг", "Убьёт")
DIR_REQUIRED = ("На чём стоит", "Скорее", "Что различит", "Первый шаг", "Убьёт")


def check_directions(text):
    """06-directions.md: у каждого «НАПРАВЛЕНИЕ N» — на чём стоит, версия с уверенностью, что различит, первый шаг,
    что убьёт; есть оси деления и «С чего начать». Ни одно направление не остаётся без предположения и действия."""
    errors = []
    heads = list(re.finditer(r"^\s*(?:#{1,4}\s*)?\**НАПРАВЛЕНИЕ\s+(\d+)\b", text, re.M))
    if len(heads) < 3:
        errors.append("06-directions.md: направлений %d — карте нужно не меньше трёх («НАПРАВЛЕНИЕ N — …»)" % len(heads))
    if not re.search(r"^\s*(?:#{1,4}\s*)?\**КАК ДЕЛИТЬ", text, re.M):
        errors.append("06-directions.md: нет раздела «КАК ДЕЛИТЬ» — оси, по которым разложены направления")
    if not re.search(r"^\s*(?:#{1,4}\s*)?\**С ЧЕГО НАЧАТЬ", text, re.M):
        errors.append("06-directions.md: нет раздела «С ЧЕГО НАЧАТЬ»")
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        tail = re.search(r"^\s*(?:#{1,4}\s*)?\**(?:С ЧЕГО НАЧАТЬ|ЧЕГО НЕ ХВАТАЕТ|КАК ДЕЛИТЬ)", text[m.end():end], re.M)
        if tail:
            end = m.end() + tail.start()
        block = text[m.start():end]
        got = fields(block, DIR_FIELDS)
        errors += [e.replace("Направление", "06-directions.md, направление") for e in
                   check_fields("Направление %s" % m.group(1), got, DIR_REQUIRED)]
    return errors


def table_rows(text):
    """(заголовок, строки) первой таблицы, в шапке которой есть «Скорее» или «исход»."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith("|") and re.search(r"исход", line, re.I):
            head = [c.strip() for c in line.strip().strip("|").split("|")]
            rows = []
            for row in lines[i + 2:]:
                if not row.strip().startswith("|"):
                    break
                rows.append([c.strip() for c in row.strip().strip("|").split("|")])
            return head, rows
    return None, []


def check_document(text):
    errors = []
    head, rows = table_rows(text)
    if head is None:
        return ["06-validation.md: нет таблицы утверждений со столбцом исхода"]
    low = [h.lower() for h in head]
    i_out = next((i for i, h in enumerate(low) if "исход" in h), None)
    i_guess = next((i for i, h in enumerate(low) if "скорее" in h), None)
    if i_guess is None:
        return ["06-validation.md: в таблице утверждений нет столбца «Скорее»"]
    for row in rows:
        if i_out is None or i_out >= len(row) or not NO_DATA.search(row[i_out]):
            continue
        name = row[0][:40] if row else "?"
        cell = row[i_guess] if i_guess < len(row) else ""
        if not meaningful(cell):
            errors.append("06-validation.md, «%s»: исход «нет данных», а «Скорее» пусто" % name)
        elif refusal(cell):
            errors.append("06-validation.md, «%s»: в «Скорее» отказ («%s»)" % (name, cell[:40]))
    return errors


DEAD_END = re.compile(
    r"не\s+измер|нет\s+данных|данных\s+(?:нет|не\s+хват|мало)|мало\s+данных|неизвестн|не\s+известн|не\s+проверен"
    r"|не\s+подтвержд|не\s+доказ|на\s+границе\s+случайност|спорит|противореч|не\s+различим|не\s+держится"
    r"|сужен|не\s+вер(?:ит|ю|им)\b|не\s+показ(?:ал|ыва)|не\s+на\s+чем|непонятн|неясн|не\s+ясн|под\s+вопросом"
    r"|(?:эффекта|отклика|прироста|разницы|сигнала)[^.;]{0,30}?\s+нет\b|нет\s+(?:эффекта|отклика|прироста|разницы|сигнала)",
    re.I)
RESOLVED = re.compile(
    r"→|скорее|вероятн|верси[яюи]|значит|поэтому|следующий\s+шаг|первый\s+шаг|\bшаг\s*:|провер(?:ить|им|ьте|ка\s*:)"
    r"|сделать|сначала|различ(?:ит|ат|ить)|убь[её]т|перевернёт|вместо|оценка|предполож|допущени|гипотез[аы]\s*:"
    r"|покажет|ответит|уточнит|выгрузк|звонк|запрос", re.I)
QUEUE = re.compile(r"^\W*(?:в\s+очереди|в\s+запасе)", re.I)
QUEUE_OK = re.compile(r"\bесли\b|\bкогда\b|вернуться|при\s+результате|после\s+того", re.I)
HANDOFF_SKIP = re.compile(r"что\s+нужно|чего\s+не\s+покрыл|обещан|вопрос\s+вам|что\s+лежит|перенесено|замечания\s+к\s+систем",
                          re.I)
ITEM = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")


def handoff_units(text):
    """[(раздел, текст единицы)]: пункты списков (с продолжениями) и абзацы; вводный текст до первого «## » и
    таблицы пропускаются."""
    units, section, cur = [], None, None
    for line in text.splitlines():
        if line.startswith("#"):
            if cur:
                units.append(cur)
            cur = None
            section = line.lstrip("#").strip() if line.startswith("##") else section
            continue
        if section is None or line.strip().startswith("|"):
            continue
        if not line.strip():
            if cur:
                units.append(cur)
            cur = None
            continue
        if ITEM.match(line) or cur is None:
            if cur:
                units.append(cur)
            cur = [section, line.strip()]
        else:
            cur[1] += " " + line.strip()
    if cur:
        units.append(cur)
    return [(sec, txt) for sec, txt in units if not HANDOFF_SKIP.search(sec or "")]


def check_handoff(text):
    errors = []
    for sec, txt in handoff_units(text):
        plain = re.sub(r"[*_`]", "", txt)
        short = plain[:70].strip()
        if QUEUE.match(ITEM.sub("", plain)) or re.search(r"(?:^|[.:]\s)(?:В\s+очереди|В\s+запасе)", plain):
            q = re.search(r"(?:В\s+очереди|В\s+запасе)(.*)", plain, re.I)
            if q and not QUEUE_OK.search(q.group(1)):
                errors.append("08-handoff.md, «%s»: очередь без условия («%s…»): назови, при каком результате к ней "
                              "вернуться, или перенеси список в 08-service.md" % (sec, q.group(0)[:50].strip()))
            continue
        if DEAD_END.search(plain) and not RESOLVED.search(plain):
            errors.append("08-handoff.md, «%s»: тупик без версии и шага («%s…»): допиши «→ скорее: … (уверенность …)» "
                          "и/или «→ шаг: …»" % (sec, short))
    return errors


def main():
    if len(sys.argv) < 2:
        sys.stderr.write(__doc__)
        return 2
    task = sys.argv[1].rstrip("/")
    only_handoff = "--handoff" in sys.argv[2:]
    only_step = "--step" in sys.argv[2:]
    val, doc = read(os.path.join(task, "02c-validation.md")), read(os.path.join(task, "06-validation.md"))
    hand = read(os.path.join(task, "08-handoff.md"))
    dirs = "" if only_handoff else read(os.path.join(task, "06-directions.md"))
    if only_handoff:
        val = doc = ""
    if only_step:
        hand = ""
    if not val and not doc and not hand and not dirs:
        print("Проверки по сути, документа валидации и сдачи нет: проверять нечего.")
        return 0
    if val and hypotheses(val) and not claims(val):
        n_open, errors = check_hypotheses(val)
    else:
        n_open, errors = check_validation(val) if val else (0, [])
    if doc:
        errors += check_document(doc)
    if dirs:
        errors += check_directions(dirs)
    if hand:
        errors += check_handoff(hand)
    os.makedirs(os.path.join(task, "checks"), exist_ok=True)
    out = ["# Конкретика: «нет данных» и тупики в сдаче: " + os.path.basename(task), "",
           "Утверждений или гипотез без ясного ответа: %d" % n_open, "Сдача проверена: %s" % ("да" if hand else "нет её"),
           "", "## Ошибки"] + (["- " + e for e in errors] or ["- нет"])
    open(os.path.join(task, "checks", "concrete.md"), "w", encoding="utf-8").write("\n".join(out) + "\n")
    for e in errors:
        print("конкретика: " + e)
    if not errors:
        print("Конкретика: утверждений «нет данных» %d, у всех есть догадка и где посмотреть; тупиков в сдаче нет." % n_open)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
