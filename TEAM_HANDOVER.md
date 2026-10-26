# Передача Alfa команде — 26 октября 2026

Репозиторий: https://github.com/holodnayazvezda/Alpha-Hackathon-97a673c845283079
Рабочая ветка: **main**. Приложение находится в `Alfa-Hackaton/`.

Репозиторий создан через браузер как отдельная публичная поставка текущего решения.
Прежний командный remote Nitospb остаётся историческим источником.
Исходники отправляются в новый `origin`, только ветка `main`; точный commit
проверяется командой `git log -1 --oneline`.
Начните с [AGENTS.md](AGENTS.md), затем [актуального отчёта](NEXT_AGENT_HANDOFF.md).
Отчёт содержит матрицу C01–C12, backlog W01–W09 и журнал с отдельными отметками
реализации и приёмки. Незавершённые пакеты намеренно оставлены незавершёнными.

## Что уже работает

- Next BFF → Python API: компании/профили/роли, персональная лента, реакции,
  сохранения, разбор, уточняющий вопрос, история и trace, цитаты/PDF, оценка ответа.
- Агент **grounded-agent-v14.1** отдельно проверяет каждый тезис и позицию банка.
  Даёт полезную условную оценку без обязательного опросника; точные суммы и
  неизвестные условия не выдумывает. Источники можно скопировать вместе с разбором.
- Отдельный Selenium live-worker РБК/Интерфакс → инкрементальные векторы →
  согласованная версия каталога → API reload без потери пользовательского state.
  Live-проверка относится к этим двум источникам, не ко всем адаптерам парсера.
- Группы публикаций с сохранением первоисточников, гибридный поиск материалов банка,
  online backup/restore SQLite, подготовленные инструменты оценки и обучения.

## Запуск из чистого checkout

Нужны Docker Engine/Desktop и Compose v2. Из корня репозитория:

```bash
cd Alfa-Hackaton
cp .env.example .env  # только при отсутствии .env
# Для генерации заполнить ALFA_API_KEY локально, ключ получить по закрытому каналу.
docker compose up --build -d
```

Откройте http://127.0.0.1:3000. Без полного комплекта данных запускается явно
помеченный **синтетический smoke-набор**. Без ключа генерация отключена.
Это проверка установки, а не финальный корпус. `ALFA_REQUIRE_FULL=1` запрещает
такую подстановку. Полные параметры, API и ограничения: [service/README](Alfa-Hackaton/service/README.md).
Для текущего Mac порт **9082**: `ALFA_WEB_PORT=9082 docker compose ps`.
Не запускайте второй API/worker на том же state/runtime и не применяйте `down -v`.

## Данные и состояние передаются отдельно от Git

**Git содержит исходники, конфигурации без ключей, тесты и документацию.**
Данные, модели, `.env`, runtime, логи, notes/feedback/jobs, браузерные профили и
окружения исключены. Нового полного data-release эта передача не создаёт.

- `full-snapshot-v1` на GitHub — старый комплект (6 095 новостей / 1 404 TG).
  `python3 tools/restore_release.py` восстанавливает именно его.
- Последний базовый корпус — 11 835 новостей / 1 412 TG; live-версия растёт.
  Срез health при передаче: 13 290 документов = 11 878 новостей + 1 412 TG,
  публикация 26.10.2026 09:56 МСК. Это наблюдение, не фиксированный размер релиза.
- Текущая полная установка на Mac: `Alfa-Hackaton/pipeline/output/` (базовый
  каталог, ranking, векторы/metadata, service-assets.sqlite, bank-semantic.sqlite,
  releases/current.json и неизменяемые generations), `data/reports/` (PDF).
  Точный контракт и проверка поколений: [PUBLICATION](Alfa-Hackaton/pipeline/PUBLICATION.md).
  Для переноса работающего каталога нужен согласованный снимок выбранного
  поколения, а не произвольные отдельные файлы во время публикации.
- Источники/CSV/исходный финальный ZIP и веса для пересборки описаны в
  [DATA_UPDATE](Alfa-Hackaton/pipeline/DATA_UPDATE.md) и разделе5 отчёта.
  Абсолютные Mac-пути там обозначают местоположение у владельца, их нет в checkout.
- Mutable state находится в Docker volume `alfa-hackaton_service-state`.
  Для передачи состояния использовать `python -m service.backup backup`,
  затем `docker cp` по инструкции service/README; не копировать живую БД без WAL.
  Передавать только команде. Ключи и персональные заметки не включать в Git.

Новые локальные комплекты: `distribution/online-serving-2026-10-26` (389МБ) и
`distribution/serving-training-kit-2026-10-26` (896МБ, модели+готовые training/data).
Проверены восстановление, отдельный API/PDF и training --check-only без обучения.
Инструкция: [SERVING_BUNDLE](tools/SERVING_BUNDLE.md). Они не публикуются автоматически
в GitHub. Полная пересборка из сырых очередей/taxonomy и внешняя/Linux-приёмка
остаются **W06.2–W06.3**. Внешний стенд и доступ жюри тоже отдельно.

## Карта документации

| Задача | Точка входа |
|---|---|
| Архитектура, API, запуск, бюджет, backup | [service/README](Alfa-Hackaton/service/README.md) |
| Полезная оценка и проверка отдельных тезисов | [PARTIAL_ASSESSMENTS](Alfa-Hackaton/service/PARTIAL_ASSESSMENTS.md) |
| Планирование, роли, механизмы, банк-поиск | [PLANNING](Alfa-Hackaton/service/PLANNING.md) |
| Происхождение данных и пересборка | [pipeline/README](Alfa-Hackaton/pipeline/README.md), [DATA_UPDATE](Alfa-Hackaton/pipeline/DATA_UPDATE.md) |
| Live-worker и его безопасный перезапуск | [LIVE](Alfa-Hackaton/pipeline/LIVE.md) |
| Атомарная публикация и reader leases | [PUBLICATION](Alfa-Hackaton/pipeline/PUBLICATION.md) |
| Группы событий и числовые варианты | [STORIES](Alfa-Hackaton/pipeline/STORIES.md) |
| Парсер и контракт статей | [parser/AGENTS](Alfa-Hackaton/parser/AGENTS.md), [parser/README](Alfa-Hackaton/parser/README.md) |
| Интерфейс | [frontend/AGENTS](Alfa-Hackaton/frontend/AGENTS.md), [frontend/README](Alfa-Hackaton/frontend/README.md) |
| Независимая оценка и ручной gold | [evaluation/README](Alfa-Hackaton/evaluation/README.md) |
| Будущее обучение | [training/AGENTS](Alfa-Hackaton/training/AGENTS.md), [RUNBOOK](Alfa-Hackaton/training/RUNBOOK.md), [DATASET_CARD](Alfa-Hackaton/training/DATASET_CARD.md), [ANNOTATION](Alfa-Hackaton/training/ANNOTATION.md) |
| Лицензии и зависимости | [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES.md) |

SERVICE_AUDIT.md — исторический аудит. Последние записи NEXT_AGENT_HANDOFF имеют
приоритет перед прежними сведениями о v8, остановленных процессах и запрете push.

## Что делать следующим

1. Получить полный актуальный комплект данных вне Git и закрыть W06.2–W06.3.
2. Закрыть W02: независимые одобренные экспертные оценки, baseline и метрики.
   Сейчас approved gold отсутствует, точность бизнеса не измерена.
3. W03.5: память явных условий и разница ответов реализованы в v14.1;
   [границы extractor и живая проверка](Alfa-Hackaton/service/DIALOGUE.md).
   Локальные tests проходят, успешная живая LLM-приёмка ещё нужна.
4. Продолжить W04: проверка групп событий/конфликтов и качества банк-RAG.
5. Пройти UX/mobile и внешнюю приёмку W05/W07/W08. Локальный user_id не заменяет
   настоящую авторизацию; перед интернет-размещением нужны TLS и серверные права.

Единицы REVENUE_COMPANY **неизвестны** — не выводить порог15млрд и валюту.
Telegram не смешивать с новостным ML-training. Обучение E5 **не запускать без
отдельной команды пользователя**. Старые месячные/TG очереди и отменённые квоты
не возобновлять. Работающий отдельный live-worker не останавливать без причины.
Оригинальные ZIP/ID/hashes сохранять. Меняя функцию, обновлять журнал и её отметки.

## Проверка перед передачей

Из `Alfa-Hackaton/`, Python3.12 с `service/requirements.lock`:

```bash
python -m unittest discover -s service/tests -v
python -m unittest discover -s recommendations -p 'test_*.py'
python -m unittest discover -s insight_generation -p 'test_*.py'
python -m unittest discover -s pipeline -p 'test_*.py'
python -m unittest discover -s evaluation -p 'test_*.py'
python -m service.smoke --base http://127.0.0.1:9082/api/live
npm --prefix frontend ci
npm --prefix frontend run lint
npm --prefix frontend run build -- --webpack
```

Проверены перед передачей: service53, recommendations27, insight_generation16,
pipeline28, evaluation7 — все прошли (131 тест). BFF smoke прошёл: 11 проверок,
без пропусков и LLM-вызовов. Проверка Git-кандидатов: 130 файлов, без локальных
ключей/токенов, баз данных, весов и runtime. Ссылки основных документов проверены.
Последняя правка кнопки: lint и production
Docker/TypeScript build прошли, HTTP200. Browser/mobile визуальная приёмка последних
правок недоступна в этой среде и не заявляется выполненной. Платных LLM-вызовов
для передачи не делали; предыдущие ограниченные live-проверки описаны в отчёте.
Локальные свидетельства `/.release-downloads/handover-*-tests.log` относительно
корня репозитория не публикуются; результаты воспроизводятся командами выше.
Workflow `.github/workflows/service.yml` запускает синтетические проверки при push;
его результат проверять отдельно, наличие workflow не означает успешный remoteCI.

## Новый этап v14.1

Слепой экспертный пилот: `Alfa-Hackaton/pipeline/output/evaluation-pilot-2026-10-26/reviewer.html`,
20компаний/257заданий, gold0. Не выдавать validation за test.
Калькулятор процентных/валютных сценариев и scoped история доступны в разборе:
[SCENARIOS](Alfa-Hackaton/service/SCENARIOS.md).
Контрольные тесты:66service+28recommendations+16insight+28pipeline+10evaluation+8tools.
Последний smoke14 проверок, без платных вызовов. Исторические числа выше относятся
к предыдущей передаче. Изменения/ограничения зафиксированы в журнале отчёта.

Полный текущий ZIP: `distribution/alfa-team-handover-2026-10-26-v14.1.zip`
(около919МБ), SHA рядом в `.zip.sha256`. Источник внутри — e5662f7; последние
уточнения документации доступны в Git. Начать со START_HERE.md внутри ZIP.
Для e5662f7 **оба GitHub CI прошли**, включая clean Ubuntu Docker smoke:
[новый репозиторий](https://github.com/holodnayazvezda/Alpha-Hackathon-97a673c845283079/actions/runs/40307914474),
[командный](https://github.com/Nitospb/hack-sh4252sh234-a9f2/actions/runs/40307928416).
Полный корпус проверен локально на Mac, Linux CI использует synthetic seed.
