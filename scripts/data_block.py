#!/usr/bin/env python3
"""Блоки данных в артефактах: машинная часть — JSON по схеме, а не текст, который ловят регулярками.

Исполнитель пишет структурную часть артефакта блоком

    ```данные
    {"отсев_идей": [{"n": 1, "суть": "…", "вердикт": "кажется валидной", …}]}
    ```

Скрипт проверяет блок по схеме (SCHEMAS) и превращает его в канонический текст (render), а дальше работает обычная
проверка формы — правила не дублируются, а расхождения формата («- С-01 [блок] — …» против «С-01 — …») исчезают.
Текстовый формат по-прежнему принимается: блок данных — способ, при котором формат не может разойтись.

Ключи блоков:
- «по_проверке_смысла» — ответы автора на замечания проверки смысла (review_format.py, check_artifact.py --review);
- «отсев_идей» — отсев новых идей Нострадамуса (check_ideas.py);
- «следствия» — следствия пробного прогона в 03c-rehearsal.md (check_rehearsal.py);
- «по_пробному_прогону» — ответы на следствия в бэклоге или плане (check_rehearsal.py);
- «аудит» — оценки мест выборочного аудита (audit_sample.py).

  python3 scripts/data_block.py <файл>   # показать блоки, ошибки схемы и канонический текст
"""
import json
import re
import sys

FENCE = re.compile(r"^```[ \t]*данные[ \t]*\n(.*?)^```[ \t]*$", re.M | re.S)

S = {"type": "str"}
SCHEMAS = {
    "по_проверке_смысла": {"type": "list", "min": 1, "item": {
        "замечание": {"type": "str", "pattern": r"^[А-ЯA-Z]-\d{2,}$"},
        "ответ": {"type": "enum", "values": ("исправлено", "снято", "оспорено")},
        "что": S}},
    "отсев_идей": {"type": "list", "min": 1, "item": {
        "n": {"type": "int"}, "суть": S,
        "вердикт": {"type": "enum", "values": ("кажется валидной", "переделать первый шаг", "снять")},
        "убивает": S, "возражения": S, "новая": S, "первый_шаг_различает": S, "первый_шаг_выполним": S,
        "один_источник": S, "данные_следующего_раунда": S}},
    "следствия": {"type": "dict", "item": {
        "для_эксперимента": {"type": "list", "min": 1, "item": {
            "тест": {"type": "str", "pattern": r"^(Строка\s+\d+|Карточка\s+\S.*)$"},
            "статус": {"type": "enum", "values": ("как есть", "после правки", "не запускать")},
            "что": S}},
        "для_решения": S, "что_подсказали_персоны": S}},
    "аудит": {"type": "list", "min": 1, "item": {
        "артефакт": S, "строка": {"type": "int"},
        "оценка": {"type": "enum", "values": ("держит", "не держит", "подогнано")},
        "почему": S}},
    "по_пробному_прогону": {"type": "list", "min": 1, "item": {
        "тест": {"type": "str", "pattern": r"^(Строка\s+\d+|Карточка\s+\S.*)$"},
        "ответ": {"type": "enum", "values": ("применено", "человеку", "отклонено")},
        "что": S}},
}
OPTIONAL = {"что"}  # «снято» и «как есть» могут обойтись без пояснения


def blocks(text):
    """[(объект или None, ошибка или None)] по всем блокам ```данные."""
    out = []
    for m in FENCE.finditer(text or ""):
        line = (text[:m.start()].count("\n") + 1)
        try:
            out.append((json.loads(m.group(1)), None))
        except ValueError as e:
            out.append((None, "блок данных со строки %d — не JSON: %s" % (line, e)))
    return out


def check_value(v, spec, where, errors):
    t = spec["type"]
    if t == "str":
        if not isinstance(v, str) or not v.strip():
            errors.append("%s: пусто или не строка" % where)
        elif spec.get("pattern") and not re.match(spec["pattern"], v.strip()):
            errors.append("%s: «%s» не по форме" % (where, v[:40]))
    elif t == "int":
        if not isinstance(v, int):
            errors.append("%s: не число" % where)
    elif t == "enum":
        if not isinstance(v, str) or v.strip().lower() not in spec["values"]:
            errors.append("%s: «%s» — не из допустимых (%s)" % (where, v, " / ".join(spec["values"])))
    elif t == "list":
        if not isinstance(v, list) or len(v) < spec.get("min", 0):
            errors.append("%s: нужен список" % where)
            return
        for i, item in enumerate(v, 1):
            check_fields(item, spec["item"], "%s[%d]" % (where, i), errors)
    elif t == "dict":
        check_fields(v, spec["item"], where, errors)


def check_fields(obj, fields, where, errors):
    if not isinstance(obj, dict):
        errors.append("%s: нужен объект" % where)
        return
    for name, spec in fields.items():
        if name not in obj:
            if name not in OPTIONAL:
                errors.append("%s: нет поля «%s»" % (where, name))
            continue
        if name in OPTIONAL and obj[name] in ("", None):
            continue
        check_value(obj[name], spec, "%s.%s" % (where, name), errors)


def find(text, key):
    """(значение блока с ключом key или None, ошибки JSON и схемы)."""
    errors, value = [], None
    for obj, err in blocks(text):
        if err:
            errors.append(err)
            continue
        if isinstance(obj, dict) and key in obj:
            value = obj[key]
            check_value(value, SCHEMAS[key], key, errors)
    return value, errors


def _s(v):
    return re.sub(r"\s+", " ", str(v or "")).strip()


def render(key, value):
    """Канонический текст, который понимают проверки формы."""
    if key == "по_проверке_смысла":
        return "ПО ПРОВЕРКЕ СМЫСЛА\n" + "".join(
            "%s — %s%s\n" % (_s(a.get("замечание")), _s(a.get("ответ")).lower(),
                             ": " + _s(a.get("что")) if _s(a.get("что")) else "") for a in value if isinstance(a, dict))
    if key == "отсев_идей":
        out = ["## ОТСЕВ ИДЕЙ"]
        for i in value:
            if not isinstance(i, dict):
                continue
            out += ["Идея %s — %s" % (i.get("n"), _s(i.get("суть"))),
                    "Вердикт: " + _s(i.get("вердикт")), "Убивает: " + _s(i.get("убивает")),
                    "Возражения: " + _s(i.get("возражения")), "Новая: " + _s(i.get("новая")),
                    "Первый шаг различает: " + _s(i.get("первый_шаг_различает")),
                    "Первый шаг выполним: " + _s(i.get("первый_шаг_выполним")),
                    "Один источник: " + _s(i.get("один_источник")),
                    "Данные для следующего раунда: " + _s(i.get("данные_следующего_раунда")), ""]
        return "\n".join(out) + "\n"
    if key == "следствия":
        v = value if isinstance(value, dict) else {}
        units = "".join("%s — статус: %s%s\n" % (_s(u.get("тест")), _s(u.get("статус")).lower(),
                                                  " — " + _s(u.get("что")) if _s(u.get("что")) else "")
                        for u in v.get("для_эксперимента") or [] if isinstance(u, dict))
        return ("## СЛЕДСТВИЯ\n### Для эксперимента\n%s### Для решения\n%s\n### Что подсказали персоны\n%s\n"
                % (units, _s(v.get("для_решения")), _s(v.get("что_подсказали_персоны"))))
    if key == "по_пробному_прогону":
        return "## ПО ПРОБНОМУ ПРОГОНУ\n" + "".join(
            "%s — %s: %s\n" % (_s(a.get("тест")), _s(a.get("ответ")).lower(), _s(a.get("что")) or "—")
            for a in value if isinstance(a, dict))
    if key == "аудит":
        return "## АУДИТ\n" + "".join("%s:%s — %s: %s\n" % (_s(a.get("артефакт")), a.get("строка"), _s(a.get("оценка")),
                                                           _s(a.get("почему"))) for a in value if isinstance(a, dict))
    raise KeyError(key)


def canonical(text, key):
    """(канонический текст блока или None, ошибки) — для проверок формы."""
    value, errors = find(text, key)
    if value is None:
        return None, errors
    return render(key, value), errors


def main():
    if len(sys.argv) < 2:
        sys.stderr.write(__doc__)
        return 2
    text = open(sys.argv[1], encoding="utf-8").read()
    bad = 0
    for key in SCHEMAS:
        out, errors = canonical(text, key)
        for e in errors:
            print("ошибка: " + e)
            bad += 1
        if out:
            print(out)
    if not blocks(text):
        print("Блоков данных нет.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
