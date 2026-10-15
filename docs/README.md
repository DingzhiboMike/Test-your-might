# Схемы

Три PNG в этой папке — схемы системы: роли, хранилища, маршрут и контур эксперимента; маршруты по семи типам выхода; пример прогона (валидация идеи). Тёмная тема, двойной масштаб, 1904 px в ширину.

Исходники первых двух схем — HTML в `src/`. После изменений в системе правь HTML и пересними PNG в Chrome без окна (ширина 952 px, масштаб 2; высоту подбери под схему):

```
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --hide-scrollbars \
  --force-device-scale-factor=2 --window-size=952,996 \
  --screenshot=docs/architecture-1-roles.png "file://$PWD/docs/src/architecture-1-roles.html"
```

Для схемы маршрутов — `--window-size=952,572` и `architecture-2-routes`. У третьей схемы (пример валидации) исходника нет: маршрут валидации не менялся.

Актуальное описание системы — `AGENTS.md` в корне; контракты скиллов — `.claude/skills/orchestrator/registry.md`.
