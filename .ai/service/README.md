# Рабочий сервис новостной аналитики

Приложение объединяет ленту, реальные обезличенные профили, материалы банка,
персональный разбор, уточняющий диалог, журнал инструментов и обратную связь.
Дообучение E5 и новые сборы не запускаются при старте сервиса.

## Запуск через Docker

Для разработки без Docker и реальных данных используйте `./run_mock.sh` из
корня репозитория: Next.js dev и Python API получают только синтетический seed.
Описание и порты — в [общем README](../README.md).

Из корня репозитория, Docker Desktop/Engine с Compose v2:

```bash
cp .env.example .env                 # только если .env ещё нет
# Заполните ALFA_API_KEY локально; не добавляйте его в Git.
docker compose up --build -d
```

Открыть http://127.0.0.1:3000. Остановить: `docker compose down`.
`down` сохраняет named volume; **не используйте `down -v` для рабочего состояния**.
`ALFA_WEB_PORT=9082 docker compose up -d` позволяет выбрать свободный порт.
API доступен только во внутренней сети Compose, публичный порт есть у Next BFF.
Все процессы выполняются без root. Чтение ленты использует готовые векторы CPU,
поэтому Torch, GPU, Selenium и загрузка весов для online-запуска не нужны.

### CI/CD на SSH-сервер

Workflow `.github/workflows/service.yml` после успешных проверок на `main`
передаёт исходники через rsync в `/opt/alfahack`, выполняет там
`ALFA_REQUIRE_FULL=1 docker compose -f compose.yaml -f compose.production.yaml up --build -d --wait`
и проверяет `/api/live/health` через loopback. Его можно запустить вручную через
`workflow_dispatch`; pull request не развёртывается. SSH-пользователь должен
иметь право записи в `/opt/alfahack` и право выполнять `docker compose` без
`sudo`. На сервере также нужны Docker Compose v2, `curl` и существующая Docker
сеть `traefik_traefik_proxy`.

`compose.production.yaml` подключает только web-контейнер к сети Traefik,
создаёт HTTPS-маршрут `alfa.aezakmi.org` на порт контейнера 3000 через
entrypoint `websecure` и certresolver `le`. Middleware к маршруту не подключён.
Существующий локальный bind
`127.0.0.1:ALFA_WEB_PORT` остаётся для проверки на сервере.

До первого деплоя разместите на сервере каталоги `/opt/alfahack/pipeline/output`
и `/opt/alfahack/data`, а в `pipeline/output` —
готовые `catalog.sqlite` и `service-assets.sqlite` с остальными файлами
согласованного serving-комплекта. Способ подготовки комплекта описан в
[SERVING_BUNDLE.md](../tools/SERVING_BUNDLE.md). Содержимое серверного `.env`
задайте многострочным GitHub secret `DEPLOY_ENV_FILE`: workflow переносит его
как файл с правами `600` и атомарно заменяет `/opt/alfahack/.env` перед запуском.
В нём задаются `ALFA_API_KEY`, `ALFA_INTERNAL_TOKEN` и при необходимости
`ALFA_WEB_PORT`. Сам маршрут Traefik не проверяет права пользователя; для
внешнего доступа их нужно обеспечить отдельно.

В GitHub Actions задайте repository secrets `DEPLOY_HOST`, `DEPLOY_USER`,
`DEPLOY_SSH_KEY` (закрытый SSH-ключ), `DEPLOY_KNOWN_HOSTS` (запись host key,
проверенная по доверенному отпечатку), `DEPLOY_ENV_FILE` (полный текст `.env`)
и при нестандартном порте `DEPLOY_PORT`.
Публичный ключ добавьте в `authorized_keys` пользователя сервера. Рабочие
`.env`, `data/`, `pipeline/output/`, модели, runtime и SQLite исключены из
rsync; Compose volume `alfa-hackaton_service-state` сохраняется при обновлениях.
В остальных путях `/opt/alfahack` rsync удаляет файлы, отсутствующие в Git,
поэтому серверные конфигурации храните вне каталога приложения или в
перечисленных исключениях. Сборщики и обучение workflow не запускает.

Если полного каталога нет, контейнер создаёт небольшой **синтетический** набор
(две компании, шесть новостей); интерфейс явно сообщает об этом. Это проверка
установки и сценария, не корпус для обучения и не реальные банковские сведения.
Без ключа лента/профиль/сохранения работают, генерация отключена.
`ALFA_REQUIRE_FULL=1` запрещает синтетическую подстановку и завершает запуск при
отсутствии полного каталога. Секреты .env исключены из Docker build context.

### Полные данные

Релиз `full-snapshot-v1` восстанавливается скриптом `tools/restore_release.py`.
Он содержит прежний командный каталог. Более свежий локальный корпус описан в
[DATA_UPDATE.md](../pipeline/DATA_UPDATE.md); опубликованный старый релиз сам по
себе не становится обновлённым. Оригинальные ZIP не перезаписываются.

Compose монтирует:

| Путь хоста | Назначение | Доступ |
|---|---|---|
| `pipeline/output/` | catalog.sqlite, ranking.sqlite, article chunks/npy, service-assets.sqlite | read-only |
| `data/reports/` | оригинальные банковские PDF | read-only |
| named volume `service-state` | feedback.sqlite, service.sqlite, WAL и lock | read/write |

Для полной версии нужны catalog.sqlite и service-assets.sqlite. Векторы и
ranking.sqlite улучшают выдачу; при их отсутствии семантический режим будет
ограничен и явно указан в ответе ленты. Скрипт `smoke` проверяет реальный путь.

Подготовка клиентского контекста и OCR выполняется **один раз вне online API**:

```bash
python -m pip install -r service/requirements.lock
# Tesseract с rus+eng должен быть установлен оператором.
python -m service.prepare --output pipeline/output/service-assets.sqlite
```

Исходники: `data/dataset/df_Uid_data_hack.csv`,
`taxonomy/output/relationship_interests/relationships.jsonl`, `data/reports/`.
Можно задать `--csv`, `--relationships`, `--reports`, `--tessdata`.
`--skip-ocr` готовит только профили. Идентификаторы исходных строк сохраняются.
Публикуйте подготовленные assets при остановленном API атомарной заменой,
с резервной копией. Не пересчитывайте каталог поверх пользовательского feedback.
Новые векторы/каталог публикуйте согласованным поколением через pipeline.publication:
Snapshots подхватывает его в следующем запросе без перезапуска. При замене
service-assets/bank-semantic вне generation перезапустите API после backup.

## Запуск на Mac без Docker

Python 3.12, Node 22, установленные frontend-зависимости:

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r service/requirements.lock
cd frontend
npm ci
npm run build -- --webpack
cd ..
.venv/bin/python run_local.py --python .venv/bin/python --production
```

Для разработки убрать `--production`. Отдельно API:
`python recommendations/server.py --port 8091 --state /путь/к/feedback.sqlite`.
`ALFA_SERVICE_STATE` задаёт отдельный SQLite запусков и уточнений;
`ALFA_ASSETS` — индекс контекста/банка. По умолчанию используются папки каталога
и feedback. API получает .env из папки приложения; Next никогда не читает ключ.
`run_local.py` запускает только свои API/web, закрывает их по Ctrl+C и отказывается
занимать уже использованные порты. Не запускайте второй API с тем же service-state.

## Сценарий демонстрации

1. Главная → «Открыть новостную аналитику». Выбрать реальную компанию через
   поиск ID/ОКВЭД. Названий компаний в исходнике нет — вымышленные бренды не нужны.
2. `/profile`: проверить факты, происхождение и ограничения. Уточнения пользователя
   сохраняются сервером отдельно и рассматриваются как заявления, не как банковские факты.
3. `/settings`: выбрать роль. В ленте настроить личные темы, открыть новость.
   Сохранения, реакции и история пользователя изолированы в feedback.sqlite.
4. Из карточки → «Персональный разбор и диалог» → «Подготовить разбор».
   Запрос быстро получает run_id; интерфейс опрашивает статус, а лента не блокируется.
5. В ответе разделены событие, факты компании, позиция банка и AI-применение.
   Цитаты открывают исходную новость или страницу настоящего PDF.
6. Задать уточнение: создаётся дочерний запуск с предыдущим ответом и новым поиском.
   Неподтверждённая связь заканчивается needs_context/not_relevant, а не выдуманным эффектом.
7. `/trace`: реальные входы/выходы инструментов и измеренные времена.
   `/quality`: actual tokens/runs, реакции и пользовательские оценки разборов.

Например U_171 и U_206 имеют один ОКВЭД62.01, но различаются кредитным/ФТС
флагами. Такие наблюдения меняют приоритет и основания анализа; флаг не доказывает
плавающую ставку, размер долга или валюту договора. Единицы REVENUE_COMPANY не
подтверждены — не переводим их в рубли и не делаем вывод о сегменте >15млрд.
Платёжная доля не является долей рынка; GROUP_ID не доказывает владение.

## Контракт API

Браузер обращается к `/api/live/<endpoint>`, Next передаёт запрос Python API.
`company_id`, `source_record_id`, `user_id` задают контекст; в родительском запуске
также проверяется тот же article_id. Это тестовая идентичность прототипа, не IAM.

Интерактивная документация Swagger UI: `http://127.0.0.1:3000/docs` (или текущий
порт Next). Машиночитаемая схема: `/api/live/openapi.json`; напрямую во внутренней
сети Python API — `/openapi.json` с тем же внутренним токеном, что и остальные
маршруты. Swagger UI использует BFF и не показывает внутренний токен. Запросы
`POST /analysis`, `/chat`, `/insight` могут расходовать лимит платного LLM-шлюза.
Ответы со сложными данными компании/разбора пока описаны как JSON-объекты;
детальные схемы этих ответов остаются дальнейшей работой.

| Метод / endpoint | Параметры / результат |
|---|---|
| GET health | counts, версии, наличие LLM, synthetic/collected |
| GET companies | q, limit; поиск профилей |
| GET company / context | company_id, source_record_id; факты и provenance |
| GET feed | контекст, role, request_id, limit1..100, mode, scope, kind |
| GET article / news | article_id / q+kind+offset+limit |
| GET profile / saved | company_id, user_id; роль/темы/реакции/сохранения |
| POST profile / events | роль и topic_ids / article_id+kind+event_id |
| POST context | text или delete_id; запись/удаление уточнения |
| POST analysis | контекст+article_id+role →202 run_id |
| POST chat | то же +question+parent_run_id →202 run_id |
| GET runs / run | контекст [+run_id]; история/статус/результат/steps |
| POST review | контекст+run_id+rating(useful/incorrect/needs_review)+note |
| GET metrics | наблюдаемые показатели текущего профиля |
| GET bank-sources | документы и поиск по q, опционально as_of |
| GET bank-file | document_id →application/pdf; `#page=N` открывает страницу |

Состояния задачи: queued/running/complete/error/interrupted. Бизнес-результат:
ready/needs_context/not_relevant. `complete` означает завершённое исполнение,
не обязательно достаточность доказательств для персонального вывода.
Кэш учитывает новость, company/source_record/user, роль, версию фактов/модели/
агента/банк-индекса, вопрос/родителя и день анализа. Не меняйте параметры под
существующим request_id ленты. Дневные/временные ограничения проверяются при выдаче.

## Агент, источники и бюджет

Собственная оркестрация `runtime.py`, а не сторонний готовый агент:
plan по событию/экспозициям → context → search_bank → draft → verify_sources →
schema/ID/date/exact quotes. В запросах применяются короткие source aliases,
а наружу возвращаются неизменные канонические Article ID. При ошибке контракта
допускается одна ревизия в том же общем лимите двух draft, без сетевых retries. Решение retrieve запускает второй поиск и ревизию,
затем повторную проверку. Максимум два draft и два verify, без автоматических
повторов сетевых/платных ошибок. Неудачные шаги тоже присутствуют в журнале;
диагностика содержит тип/расположение сбоя, без секретов и provider-body.

FTS-поиск банка возвращает кандидатов; фрагменты с преобладанием распознанных
таблиц/графиков не используются как цитируемый текст. Оригинальные PDF доступны полностью. Только датированные документы за180дней
до as_of допускаются в payload. Отчёт2021года остаётся доступен в Sources, но
не применяется как текущий прогноз. OCR не равен проверке чисел по оригиналу.
Gold-обзор с непроверенной точной датой доступен как PDF, исключён из генерации.
Точные цитаты проверяются с нормализацией пробелов; LLM-проверка не заменяет эксперта.

Только разрешённые gateway URL и model IDs (`insight_generation/client.py`).
По умолчанию Qwen3.6. Параметр отключения thinking для этого шлюза
проверен по actual usage (reasoning_tokens=0); настройки совместимых шлюзов
могут различаться. См. [контракт reasoning](https://github.com/OpenRouterTeam/docs/blob/main/guides/best-practices/reasoning-tokens.mdx). В отдельном вызове контролируется корректность источников,
чтобы основной генеративный ответ не публиковался без проверки. Список моделей
не расширяется произвольными внешними провайдерами. Ключ только на сервере.

Очередь:2workers, максимум8принятых задач. Ledger calls хранит actual usage и
резервы на активные/прерванные запросы и ошибки без подтверждённого usage. Локально30calls/300000tokens в день;
лимиты настраиваются ALFA_MAX_CALLS_PER_DAY / ALFA_MAX_TOKENS_PER_DAY.
Резерв30000tokens на вызов — консервативный локальный ограничитель, не тариф.
Общий бюджет команды500₽/день контролирует шлюз, сброс03МСК. При budget error
включается circuit breaker до сброса. Расходы других участников локальный ledger
не видит; стоимость в рублях без документированного тарифа не рассчитывается.

## Проверки и ограничения

```bash
python -m unittest discover -s service/tests -v
python -m unittest discover -s recommendations -p 'test_*.py'
python -m unittest discover -s insight_generation -p 'test_*.py'
python -m service.smoke --base http://127.0.0.1:3000/api/live
```

Smoke сохраняет тестовые настройки/реакции только под новым smoke-user,
проверяет notes/delete/isolation/PDF, **не вызывает LLM**, не запускает сбор/обучение.
CI использует синтетический seed, локальные HTTP и fake transports. Платный
E2E выполняется оператором отдельно через интерфейс, не на каждом push.

Точность бизнес-выводов и relevance precision/nDCG требуют независимой ручной
оценки. Пустое значение метрики не заменяется демонстрационным графиком.
Отзывы пользователя не превращаются автоматически в обучающие/эталонные метки.
Общий корпус конечен: после исчерпания лента короче, повторы не добавляются ради24.

## Эксплуатация и безопасность прототипа

Секреты только .env/secret manager, origin/body limits на BFF, внутренний токен,
SQL с параметрами и scope в инструментах, read-only mounts каталога/PDF,
разделение пользовательского состояния и контента, bounded jobs/usage.
Сохранённый текст новости/банка/уточнения — данные, не инструкции агенту.

Loopback и локальные user_id — **не банковская авторизация**. До публикации в
интернет поставить authenticated TLS ingress; получать user/company permissions
из доверенной серверной сессии; заменить default internal token и ограничить
доступ к trace/платёжным фактам. Не выдавать прототип за production интернет-банк.
Контейнеры по умолчанию не публикуют интерфейс наружу.

Резервные копии: после остановки API скопировать весь state volume или выполнить
SQLite backup для feedback.sqlite и service.sqlite; живые WAL нельзя игнорировать.
Каталог и assets версионируются отдельно. Локальные логи/журнал содержат исходные
обезличенные факты: доступ только команде. В published logs/репозиторий их не включать.
Сборщики и тренировка остаются отдельными операторскими задачами; старт сервиса
не даёт команды возобновить ранее остановленный сбор.

## Проверенный локальный запуск — 26 октября 2026

Проверены production Docker build и CPU-запуск, полный и отдельный синтетический
smoke, 11 HTTP-маршрутов, frontend lint/TypeScript, тесты service/recommendations/
insight_generation/pipeline. В браузере пройдены восстановление компании,
персональный разбор с цитатой банка, уточняющий ответ со списком параметров
договора, сохранение оценки, история/parent и переход в trace текущего запуска.
Оба живых содержательных ответа завершились complete/needs_context: модель
объяснила условия и запросила неизвестные договорные данные, не рассчитав
выдуманные суммы. Это не измеренная точность на ручном эталоне.
Машинный отчёт: pipeline/output/service_validation.json (локальный, вне Git).
Ключ проверен на отсутствие в Git-кандидатах; исходный catalog.sqlite и прежний
feedback.sqlite сохранили SHA-256. Новые реакции/запуски Docker — в отдельном volume.
Этот раздел описывает первоначальную проверку сервиса. Текущая версия v13.2
и передача исходников описаны в [TEAM_HANDOVER](../TEAM_HANDOVER.md) и
[NEXT_AGENT_HANDOFF](../NEXT_AGENT_HANDOFF.md).
Опубликованный полный data-release full-snapshot-v1 не заменён.


## Развитие по backlog, 26.10

Согласованная публикация каталога с request-pinned reload описана в
[PUBLICATION](../pipeline/PUBLICATION.md). Она opt-in и сама не запускает сбор.
Offline рубрика/оценка ручных judgments и temporal split audit:
[evaluation](../evaluation/README.md). Пока нет ручного gold, показатели качества
остаются неизвестными. Актуальные отметки реализации — в корневом NEXT_AGENT_HANDOFF.md.

## Резервное копирование mutable state

`service.backup` делает online SQLite backup для feedback.sqlite/service.sqlite,
включая committed данные WAL. Каталог назначения должен быть новым. Манифест
фиксирует SHA и окно времени: каждая БД согласована транзакционно, единой
межбазовой транзакции у независимых state-файлов нет. Каталог/модели/ключи/Chrome
в этот bundle не попадают. Храните bundle с ограниченным доступом: в нём заметки,
история и контекст запросов пользователей.

```bash
python -m service.backup backup --state /absolute/state --bundle /absolute/backups/state-2026-10-26
python -m service.backup restore --bundle /absolute/backups/state-2026-10-26 --state /absolute/new-state
# Docker, backup остаётся в named volume; для внешней копии использовать docker cp:
docker compose exec -T api python -m service.backup backup --state /state --bundle /state/backups/state-2026-10-26
```

Restore проверяет SHA/integrity до записи и берёт service.lock. Существующие
SQLite/WAL не перезаписываются. Для восстановления подготовьте новую папку,
смонтируйте её вместо прежнего state после остановки API и проверьте smoke.
Доставку резервных копий на отдельный носитель/сервер выполняет оператор;
автоматического расписания backups пока нет. Проверка restore выполняется в
отдельной папке, рабочий volume не очищается.


Свежие новости подключены через [live-worker](../pipeline/LIVE.md). На текущем
Mac проверены РБК/Интерфакс; это не утверждение о непрерывной доступности всех
настроенных сайтов. API хранит файлы аренды читаемых generations в отдельном
writable reader-leases bind: flock между macOS и Docker Desktop недостаточен.
Условные механизмы/адресные вопросы v9: [PLANNING](PLANNING.md).

## Несколько публикаций и банковская экспертиза

[STORIES](../pipeline/STORIES.md) описывает группы публикаций, ограниченную
дедупликацию, числовые цитаты и сохранение всех первоисточников. Группы появляются
в reader и анализе. Разные домены не объявляются независимыми подтверждениями.
[PLANNING](PLANNING.md) описывает grounded-agent-v11 и гибридный банк-поиск по
словам и E5-вектору события. Отдельный semantic index готовится offline;
online-сервис не обучает и не загружает Torch. Актуальная проверка исполнения
не означает измеренное качество на независимом экспертном наборе.


Политика готовых оценок/частичных ответов v13.2:
[PARTIAL_ASSESSMENTS](PARTIAL_ASSESSMENTS.md). Каждый тезис и позиция банка
проверяются отдельно; полезная сценарная оценка показывается без обязательного
опроса о каждом параметре, а точный денежный эффект не выдумывается.

## Следующий этап v14

[Память явных уточнений](DIALOGUE.md), [калькулятор сценариев](SCENARIOS.md),
[переносимый serving bundle](../tools/SERVING_BUNDLE.md) и
[слепая экспертная оценка](../evaluation/README.md) реализованы отдельными модулями.
Полноту ручной приёмки и оставшиеся ограничения см. в NEXT_AGENT_HANDOFF.md.

Локальная ограниченная проверка нагрузки без LLM:
`python -m service.loadcheck --base http://127.0.0.1:9082/api/live --requests 16 --workers 4`.
Допускаются только loopback адреса и ограниченный параллелизм. Измеряет HTTP
health/feed и создаёт служебную историю только для отдельного loadcheck-user;
не измеряет ёмкость production/скорость Selenium/шлюза.

Доступность новых анализов и резерв на verifier: [BUDGETS](BUDGETS.md).
Health теперь учитывает реальный ledger и занятый ресурс, а не только наличие ключа.

## Финальная передача v15

Актуальная пошаговая инструкция запуска полного набора на сервере:
[DEPLOYMENT.md](../../DEPLOYMENT.md). Используйте compose.deploy.yaml вместе с
основным Compose; он требует полный каталог и непустые серверные секреты.
Сопоставление источников дополняет основной LLM-анализ: [SOURCE_COMPARISON](SOURCE_COMPARISON.md).
Сборщики остановлены по последней команде; запуск веб-сервиса их не возобновляет.
