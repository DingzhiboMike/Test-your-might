# Схемы

Четыре PNG в этой папке — схемы системы: роли, хранилища, маршрут и контур эксперимента; маршруты по семи типам выхода; пример прогона (валидация идеи); картография документов и модель предмета. Тёмная тема, двойной масштаб, 1904 px в ширину.

Исходники всех четырёх схем — HTML в `src/`. После изменений в системе правь HTML и пересними PNG в Chrome без окна (ширина 952 px, масштаб 2; высоту подбери под схему):

```
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --hide-scrollbars \
  --force-device-scale-factor=2 --window-size=952,996 \
  --screenshot=docs/architecture-1-roles.png "file://$PWD/docs/src/architecture-1-roles.html"
```

Высота окна и имя файла для остальных схем: маршруты — `952,592` и `architecture-2-routes`; пример прогона (валидация идеи) — `952,544` и `architecture-3-example`; картография документов — `952,592` и `architecture-4-document-mapping`.

Предложение по картографии документов — `proposal-document-dossiers.md` в этой папке. Актуальное описание системы — `AGENTS.md` в корне; контракты скиллов — `.claude/skills/orchestrator/registry.md`.
