# Инструкция агенту: запуск обновления сайтов и Telegram

Задача на сервере: новые публикации → сохранение → индексация → согласованное
обновление каталога → приложение. Версия приложения у команды актуальная;
перед изменениями сверить реальные CLI и реализацию с этим документом.
Только написать/передать эту инструкцию не означает запускать сбор на прежнем Mac.

Текущая командная структура проверена на main93ce886: приложение в корне,
документация в `.ai/`. Команды ниже учитывают этот перенос. Не применять
инструкции прежнего вложенного checkout без поправки путей.

## 1. Сначала проверь окружение и входные данные

Прочитай AGENTS.md, .ai/AGENTS.md, DEPLOYMENT.md, .ai/pipeline/LIVE.md,
.ai/pipeline/PUBLICATION.md, .ai/parser/AGENTS.md и .ai/parser/docs/INTERESTS.md.
Проверь `git status`, процессы, Compose health, текущую версию каталога и логи.
Не запускай второй процесс на уже занятом runtime; lock-файлы не удалять.
Сохрани пользовательский state через service.backup до обновления сервиса.
API/web можно оставить работающими во время сбора/индексации.

**Внимание к структуре ZIP:** application-data-v15-complete.zip собран ДО переноса
приложения в корень. Распаковать его сначала в отдельный staging. Файлы из
`staging/Alfa-Hackaton/pipeline/output/` разместить в `repo/pipeline/output/`,
а `staging/data/reports/` — в `repo/data/reports/`, сохраняя остальные правила
DEPLOYMENT.md. Не оставлять данные только в лишней вложенной папке Alfa-Hackaton
и не копировать старые исходники поверх актуальной версии. Для parts-формата
использовать актуальный tools/restore_release.py и проверить его нормализацию путей.

**application-data-v15-complete.zip достаточен для online serving, но не для
нового индексирования.** До запуска publisher должны существовать:

- Данные из ZIP в `pipeline/output/` и `data/reports/`.
- `news_matching/models/`: E5 ONNX, reranker ONNX, tokenizer JSON;
  для MPS/CUDA также исходный E5 Torch checkpoint. Пути определяет model_backend.py.
- `news_matching/output/object_families.json` — определения семейств.
- `taxonomy/output/okved_topic_mapping/okved_topics.sqlite` с таблицами
  companies/topics/mapping/bindings/activities — исходные связи компаний и тем.
- Снимок для `--snapshot`: `data/articles-all.jsonl` и
  `telegram/telegram-posts.jsonl` внутри папки снимка.
- Сохраняющие прежние ID исходные live SQLite, если часть baseline появилась
  после этого снимка: новости `parser/runtime/full-snapshot/news.sqlite3`,
  прежняя online-очередь при возобновлении её runtime и Telegram — по пути ниже.
- Исходный `objects_company_interest.csv` для Telegram. Это отдельный входной
  CSV, не таблица профилей компаний и не список имён клиентов.

Модели/training-kit и исходные snapshot/taxonomy передаются отдельно. Старый
full-snapshot-v1 можно распаковать в отдельный staging как источник нужных
моделей/входов, но НЕЛЬЗЯ им перезаписывать финальный serving-каталог.
Проверь SHA и совместимость; не скачивай случайные другие веса вместо прежних.
Если необходимых исходников данных нет — перечисли недостающие пути владельцу,
не объявляй рабочий publisher и не отключай проверку сохранения ID.

Первый кандидат должен сохранять ВСЕ article_id и source_record_id финального
baseline. В baseline 13 316 документов, но проверять надо множества ID, не только
числа. Один более старый snapshot может оказаться недостаточным. Сборщик тогда
может сохранять новые записи в staging, однако публикация должна оставаться
заблокированной до восстановления полного входного корпуса.

## 2. Подготовь два Python-окружения и Chrome

Пример корня checkout — `/srv/alfa`; замени его действительным путём сервера.
Запускать от отдельного непривилегированного пользователя, Chrome без `--no-sandbox`.
Chrome/Chromium и совместимый ChromeDriver установить средствами окружения сервера;
проверить наличие, версии и запуск, а не угадывать Mac-пути. Сеть должна допускать
источники/robots, Selenium Manager при необходимости и публичные t.me/s страницы.

```bash
cd /srv/alfa
python3.12 -m venv .venv-parser
.venv-parser/bin/python -m pip install -r parser/requirements.lock
python3.12 -m venv .venv-index
.venv-index/bin/python -m pip install -r news_matching/requirements-gpu.lock
```

GPU-lock включает базовый lock и Torch. Здесь только установка и inference,
НЕ обучение. Для CPU используй `--backend cpu`, Linux NVIDIA — `cuda`, Mac — `mps`.
CPU ONNX и Torch считаются разными энкодерами: при смене backend первый пересчёт
может охватить весь корпус; нельзя сохранять старые векторы под новым SHA.
Планируй ресурсы по фактической машине и логам. API-контейнер не содержит всего
окружения сборщика/индексатора, эти команды выполняются отдельным worker-процессом.

```bash
cd /srv/alfa/parser
/srv/alfa/.venv-parser/bin/python -m news_collector --runtime runtime/browser-check --headless doctor
```

Doctor — отдельный технический runtime, не месячная очередь и не боевой профиль.
При ошибке Chrome исправить окружение до запуска длительных процессов.
LLM-ключ сборщикам не нужен; не копировать серверный .env в их логи.

## 3. Сайты: один пробный цикл с публикацией

Начать с РБК и Интерфакса: эта live-цепочка проверялась. Прочие источники добавлять
по одному после check-sources, не запускать сотни браузеров одновременно.
`--max-articles` — бюджет попыток, а не обещанное число новых текстов.

```bash
cd /srv/alfa
/srv/alfa/.venv-index/bin/python -m pipeline.live \
  --runtime parser/runtime/live-online \
  --collector-python /srv/alfa/.venv-parser/bin/python \
  --snapshot /srv/alfa/imports/alfa-final-dataset-2026-10-25-0900 \
  --baseline pipeline/output \
  --releases pipeline/output/releases \
  --status pipeline/output/live-status.json \
  --backend cpu --sources rbc interfax \
  --workers 1 --max-articles 3 --max-links 40
```

Путь snapshot выше — пример размещения, не файл из serving-ZIP. Создать новый
runtime или возобновить прежний только с его настоящим live-worker.json.
Не подставлять старый month/history runtime и не фабриковать marker ради обхода gate.
Если команда завершилась, проверить collecting/indexing/ranking/stories логи,
last_error и факт publish. Нулевой exit/создание news.sqlite3 сами по себе не
доказывают, что новая версия появилась в приложении.

После успешного прохода повторить ТОЧНО ту же команду с тем же runtime, добавив
`--forever --interval 900`. Это проверка источников раз в цикл с паузой15мин
после прохода, а не мгновенный push при публикации редакцией.
Подключить её к существующему supervisor/systemd/Docker worker на сервере:
один экземпляр, постоянный runtime, рабочая папка корня репозитория, restart с backoff,
SIGTERM сначала основному worker и достаточно времени завершить индексацию.
Не применять kill9 для штатной остановки. Не включать автоматизацию старого Mac.

API должен читать те же host `pipeline/output/releases` и `live-status.json`:
в штатном Compose они уже доступны через bind `/catalog`. Worker публикует
immutable generation + current.json; API подхватывает её на следующем запросе.
Не копировать отдельную SQLite поверх работающего каталога и не трогать feedback.
`--skip-collect` повторяет индексацию уже собранного, но может пропустить её при
неизменившемся fingerprint; это НЕ универсальная кнопка пересборки Telegram.

## 4. Telegram: отдельный сборщик публичных каналов

Код использует Selenium и публичные `https://t.me/s/<channel>`, а не Bot API или
личную сессию. API_ID, API_HASH и bot token для этой реализации не нужны.
Доступная история ограничена публичным preview/бюджетом страниц.

**Важно:** текущий `pipeline/corpus.py` читает live Telegram по фиксированному
пути `parser/runtime/telegram-live/telegram.sqlite3`.
Если запустить сбор в telegram-analytics, он будет собирать отдельную аналитику,
но текущий builder эту базу сам не найдёт. Не создавать между ними ненадёжную
символическую ссылку и не копировать живую SQLite без согласованного backup.

Для нового сервера создай отдельную конфигурационную папку окна, например
`parser/runtime/telegram-window/history-job.json` с ключами `since` и `until`:
UTC ISO8601, начало нужного периода и момент первого запуска. Это только входное
окно Telegram, НЕ команда запускать месячный news-backfill. Не перезаписывать
существующее окно: Telegram runtime привязан к нему. `--follow` расширяет верхнюю
границу на следующих проходах, сохраняя начальную нижнюю.

```bash
cd /srv/alfa/parser
/srv/alfa/.venv-parser/bin/python -m news_collector \
  --runtime runtime/telegram-live --headless telegram \
  --channels-config config/telegram-channels.json \
  --interests /srv/alfa/inputs/objects_company_interest.csv \
  --window-from runtime/telegram-window \
  --max-pages 2 --max-posts 40
```

Сначала один ограниченный проход. Затем та же команда с `--poll-seconds 1800 --follow`
как отдельный supervised process. Для первого теста можно ограничить `--channels`
существующими enabled handles из config, не угадывать имена каналов.
Результат: telegram.sqlite3, telegram-posts.jsonl, telegram-report.json и карты
тем/отраслей. Проверить настоящие channel/message_id, даты, тексты и ссылки.
blocked/error не сбрасывать бесконечно: исправить причину, robots/pacing сохранять.
SIGTERM/SIGINT останавливают этот процесс отдельно от новостного worker.

## 5. Связка Telegram → приложение: обязательная проверка агентом

В проверенной версии pipeline.live fingerprint учитывает NEWS и день UTC,
но НЕ новую Telegram-базу. Поэтому запуска Telegram недостаточно для гарантии
обновления каталога: новый пост может попасть при следующей news/daily пересборке,
но отдельный регулярный TG-trigger не реализован. В более свежем коде команды
это могло быть исправлено — сначала проверь реализацию, не делай дубль.

Если ещё не исправлено, перед обещанием автоматического Telegram в UI:

1. Добавить согласованный read-only/online-backup снимок TG SQLite и отпечаток
   содержательных версий постов в решение о пересборке, включая исправления.
2. Передавать этот снимок builder явно; не полагаться на изменяемую БД, прочитанную
   из нескольких разных моментов времени. Путь источника лучше сделать параметром.
3. Сохранить одного publisher, worker/build locks, предыдущие IDs и контроль SHA.
4. Проверить, что новый TG-пост без новой news-статьи запускает публикацию, повторный
   цикл без изменений не создаёт дублей, а правка поста меняет версию корректно.
5. Проверить kind=telegram_post и ml_export_allowed=false: Telegram остаётся
   внутренней аналитикой, не добавляется в новостные training-выгрузки.

Это небольшая отдельная задача интеграции, а не выполненная настройка сервера.
В инструкции нет команды, которая честно заменяет её постоянным `--skip-collect`.
До её приёмки сообщать: «Telegram собирается отдельно; независимая автоматическая
публикация новых постов в приложение не подтверждена».

## 6. Приёмка и эксплуатация

- Сайты: реальная новая статья → news.sqlite3 → новая generation → API `/article`
  возвращает текст/дату/ссылку, лента учитывает статью при подходящей релевантности.
- Telegram: реальный новый пост → отдельная TG SQLite → после интеграции новая
  generation с тем же kind и запретом training; отсутствие в конкретной ленте
  может объясняться ролью/интересами, но наличие в каталоге проверить напрямую.
- Проверять live-status.json: running, heartbeat_at, phase, last_error,
  last_publish_success, serving_version, source_health, новые/переиспользованные chunks.
- Проверять health/quality и `/api/live/article?article_id=...`, не только PID.
- `collected_articles` не равно количеству новых уникальных или допущенных в выдачу.
- Изображения только URL; не запускать скачивание. Robots/pacing/cooldown, профильные
  leases и runtime-lock сохранить. ProfileStore удаляет только разрешённый кэш
  закрытых профилей, cookies/данные/ZIP/state не чистить под видом оптимизации.
- Статус «running» без свежих записей/heartbeat не доказательство здоровья. Не
  запускать дубли; изучить лог и безопасно перезапустить тот же runtime.
- Все данные/модели/кэш/логи — вне Git. Не использовать публичный релиз для секретов
  или пользовательского state. Обучение не требуется и этой задачей не разрешено.

При передаче результата указать процессы/supervisor, пути runtime и моделей,
источники/каналы, периодичность, последнюю запись и публикацию, реальный coverage,
оставшиеся ограничения. Не выдавать конфигурацию за выполненную живую приёмку.
