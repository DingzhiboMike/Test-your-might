# Схема

`architecture.png` — общая схема: роли, хранилища, маршрут и контур эксперимента. Тёмная тема, ширина 1904 px (двойной масштаб).

Исходник — `src/architecture.html`. После изменений в системе правь HTML и переснимай PNG в Chrome без окна:

```
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --hide-scrollbars \
  --force-device-scale-factor=2 --window-size=952,1000 \
  --screenshot="$PWD/docs/architecture.png" "file://$PWD/docs/src/architecture.html"
```

Высоту окна подбирай под схему. Chromium под Linux съедает около 88 px на рамку окна: добавь их к высоте и обрежь пустое поле снизу.

`proposal-document-dossiers.md` — предложение по картографии документов. Актуальное описание системы — `AGENTS.md` в корне, внутреннее устройство — `INFRASTRUCTURE.md`.
