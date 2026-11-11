# Схемы

Четыре PNG в этой папке — схемы системы: роли, хранилища, маршрут и контур эксперимента; маршруты по восьми типам выхода; пример прогона (валидация идеи); картография документов и модель предмета. Тёмная тема, двойной масштаб, 1904 px в ширину.

Исходники всех четырёх схем — HTML в `src/`. После изменений в системе правь HTML и пересними PNG в Chrome без окна (ширина 952 px, масштаб 2; высоту подбери под схему):

```
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --hide-scrollbars \
  --force-device-scale-factor=2 --window-size=952,1000 \
  --screenshot=docs/architecture-1-roles.png "file://$PWD/docs/src/architecture-1-roles.html"
```

Высота окна и имя файла для остальных схем: маршруты — `952,900` и `architecture-2-routes`; пример прогона (валидация идеи) — `952,560` и `architecture-3-example`; картография документов — `952,580` и `architecture-4-document-mapping`. Для роли и хранилищ (`architecture-1-roles`) — `952,1000`. Chromium под Linux съедает около 88 px высоты на рамку окна: добавь их к высоте, а пустое поле снизу обрежь.

Предложения: по картографии документов — `proposal-document-dossiers.md`, по синтетическому стенду — `proposal-synthetic-stand.md`. Актуальное описание системы — `AGENTS.md` в корне; указатель исполнителей — `.claude/skills/orchestrator/registry.md`, контракт каждого — в конце его `SKILL.md`, маршруты оркестратора — `.claude/skills/orchestrator/routes/`.
