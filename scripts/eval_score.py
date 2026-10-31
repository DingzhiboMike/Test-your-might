#!/usr/bin/env python3
"""Оценка итоговых выводов прогона по замороженному кейсу: не форма, а то, к чему пришла система.

  python3 scripts/eval_score.py tasks/<папка> evals/cases/<кейс>
  python3 scripts/eval_score.py tasks/<папка> evals/cases/<кейс> --expert "корректность=4 полнота=3 шаги=5"

Кейс — папка с key.json (формат — evals/README.md): что должно найтись в выводах (must), в какие ловушки система
может попасть (traps), какие рекомендации неприемлемы (forbidden), известный исход эксперимента и что ему противоречит
(outcome). Шаблоны — регулярные выражения без учёта регистра по тексту итоговых артефактов (ARTIFACTS или key.artifacts),
абзац за абзацем.

Что считает скрипт:
- полнота — доля must, которые нашлись;
- ловушки и неприемлемые рекомендации — сколько сработало;
- противоречие исходу — абзацы с шаблоном из outcome.contradicts;
- причинные выводы без опоры — абзацы с причинным словом (из-за, потому что, приводит к…), где независимых корней
  опор (реестр, как в check_quotes.py) меньше key.causal_min_roots (по умолчанию 2);
- завышенная уверенность — абзацы с «уверенность: высокая», где корней меньше трёх (web-protocol.md, п. 4).
Оценку эксперта скрипт не ставит: её передают флагом --expert, она пишется в отчёт рядом с метриками.

Отчёт — evals/results/<кейс>--<папка задачи>.md (в git не попадает; другая папка — --out <папка>). Код возврата 0 — это измерение, а не проверка
готовности; 2 — нет кейса или ключ не по формату.
"""
import datetime
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from check_quotes import QUOTE_RE, load_registry, root_of  # noqa: E402

ARTIFACTS = ("02c-validation.md", "02d-validation2.md", "02e-position.md", "02f-forecast.md", "02g-ideas-check.md",
             "03-backlog.md", "06-research.md", "06-validation.md", "07*.md", "08-handoff.md")
CAUSAL = (r"\bиз-за\b|\bпотому что\b|\bприводит к\b|\bпривел\w* к\b|\bвызван\w*\b|\bв результате\b|\bблагодаря\b"
          r"|\bbecause\b|\bdue to\b|\bleads? to\b|\bcaused\b")
HIGH = re.compile(r"уверенност\w*\s*[:—-]?\s*высок", re.I)
LISTS = ("must", "traps", "forbidden")


def fail(msg):
    sys.stderr.write("eval_score: " + msg + "\n")
    sys.exit(2)


def load_key(case):
    path = os.path.join(case, "key.json")
    if not os.path.exists(path):
        fail("нет %s" % path)
    try:
        key = json.load(open(path, encoding="utf-8"))
    except ValueError as e:
        fail("key.json не JSON: %s" % e)
    for name in LISTS:
        for i, item in enumerate(key.get(name, [])):
            if not isinstance(item, dict) or not item.get("id") or not item.get("pattern"):
                fail("%s[%d]: нужны id и pattern" % (name, i))
            try:
                re.compile(item["pattern"])
            except re.error as e:
                fail("%s %s: шаблон не компилируется: %s" % (name, item["id"], e))
    return key


def paragraphs(task, masks):
    out = []
    for mask in masks:
        for path in sorted(glob.glob(os.path.join(task, mask))):
            text = open(path, encoding="utf-8").read()
            line = 1
            for block in re.split(r"\n\s*\n", text):
                if block.strip():
                    out.append((os.path.basename(path), line, block))
                line += block.count("\n") + 2
    return out


def roots(block, reg):
    return {root_of(s, reg) for _, s in QUOTE_RE.findall(block) if s in reg}


def where(hits):
    return ", ".join("%s:%d" % (f, n) for f, n, _ in hits[:3]) + (" …" if len(hits) > 3 else "")


def score(task, case, expert="", rdir=None):
    key = load_key(case)
    paras = paragraphs(task, key.get("artifacts") or ARTIFACTS)
    if not paras:
        fail("в %s нет итоговых артефактов (%s)" % (task, ", ".join(key.get("artifacts") or ARTIFACTS)))
    reg = load_registry(task)

    def found(pattern):
        rx = re.compile(pattern, re.I | re.M)
        return [p for p in paras if rx.search(p[2])]

    res = {name: [(item, found(item["pattern"])) for item in key.get(name, [])] for name in LISTS}
    outcome = key.get("outcome") or {}
    contra = [h for pat in outcome.get("contradicts", []) for h in found(pat)]
    causal_rx = re.compile(key.get("causal_markers") or CAUSAL, re.I)
    need = int(key.get("causal_min_roots", 2))
    causal = [p for p in paras if causal_rx.search(p[2])]
    weak = [p for p in causal if len(roots(p[2], reg)) < need]
    high = [p for p in paras if HIGH.search(p[2])]
    over = [p for p in high if len(roots(p[2], reg)) < 3]

    must_hit = sum(1 for _, h in res["must"] if h)
    m = {"полнота": "%d из %d" % (must_hit, len(res["must"])),
         "ловушки": sum(1 for _, h in res["traps"] if h),
         "неприемлемые рекомендации": sum(1 for _, h in res["forbidden"] if h),
         "противоречие исходу": len(contra),
         "причинные выводы без опоры": "%d из %d" % (len(weak), len(causal)),
         "завышенная уверенность": "%d из %d" % (len(over), len(high))}
    out = ["# Оценка прогона: %s · %s" % (os.path.basename(case.rstrip("/")), os.path.basename(task.rstrip("/"))), "",
           "Дата: %s. Абзацев в итоговых артефактах: %d." % (datetime.date.today().isoformat(), len(paras)), "",
           "| Метрика | Значение |", "| --- | --- |"]
    out += ["| %s | %s |" % (k, v) for k, v in m.items()]
    out += ["| оценка эксперта | %s |" % (expert or "не выставлена")]
    for name, title in (("must", "Должно найтись"), ("traps", "Ловушки"), ("forbidden", "Неприемлемые рекомендации")):
        if res[name]:
            out += ["", "## " + title]
            for item, hits in res[name]:
                ok = bool(hits) if name == "must" else not hits
                out.append("- %s %s — %s%s" % ("✓" if ok else "✗", item["id"], item.get("why", ""),
                                               (" (" + where(hits) + ")") if hits else ""))
    if outcome:
        out += ["", "## Исход эксперимента", "- " + outcome.get("text", "—"),
                "- противоречит: " + (where(contra) if contra else "нет")]
    if weak:
        out += ["", "## Причинные выводы, где опор меньше %d независимых" % need, "- " + where(weak)]
    if over:
        out += ["", "## «Уверенность: высокая» меньше чем на трёх корнях", "- " + where(over)]
    report = "\n".join(out) + "\n"
    rdir = rdir or os.path.join(os.path.dirname(HERE), "evals", "results")
    os.makedirs(rdir, exist_ok=True)
    name = "%s--%s.md" % (os.path.basename(case.rstrip("/")), os.path.basename(task.rstrip("/")))
    with open(os.path.join(rdir, name), "w", encoding="utf-8") as f:
        f.write(report)
    return report


def main():
    args = [a for a in sys.argv[1:]]
    opts = {}
    for flag in ("--expert", "--out"):
        if flag in args:
            i = args.index(flag)
            opts[flag] = args[i + 1] if i + 1 < len(args) else ""
            del args[i:i + 2]
    if len(args) != 2:
        sys.stderr.write(__doc__)
        return 2
    task, case = args[0].rstrip("/"), args[1].rstrip("/")
    if not os.path.isdir(task):
        fail("папки задачи нет: " + task)
    sys.stdout.write(score(task, case, opts.get("--expert", ""), opts.get("--out")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
