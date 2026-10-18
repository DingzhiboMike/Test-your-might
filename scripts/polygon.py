#!/usr/bin/env python3
"""Полигон: синтетические отчёты об экспериментах с заранее известной правдой и сверка ответа навыка.

  python3 scripts/polygon.py make --seed 1 --reports DIR --key-out FILE [--task tasks/_polygon-1]
  python3 scripts/polygon.py score --key FILE --answer FILE [--min 0.8]

make: генерирует 11 выдуманных отчётов (по одному на ловушку) без нейросети, только по seed. Отчёты пишутся в DIR,
ключ ответов — в FILE (вне DIR); навыку ключ не показывается. С --task создаётся папка задачи: минимальное ТЗ и
отчёты, зарегистрированные как источники (tasks/ в git не попадает).

score: читает блок «СВЕРКА» из ответа навыка, строки вида
  T-03 | поле=бета | исход=заложенный_исключён | флаги=недошедшее,выбросы
и сравнивает с ключом: исход (допустимые варианты из ключа), поле мощности, флаги (F1). Печатает таблицу и итог;
с --min код возврата 1, если точность по исходу ниже порога.

Ещё три режима:
  python3 scripts/polygon.py map-recall --seed 1 [--min 0.9]      # полнота тегов map_docs.py на выдуманных строках
  python3 scripts/polygon.py make-interviews --seed 1 --out DIR --key-out FILE   # транскрипты с заложенными сигналами
  python3 scripts/polygon.py score-interviews --key FILE --answer FILE [--min 0.7]
map-recall — без нейросети, входит в CI: ловит регрессию разметки (часть форм нарочно трудная — числа словами,
«в два раза» — полнота ниже 1 честно). make-interviews — сигналы: обход, триггер, слова против поведения,
альтернатива, цена, барьер; ответ навыка — блок «СВЕРКА», строки «И-01 | сигналы=обход,триггер».

Синтетика ничего не подтверждает: полигон проверяет навык, а не мир.
"""
import argparse
import json
import math
import os
import random
import subprocess
import sys
from statistics import NormalDist

ND = NormalDist()
HERE = os.path.dirname(os.path.abspath(__file__))


# ---------- статистика ----------
def pval(x1, n1, x2, n2):
    p = (x1 + x2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    return math.erfc(abs(x2 / n2 - x1 / n1) / se / math.sqrt(2)) if se else 1.0


def interval(x1, n1, x2, n2):
    a, b = x1 / n1, x2 / n2
    se = math.sqrt(a * (1 - a) / n1 + b * (1 - b) / n2)
    return b - a, b - a - 1.96 * se, b - a + 1.96 * se


def n_group(p1, p2, power=0.8, alpha=0.05):
    z = ND.inv_cdf(1 - alpha / 2) + ND.inv_cdf(power)
    return int(math.ceil(z * z * (p1 * (1 - p1) + p2 * (1 - p2)) / (p2 - p1) ** 2))


def draw(rng, n, p):
    return max(0, min(n, int(round(rng.gauss(n * p, math.sqrt(n * p * (1 - p)))))))


def pct(x):
    return ("%.2f" % (100 * x)).replace(".", ",") + "%"


# ---------- сценарии ----------
DOMAINS = [
    ("скидка 20% на второй месяц подписки", "доля продлений на второй месяц"),
    ("напоминание об оплате в мессенджере", "доля оплативших в течение 7 дней"),
    ("бесплатная доставка первого заказа", "доля сделавших второй заказ за 30 дней"),
    ("бонус за приглашение коллеги", "доля активировавших пробный период"),
    ("онбординг-письма с примерами", "доля дошедших до первой публикации за 14 дней"),
]


def base(rng, power_plan=0.8):
    p0 = round(rng.uniform(0.05, 0.18), 3)
    lift = round(rng.uniform(0.012, 0.03), 3)
    return {"p0": p0, "lift": lift, "n_plan": n_group(p0, p0 + lift, power_plan), "dom": rng.choice(DOMAINS),
            "alpha": 0.05, "field": None, "slices": [], "notes": []}


def finish(sc, nA, nB, xA, xB, verdict):
    sc.update(nA=nA, nB=nB, xA=xA, xB=xB, verdict=verdict, p=pval(xA, nA, xB, nB))
    return sc


def s_beta_null(rng):
    for _ in range(300):
        sc = base(rng)
        sc["field"] = "0.2"                       # записана бета, группы посчитаны под мощность 0,8
        n = int(sc["n_plan"] * rng.uniform(0.97, 1.03))
        xA, xB = draw(rng, n, sc["p0"]), draw(rng, n, sc["p0"])
        if pval(xA, n, xB, n) > 0.2 and interval(xA, n, xB, n)[2] < sc["lift"]:
            sc = finish(sc, n, n, xA, xB, "Ни одна метрика не прокрасилась, оснований утверждать влияние нет.")
            sc["key"] = dict(поле="бета", исход=["заложенный_исключён"], флаги=[])
            return sc


def s_weak(rng):
    for _ in range(300):
        sc = base(rng, power_plan=0.2)
        sc["field"] = "0.2"                       # мощность действительно низкая: группы посчитаны под 0,2
        n = sc["n_plan"]
        xA, xB = draw(rng, n, sc["p0"]), draw(rng, n, sc["p0"] + sc["lift"] / 2)
        d, lo, hi = interval(xA, n, xB, n)
        if pval(xA, n, xB, n) > 0.2 and lo < 0 < sc["lift"] < hi:
            sc = finish(sc, n, n, xA, xB, "Статистически значимой разницы нет, гипотезу не подтвердили.")
            sc["key"] = dict(поле="мощность_низкая", исход=["не_различимо"], флаги=[])
            return sc


def s_true_pos(rng):
    for _ in range(300):
        sc = base(rng)
        sc["field"] = "0.8"
        n = sc["n_plan"]
        xA, xB = draw(rng, n, sc["p0"]), draw(rng, n, sc["p0"] + sc["lift"] * 1.2)
        if pval(xA, n, xB, n) < 0.01:
            sc = finish(sc, n, n, xA, xB, "Метрика прокрасилась. Окупаемость по расчёту — около 3 месяцев при плане 6.")
            sc["key"] = dict(поле="мощность", исход=["можно_раскатывать"], флаги=[])
            return sc


def s_slice_fp(rng):
    for _ in range(300):
        sc = base(rng)
        sc["field"] = "0.8"
        n = sc["n_plan"]
        xA, xB = draw(rng, n, sc["p0"]), draw(rng, n, sc["p0"])
        if not (pval(xA, n, xB, n) > 0.3 and interval(xA, n, xB, n)[2] < sc["lift"]):
            continue
        names = ["новые клиенты", "старые клиенты", "малый чек", "большой чек", "будни", "выходные",
                 "мобильное приложение", "сайт", "север", "юг"]
        rng.shuffle(names)
        slices = []
        for i, nm in enumerate(names):
            m = max(200, n // 6)
            a = draw(rng, m, sc["p0"])
            b = draw(rng, m, sc["p0"] + (0.045 if i == 3 else 0))
            slices.append((nm, m, m, a, b, pval(a, m, b, m)))
        if 0.01 < slices[3][5] < 0.05 and sum(1 for s in slices if s[5] < 0.05) == 1:
            sc = finish(sc, n, n, xA, xB, "Основная метрика не прокрасилась, но в сегменте «%s» значимый рост — "
                                          "рекомендуем раскатить на сегмент." % names[3])
            sc["slices"] = slices
            sc["key"] = dict(поле="мощность", исход=["заложенный_исключён"], флаги=["разрезы"])
            return sc


def s_srm(rng):
    sc = base(rng)
    sc["field"] = "0.8"
    n = sc["n_plan"]
    nA, nB = int(n * 1.2), int(n * 0.8)           # план 50/50, факт ~60/40
    xA, xB = draw(rng, nA, sc["p0"]), draw(rng, nB, sc["p0"] + sc["lift"] * 0.8)
    sc = finish(sc, nA, nB, xA, xB, "Группа B показала рост конверсии, рекомендуем раскатить.")
    sc["notes"] = ["Соотношение групп по плану 50/50."]
    sc["key"] = dict(поле="мощность", исход=["скомпрометирован"], флаги=["srm"])
    return sc


def s_dilution(rng):
    for _ in range(300):
        sc = base(rng)
        sc["field"] = "0.8"
        n = sc["n_plan"]
        reach = 0.12
        xA, xB = draw(rng, n, sc["p0"]), draw(rng, n, sc["p0"] + sc["lift"] * reach)
        if pval(xA, n, xB, n) > 0.25 and interval(xA, n, xB, n)[2] < sc["lift"]:
            sc = finish(sc, n, n, xA, xB, "Значимых различий нет.")
            sc["notes"] = ["Предложение отправлено всей тестовой группе (%d клиентов); открыли сообщение %d клиентов "
                           "(%s), заметили предложение в кабинете %d." % (n, int(n * 0.31), pct(0.31), int(n * reach))]
            sc["key"] = dict(поле="мощность", исход=["заложенный_исключён"], флаги=["недошедшее"])
            return sc


def s_contam(rng):
    for _ in range(300):
        sc = base(rng)
        sc["field"] = "0.8"
        n = sc["n_plan"]
        xA, xB = draw(rng, n, sc["p0"] + sc["lift"] * 0.6), draw(rng, n, sc["p0"] + sc["lift"] * 0.8)
        if pval(xA, n, xB, n) > 0.3:
            sc = finish(sc, n, n, xA, xB, "Значимых различий между группами нет.")
            sc["notes"] = ["В ходе теста 18% клиентов контрольной группы получили то же предложение через обращение "
                           "в поддержку и воспользовались им."]
            sc["key"] = dict(поле="мощность", исход=["скомпрометирован"], флаги=["загрязнение"])
            return sc


def s_outliers(rng):
    sc = base(rng)
    n = int(rng.uniform(4000, 7000))
    mA = rng.randint(21000, 30000)
    sd = int(mA * 3.4)
    step = int(2.1 * sd * math.sqrt(2.0 / n))
    sc.update(metric_mean=True, nA=n, nB=n, mA=mA, mB=mA + step, sd=sd, trimA=int(mA * 0.62),
              trimB=int(mA * 0.62) + int(0.3 * sd * math.sqrt(2.0 / n)), p_raw="0,04", p_trim="0,62",
              verdict="Рост средней суммы значим на всей выборке; после усечения верхнего 1% по сумме значимость "
                      "исчезает: прирост держится на нескольких крупных клиентах.")
    sc["key"] = dict(поле=None, исход=["не_различимо"], флаги=["выбросы"])
    return sc


def s_two_expect(rng):
    for _ in range(300):
        sc = base(rng)
        sc["field"] = "0.8"
        n = sc["n_plan"]
        small = round(sc["lift"] * 0.6, 3)
        xA, xB = draw(rng, n, sc["p0"]), draw(rng, n, sc["p0"] + sc["lift"] * 0.3)
        d, lo, hi = interval(xA, n, xB, n)
        if pval(xA, n, xB, n) > 0.1 and small < hi < sc["lift"]:
            sc = finish(sc, n, n, xA, xB, "Значимого роста нет; рекомендуем переработать гипотезу.")
            sc["hyp_lift"] = small                # в гипотезе — меньший прирост, в таблице плана — больший
            sc["key"] = dict(поле="мощность", исход=["заложенный_исключён", "не_различимо"], флаги=["два_ожидания"])
            return sc


def s_no_verdict(rng):
    sc = base(rng)
    sc.update(no_results=True, verdict="Итоги не подводили, ждём ресурсов аналитиков.")
    sc["key"] = dict(поле=None, исход=["нет_данных"], флаги=["нет_итогов"])
    return sc


def s_not_payback(rng):
    for _ in range(300):
        sc = base(rng)
        sc["field"] = "0.8"
        n = sc["n_plan"]
        xA, xB = draw(rng, n, sc["p0"]), draw(rng, n, sc["p0"] + sc["lift"] * 1.1)
        if pval(xA, n, xB, n) < 0.02:
            sc = finish(sc, n, n, xA, xB, "Метрика прокрасилась. Затраты на предложение не окупаются: по расчёту окупаемость "
                                          "около 26 месяцев при плане 6.")
            sc["key"] = dict(поле="мощность", исход=["эффект_есть_не_окупается"], флаги=["не_окупается"])
            return sc


SCENARIOS = [s_beta_null, s_weak, s_true_pos, s_slice_fp, s_srm, s_dilution, s_contam, s_outliers, s_two_expect,
             s_no_verdict, s_not_payback]


# ---------- текст отчёта ----------
def render(sc, style):
    offer, metric = sc["dom"]
    t = {0: ("Гипотеза", "Группы", "Метрики", "План теста", "Итоги теста", "Выводы"),
         1: ("Hypothesis", "Groups", "Metrics", "Pre-test", "Post-test", "Result"),
         2: ("Описание", "Кто участвует", "Что измеряем", "Расчёт выборки", "Что получилось", "Заключение")}[style]
    L = ["# Тест: %s" % offer]
    if sc.get("metric_mean"):
        L.append("\n## %s\nЕсли клиентам предложить «%s», то средняя сумма заказа вырастет на 8%%." % (t[0], offer))
        metric = "средняя сумма заказа"
    else:
        lift_h = sc.get("hyp_lift", sc["lift"])
        L.append("\n## %s\nЕсли клиентам предложить «%s», то %s вырастет на %s п.п. (с %s до %s)." % (
            t[0], offer, metric, ("%.1f" % (100 * lift_h)).replace(".", ","), pct(sc["p0"]), pct(sc["p0"] + lift_h)))
    L.append("\n## %s\nA: контроль, предложения нет. B: получили предложение." % t[1])
    L.append("\n## %s\nОсновная: %s. Альфа 0,05." % (t[2], metric))
    if sc.get("field") is not None:
        L.append("\n## %s\n| Показатель | Значение |\n|---|---|\n| Текущая основная метрика | %s |\n"
                 "| Ожидаемая основная метрика | %s |\n| Альфа | 0.05 |\n| Мощность (1 - бета) | %s |\n"
                 "| Группа минимум | %d |\n| Группа A/B факт | %s |" % (
                     t[3], pct(sc["p0"]), pct(sc["p0"] + sc["lift"]), sc["field"], sc["n_plan"],
                     "%d/%d" % (sc["nA"], sc["nB"]) if "nA" in sc else "—"))
    else:
        L.append("\n## %s\nРасчёт выборки в карточке не приведён." % t[3])
    L.append("\n## %s" % t[4])
    if sc.get("no_results"):
        L.append("Тест проведён, итогов в карточке нет.")
    elif sc.get("metric_mean"):
        L.append("| Показатель | Группа A | Группа B | p-value |\n|---|---|---|---|\n"
                 "| Клиентов | %d | %d | |\n| Средняя сумма, руб. | %d | %d | %s |\n"
                 "| Средняя сумма без верхнего 1%%, руб. | %d | %d | %s |\n"
                 "Стандартное отклонение суммы около %d руб." % (
                     sc["nA"], sc["nB"], sc["mA"], sc["mB"], sc["p_raw"], sc["trimA"], sc["trimB"], sc["p_trim"], sc["sd"]))
    else:
        L.append("| Группа | Клиентов | Выполнили | Доля |\n|---|---|---|---|\n| A | %d | %d | %s |\n"
                 "| B | %d | %d | %s |\np-value: %.3f" % (
                     sc["nA"], sc["xA"], pct(sc["xA"] / sc["nA"]), sc["nB"], sc["xB"], pct(sc["xB"] / sc["nB"]), sc["p"]))
        if sc["slices"]:
            L.append("\nПо сегментам:\n| Сегмент | A | B | p-value |\n|---|---|---|---|")
            for nm, a_n, b_n, a, b, p in sc["slices"]:
                L.append("| %s | %d/%d | %d/%d | %.3f |" % (nm, a, a_n, b, b_n, p))
    for note in sc["notes"]:
        L.append("\n" + note)
    L.append("\n## %s\n%s" % (t[5], sc["verdict"]))
    return "\n".join(L) + "\n"


def make(a):
    rng = random.Random(a.seed)
    order = list(range(len(SCENARIOS)))
    rng.shuffle(order)
    ids = ["T-%02d" % (i + 1) for i in range(len(SCENARIOS))]
    rng.shuffle(ids)
    os.makedirs(a.reports, exist_ok=True)
    key = {}
    for fid, idx in zip(ids, order):
        sc = SCENARIOS[idx](random.Random(a.seed * 1000 + idx))
        if sc is None:
            sys.exit("polygon: сценарий %s не собрался при seed %d — возьми другой seed" % (SCENARIOS[idx].__name__, a.seed))
        open(os.path.join(a.reports, fid + ".md"), "w", encoding="utf-8").write(render(sc, rng.randint(0, 2)))
        key[fid] = dict(sc["key"], сценарий=SCENARIOS[idx].__name__[2:])
    os.makedirs(os.path.dirname(os.path.abspath(a.key_out)), exist_ok=True)
    json.dump(key, open(a.key_out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if a.task:
        os.makedirs(a.task, exist_ok=True)
        open(os.path.join(a.task, "00-tz.md"), "w", encoding="utf-8").write(
            "ТЗ (синтетический полигон)\n\nGAP:\n  1. Что показал каждый из экспериментов и мог ли он увидеть "
            "заложенный эффект [ключевой] {ответ: контекст}\n\nСИНТЕТИКА: отчёты выдуманы, свидетельством не являются.\n"
            "СОГЛАСОВАНО: полигон\n")
        for fid in sorted(key):
            subprocess.run([sys.executable, os.path.join(HERE, "add_source.py"), "--task", a.task, "--kind", "context",
                            "--location", os.path.join(a.reports, fid + ".md"), "--ctx-type", "result",
                            "--author", "синтетика", "--pub-date", "unknown", "--status", "final"],
                           check=True, capture_output=True)
    print("сценариев: %d, отчёты: %s, ключ: %s" % (len(key), a.reports, a.key_out))


# ---------- сверка ----------
def parse(text):
    out = {}
    for line in text.splitlines():
        parts = [p.strip().strip("`") for p in line.strip().lstrip("-*• ").split("|")]
        if not parts or not parts[0].startswith("T-"):
            continue
        rec = {"поле": None, "исход": None, "флаги": []}
        for p in parts[1:]:
            k, _, v = p.partition("=")
            k, v = k.strip(), v.strip().strip("[]")
            if k == "поле":
                rec["поле"] = None if v in ("", "—", "-", "нет") else v
            elif k == "исход":
                rec["исход"] = v
            elif k == "флаги":
                rec["флаги"] = [x.strip() for x in v.split(",") if x.strip() and x.strip() not in ("—", "-", "нет")]
        out[parts[0]] = rec
    return out


def f1(got, want):
    got, want = set(got), set(want)
    if not got and not want:
        return 1.0
    tp = len(got & want)
    if not tp:
        return 0.0
    pr, rc = tp / len(got), tp / len(want)
    return 2 * pr * rc / (pr + rc)


def score(a):
    key = json.load(open(a.key, encoding="utf-8"))
    ans = parse(open(a.answer, encoding="utf-8").read())
    rows, s_out, s_field, s_flags, n_field = [], 0.0, 0.0, 0.0, 0
    for fid in sorted(key):
        k, g = key[fid], ans.get(fid, {"поле": None, "исход": None, "флаги": []})
        o = 1.0 if g["исход"] in k["исход"] else 0.0
        fl = f1(g["флаги"], k["флаги"])
        if k["поле"] is not None:
            n_field += 1
            f = 1.0 if g["поле"] == k["поле"] else 0.0
            s_field += f
        else:
            f = None
        s_out += o
        s_flags += fl
        rows.append("%-5s %-14s исход %-4s поле %-4s флаги %.2f   (ключ: %s / %s / %s)" % (
            fid, k["сценарий"], "ок" if o else "МИМО", "—" if f is None else ("ок" if f else "МИМО"), fl,
            "|".join(k["исход"]), k["поле"] or "—", ",".join(k["флаги"]) or "—"))
    n = len(key)
    print("\n".join(rows))
    acc = s_out / n
    print("\nточность по исходу: %.0f%% (%d из %d)" % (100 * acc, s_out, n))
    print("точность по полю мощности: %s" % ("%.0f%% (%d из %d)" % (100 * s_field / n_field, s_field, n_field) if n_field else "—"))
    print("флаги (F1): %.2f" % (s_flags / n))
    return 1 if (a.min and acc < a.min) else 0



# ---------- карта документов: полнота тегов map_docs.py ----------
# Строки с заранее известным тегом. Часть форм нарочно трудная (числа словами, таблицы, «в два раза»): полигон
# меряет, сколько ловит скрипт, а не подгоняет шаблоны под него.
MAP_LINES = {
    "число": ["Конверсия {p}% против {q}%", "В опросе {n} респондентов", "Ответили {a} / {b}",
              "p-value 0.{x}, различий нет", "Средний чек {n} тыс. руб", "Отток {p}% за квартал",
              "Выручка выросла на {p} п.п.", "<table><tr><td>Группа {g}</td><td>{a} / {b}</td></tr></table>",
              "Каждый третий клиент ушёл", "Отток вырос в два раза"],
    "срез": ["Среди новичков картина другая", "Для ИП с оборотом до {n} млн", "Сегмент малых команд",
             "Активные клиенты ведут себя иначе", "Портрет: владелец сам ведёт учёт", "У ООО доля выше"],
    "продукт": ["Тариф включает выгрузку в 1С", "Лимит на переводы — {n} тыс.", "Подписка продлевается сама",
                "Комиссия за перевод не взимается", "Виртуальная карта выпускается за минуту"],
    "риск": ["Ограничение: выборка мала", "Мощность теста низкая", "Эффект не значим", "Риск: самовозврат",
             "Акция может не окупиться"],
}
MAP_NEUTRAL = ["Документ подготовила команда продукта", "Ниже — описание процесса", "Встреча прошла в среду",
               "Вопросы обсуждали по очереди", "Итоги записаны в протокол"]


def map_recall(a):
    sys.path.insert(0, HERE)
    from map_docs import clean, tags
    rng = random.Random(a.seed)
    stats = {t: [0, 0] for t in MAP_LINES}
    false_pos, neutral = 0, 0
    missed = []
    for _ in range(a.docs):
        for tag, forms in MAP_LINES.items():
            for form in forms:
                raw = form.format(p=rng.randint(2, 60), q=rng.randint(2, 60), n=rng.randint(12, 900),
                                  a=rng.randint(10, 400), b=rng.randint(500, 6000), x=rng.randint(10, 99),
                                  g=rng.choice("ABCD"))
                for line in clean(raw) or [raw]:
                    stats[tag][1] += 1
                    if tag in tags(line):
                        stats[tag][0] += 1
                    elif form not in missed:
                        missed.append(form)
        for line in MAP_NEUTRAL:
            neutral += 1
            false_pos += bool(tags(line))
    hit = sum(h for h, _ in stats.values())
    total = sum(n for _, n in stats.values())
    print("| Тег | Поймано | Из | Полнота |\n| --- | --- | --- | --- |")
    for t, (h, n) in stats.items():
        print("| %s | %d | %d | %.2f |" % (t, h, n, h / n))
    print("\nПолнота всего: %.2f; ложных тегов на нейтральных строках: %d из %d." % (hit / total, false_pos, neutral))
    if missed:
        print("Не ловит формы: " + "; ".join(missed[:8]))
    return 1 if a.min and hit / total < a.min else 0


# ---------- интервью: заложенные сигналы и сверка разбора ----------
SIGNALS = {
    "обход": ["Сейчас мы всё сводим в таблицу вручную, раз в неделю, по вечерам.",
              "Пока выкручиваемся: бухгалтер пересылает выписки в мессенджер, я переношу руками."],
    "триггер": ["Искать начали, когда ушёл бухгалтер и мы сорвали срок отчёта.",
                "Всё поменялось после проверки: штраф был, и тогда решили, что так нельзя."],
    "слова_против_поведения": ["Пользуемся каждый день, очень удобно.|Если честно, последний раз открывали в прошлом месяце.",
                               "Для нас это важнейший инструмент.|Ну, отчёт оттуда мы так ни разу и не выгрузили."],
    "альтернатива": ["Смотрели ещё одну систему, но там надо всё настраивать самим.",
                     "Думали нанять человека на полставки вместо всего этого."],
    "цена": ["Больше трёх тысяч в месяц за такое платить не готовы.",
             "Если будет дороже нынешнего тарифа, директор не подпишет."],
    "барьер": ["Боимся, что сотрудники не перейдут и будут вести по-старому.",
               "Главное — чтобы не пришлось переносить архив за пять лет."],
}
FILLER_Q = ["Расскажите, чем занимается компания?", "Кто у вас отвечает за учёт?", "Как устроен обычный месяц?",
            "Что было дальше?", "А как сейчас?"]
FILLER_A = ["Мы небольшая команда, человек двенадцать.", "В основном я сам, иногда помогает партнёр.",
            "В начале месяца закрываем документы, потом спокойнее.", "Да как обычно, ничего особенного.",
            "Работаем, клиенты есть, растём понемногу."]


def make_interviews(a):
    rng = random.Random(a.seed)
    os.makedirs(a.out, exist_ok=True)
    key = {}
    for i in range(1, a.n + 1):
        iid = "И-%02d" % i
        chosen = sorted(rng.sample(sorted(SIGNALS), rng.randint(2, 4)))
        lines = []
        for _ in range(rng.randint(2, 3)):
            lines += ["Интервьюер: " + rng.choice(FILLER_Q), "Респондент: " + rng.choice(FILLER_A)]
        late = []
        for s in chosen:
            phrase = rng.choice(SIGNALS[s])
            if "|" in phrase:  # слова в начале, поведение — позже, через несколько реплик
                first, second = phrase.split("|")
                lines += ["Интервьюер: Как часто пользуетесь?", "Респондент: " + first]
                late.append(second)
            else:
                lines += ["Интервьюер: " + rng.choice(FILLER_Q), "Респондент: " + phrase]
        for _ in range(rng.randint(1, 2)):
            lines += ["Интервьюер: " + rng.choice(FILLER_Q), "Респондент: " + rng.choice(FILLER_A)]
        for j, said in enumerate(late):
            q = "Когда последний раз что-то выгружали?" if j == 0 else "А ещё?"
            lines += ["Интервьюер: " + q, "Респондент: " + said]
        open(os.path.join(a.out, iid + ".md"), "w", encoding="utf-8").write(
            "# Интервью %s (выдуманное, полигон)\n\n" % iid + "\n".join(lines) + "\n")
        key[iid] = chosen
    os.makedirs(os.path.dirname(os.path.abspath(a.key_out)), exist_ok=True)
    json.dump(key, open(a.key_out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("интервью: %d, папка: %s, ключ: %s; сигналы: %s" % (len(key), a.out, a.key_out, ", ".join(sorted(SIGNALS))))
    return 0


def score_interviews(a):
    key = json.load(open(a.key, encoding="utf-8"))
    text = open(a.answer, encoding="utf-8").read()
    got = {}
    block = text.split("СВЕРКА", 1)[1] if "СВЕРКА" in text else ""
    for line in block.splitlines():
        parts = [x.strip() for x in line.split("|")]
        if len(parts) >= 2 and parts[0].startswith("И-") and "=" in parts[1]:
            got[parts[0]] = {s.strip() for s in parts[1].split("=", 1)[1].split(",") if s.strip()}
    scores = []
    print("| Интервью | Ключ | Ответ | F1 |\n| --- | --- | --- | --- |")
    for iid in sorted(key):
        want, have = set(key[iid]), got.get(iid, set())
        tp = len(want & have)
        f = 2 * tp / (len(want) + len(have)) if want or have else 1.0
        scores.append(f)
        print("| %s | %s | %s | %.2f |" % (iid, ", ".join(sorted(want)), ", ".join(sorted(have)) or "—", f))
    avg = sum(scores) / len(scores) if scores else 0
    print("\nСредний F1 по сигналам: %.2f" % avg)
    return 1 if a.min and avg < a.min else 0

def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make")
    m.add_argument("--seed", type=int, default=1)
    m.add_argument("--reports", required=True, help="папка для отчётов")
    m.add_argument("--key-out", required=True, help="файл ключа ответов (вне папки отчётов)")
    m.add_argument("--task", default="")
    s = sub.add_parser("score")
    s.add_argument("--key", required=True)
    s.add_argument("--answer", required=True)
    s.add_argument("--min", type=float, default=0.0)
    mr = sub.add_parser("map-recall")
    mr.add_argument("--seed", type=int, default=1)
    mr.add_argument("--docs", type=int, default=5)
    mr.add_argument("--min", type=float, default=0.0)
    mi = sub.add_parser("make-interviews")
    mi.add_argument("--seed", type=int, default=1)
    mi.add_argument("--n", type=int, default=8)
    mi.add_argument("--out", required=True, help="папка для транскриптов")
    mi.add_argument("--key-out", required=True, help="файл ключа (вне папки транскриптов)")
    si = sub.add_parser("score-interviews")
    si.add_argument("--key", required=True)
    si.add_argument("--answer", required=True)
    si.add_argument("--min", type=float, default=0.0)
    a = p.parse_args()
    if a.cmd == "make":
        make(a)
        return 0
    if a.cmd == "map-recall":
        return map_recall(a)
    if a.cmd == "make-interviews":
        return make_interviews(a)
    if a.cmd == "score-interviews":
        return score_interviews(a)
    return score(a)


if __name__ == "__main__":
    sys.exit(main())
