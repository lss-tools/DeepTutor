# FORKING.md — сопровождение форка DeepTutor (lss-tools)

Документ для следующего агента или владельца: что изменено относительно
upstream, как сливаться с upstream, что ломается при обновлении и как
проверять форк после слияния. История решений — в Brain, задача 1165
(`work/active/harnes/1165-Форк-DeepTutor-под-репетитора-ОГЭ/README.md`).

## Зачем форк

Платформа Этапа 2 ИИ-репетитора ОГЭ. От upstream (HKUDS/DeepTutor) нас
отличают две цели: русский интерфейс для девятиклассника и — в перспективе —
вложения (картинки/аудио/заготовки) в банк вопросов практики. Решение
владельца 10.10.2026: правки держим только в своём форке, PR в upstream не
оформляем; цена слияний принимается сознательно.

## Правила, нарушать нельзя

- Свои материалы — только в **новых** файлах, которых нет у upstream
  (`web/locales/ru/`, `tests/i18n/test_russian_locale.py`, этот файл).
  Правка `AGENTS.md`, `README.md`, `.gitignore` upstream = конфликт при
  каждом слиянии.
- `push` в `upstream` отключён намеренно (`DISABLED_no_push_to_upstream`).
- Каталог `.code-index/` закрыт через `.git/info/exclude`, не через
  `.gitignore` — см. факт `fact-20261010-cidx3` в Brain.
- Рабочая установка пакета в `D:\Project\deeptutor` — эталон «из коробки»,
  её не трогать; форк живёт в `D:\Project\deeptutor-fork`.
- Правки — атомарными коммитами; синхронизироваться с upstream регулярно,
  редкое слияние даёт крупный конфликт; merge, не rebase.

## Что изменено относительно upstream 6cf793bd (v1.6.14)

| Коммит | Что |
|---|---|
| `7fc7d069` | регистрация локали ru: `web/i18n/languages.ts` (+ `normalizeLanguage`), `web/i18n/init.ts` (ленивый импорт бандла), `deeptutor/services/settings/interface_settings.py` (`UiLanguage`, нормализатор), `deeptutor/services/config/launch_settings.py`, `deeptutor/services/config/settings_spec.py` (`_LANGUAGE_CHOICES`), ключ `language.russian` в `web/locales/en/app.json`, пол ru в `web/scripts/i18n_audit.mjs`, тест `web/tests/language-preferences.test.ts` |
| `d86d2538`…`4067fc4a` | полный русский каталог `web/locales/ru/app.json` (5538 ключей: 5508 из en + русские формы `_few`/`_many`) и `tests/i18n/test_russian_locale.py` |

`deeptutor/runtime/banner.py` сознательно не тронут: у баннера фолбэк на en,
fr и pl там тоже нет.

## Порядок слияния с upstream

```
git fetch upstream
git merge upstream/main        # merge, не rebase
```

Ожидаемые места конфликтов (по опыту этого слияния):

- `web/locales/en/app.json` — upstream добавит ключи. Конфликта почти не
  будет (мы меняли только одну строку `language.russian`), но после слияния
  ru отстанет от en: см. «Что ломается».
- `web/scripts/i18n_audit.mjs` — правьте только блок `MIN_USED_COVERAGE`.
- `web/i18n/languages.ts` и `web/i18n/init.ts` — если upstream добавит свою
  локаль, наши строки `ru` сохраняются рядом.
- `deeptutor/services/settings/interface_settings.py`,
  `launch_settings.py`, `settings_spec.py` — держим строку `ru` по образцу
  соседних локалей.

## Что ломается при обновлении

1. **Аудит strict.** Локаль без пола в `MIN_USED_COVERAGE` (de, zh, pl, ru)
   обязана переводить все используемые ключи. Новые en-ключи после слияния
   уронят гейт на ru с ошибкой «N t() literals lack a locale entry».
   Лечение: перевести новые ключи (список — `node scripts/i18n_audit.mjs
   --show-missing`), а не возвращать пол.
2. **Русские формы множественного числа.** В `ru/app.json` есть ключи
   `_few`/`_many`, которых нет в en — это норма (так же устроен pl).
   Не «чистить» их как мусор: без них i18next не разрешит множественное
   число по-русски.
3. **Тест `test_russian_locale.py`** требует `set(en) ⊆ set(ru)` — тот же
   сигнал, что и аудит.

## Проверка форка после слияния

```
cd web
npm ci
node scripts/i18n_audit.mjs      # все локали strict, включая ru: 100%
npm run test:node                # ~1300 тестов, включая language-preferences
cd ..
py -3.12 -m pytest tests/i18n    # пер-локальные suites, включая русский
```

Затем руками: поднять сервер, выбрать «Русский» в настройках, пройти экраны
чата, настроек и практики — формулировки смотрит владелец.

## Инструменты перевода (вне репозитория)

Порции и сборщик лежат в `D:\Brain\temp\1165-ru\`: `partNN.json` (переводы),
`merge_ru.py` (сборка `ru/app.json` в порядке en + проверка ключей,
интерполяций `{{...}}`, тождественных значений и полноты plural-форм),
`glossary.md` (термины перевода). Новые ключи переводить новой порцией
`partNN.json` и собирать тем же скриптом.
