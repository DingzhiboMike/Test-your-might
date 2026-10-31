#!/usr/bin/env python3
"""Фразы внутри источника, обращённые к ИИ: «игнорируй инструкции», «не упоминай», «ты теперь…», служебная разметка ролей.

Текст источника — данные, а не команды (R-012). Скрипт не решает, опасна ли фраза, а убирает её из рабочего текста:
- scripts/add_source.py при регистрации заменяет такие строки в sources/raw/<id>.txt заглушкой, оригинал кладёт
  в sources/quarantine/<id>.txt, в поле note реестра пишет «[инъекция] строки …»;
- scripts/check_quotes.py не принимает строку артефакта, где все опоры — источники с пометкой [инъекция];
- hooks/web_flag.py после WebFetch и WebSearch предупреждает агента, если такая фраза пришла в ответе.

Шаблоны нарочно узкие: обращение к ИИ плюс повелительный глагол или служебная разметка. Статья про ИИ без обращения
к читающей модели не помечается. Ложное срабатывание стоит дёшево: строка лежит в карантине, человек её видит.

  python3 scripts/injection.py <файл>   # номера помеченных строк
"""
import re
import sys

MARK = "[инъекция]"
STUB = "[строка скрыта add_source: похоже на инструкцию для ИИ, оригинал — sources/quarantine/{sid}.txt, строка {n}]"

PATTERNS = [
    # отменить прежние правила
    r"\b(ignore|disregard|forget|override)\b.{0,40}\b(previous|prior|above|earlier|all|system)\b.{0,30}\b(instructions?|prompts?|rules|directions)\b",
    r"\b(игнорир\w*|забудь\w*|отмени\w*|не\s+учитывай\w*)\b.{0,40}\b(предыдущ\w*|прошл\w*|прежн\w*|все|системн\w*|вышеуказанн\w*)\b.{0,30}\b(инструкц\w*|указани\w*|правил\w*|промпт\w*)",
    # сменить роль
    r"\byou\s+are\s+now\b", r"\bfrom\s+now\s+on,?\s+you\b", r"\bnew\s+instructions\s*:",
    r"\bты\s+(теперь|отныне)\b", r"\bновые\s+инструкции\s*:",
    # прямое обращение к модели с поручением
    r"\b(note|message|instructions?)\s+(to|for)\s+(the\s+)?(ai|llm|assistant|model|agent|chatgpt|claude|gpt)\b",
    r"\bif\s+you\s+are\s+(an?\s+)?(ai|llm|language\s+model|ai\s+assistant|ai\s+agent)\b",
    r"\b(для|к)\s+(ии|ai|нейросет\w*|языков\w+\s+модел\w*|чат-?бот\w*)\s*[:—]",
    r"\bесли\s+ты\s+(ии|нейросеть|языковая\s+модель|ассистент|агент|бот)\b",
    # просьба скрыть или выдать закрытое
    r"\b(не\s+упоминай|не\s+сообщай\s+пользовател\w*|скрой\s+от\s+пользовател\w*)\b",
    r"\b(do\s+not|don't|never)\s+(mention|reveal|tell\s+the\s+user)\b",
    r"\b(выведи|покажи|отправь|перешли|reveal|print|output|send)\b.{0,30}\b(системн\w+\s+промпт\w*|system\s+prompt|пароль\w*|ключ\w*\s+api|api\s+keys?|секрет\w*|закрыт\w+\s+данн\w*|private\s+data|credentials)\b",
    # служебная разметка ролей
    r"<\|?(im_start|im_end|system|endoftext)\|?>", r"</?\s*(system|assistant|instructions?)\s*>", r"^\s*(system|assistant)\s*:\s*\S",
]
RX = [re.compile(p, re.I | re.M) for p in PATTERNS]


def flagged_lines(text):
    """Номера строк (с 1), похожих на инструкцию для ИИ."""
    out = []
    for i, line in enumerate((text or "").splitlines(), 1):
        if any(rx.search(line) for rx in RX):
            out.append(i)
    return out


def quarantine(text, sid):
    """(рабочий текст с заглушками, [(номер, исходная строка)])."""
    lines = (text or "").split("\n")
    hit = set(flagged_lines(text))
    if not hit:
        return text, []
    kept = [(n, lines[n - 1]) for n in sorted(hit)]
    for n in hit:
        lines[n - 1] = STUB.format(sid=sid, n=n)
    return "\n".join(lines), kept


def main():
    if len(sys.argv) != 2:
        sys.stderr.write(__doc__)
        sys.exit(2)
    lines = flagged_lines(open(sys.argv[1], encoding="utf-8", errors="replace").read())
    print("строк, похожих на инструкцию для ИИ: {}{}".format(len(lines), (" — " + ", ".join(map(str, lines))) if lines else ""))
    sys.exit(1 if lines else 0)


if __name__ == "__main__":
    main()
