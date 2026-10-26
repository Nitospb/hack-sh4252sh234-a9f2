# Свежие новости → версия каталога → приложение

Запуск из корня приложения. Нужны Chrome/ChromeDriver, Python среды parser и
ML-pipeline (torch/onnxruntime/tokenizers по существующим lockfiles). Модели и
исходный snapshot должны быть подготовлены по DATA_UPDATE.md. Веса не обучаются.

```bash
python -m pipeline.live --runtime parser/runtime/live-online --sources rbc interfax \
  --collector-python /absolute/parser-venv/bin/python --backend mps \
  --workers 1 --max-articles 2 --max-links 30
```

По умолчанию выполняется **один** ограниченный цикл. `--forever --interval 900`
включает последующие циклы с паузой15мин (инженерная настройка, не требование ТЗ).
`--cycles 2 --forever` ограничивает число циклов. Источники задаются явно; они
должны существовать и быть enabled в parser/config/sources.json. Запуск всех
сотен адаптеров на Mac16GiB не является проверенной конфигурацией масштабирования.

Worker имеет собственный worker.lock. Каждый сбор использует исходные
collector.lock, robots, pacing, cooldown и аренды frontier. Только runtime с
маркером live-worker.json допускается к возобновлению; существующая история без
этого маркера отклоняется. Старые остановленные месячные очереди не используются.
Сигнал SIGTERM/SIGINT останавливает текущий сбор штатно; уже сохранённое проходит
индексацию/публикацию, затем worker завершается. Если сигнал пришёл во время
индексации, она завершается до остановки. Не удаляйте lock-файлы.

## Контракт и границы

Parser сохраняет исходный Article schema_version1 по [DATA_CONTRACT](../parser/docs/DATA_CONTRACT.md).
Стабильные id/content_hash/text_hash, source_id/source_name/canonical_url,
published_at/publication_date_status, fetched_at, text_scope/quality_flags,
raw_html_path и images сохраняются. Скачивания картинок нет (`--defer-images`),
отсутствие картинки не исключает текст. Raw HTML/очередь остаются в runtime,
Chrome хранит кэш отдельно в ALFA_BROWSER_CACHE/системном Cache.

Перед индексацией SQLite копируется через online backup под collector.lock в
index-input.sqlite3. Кандидат берёт snapshot + прежние командные SQLite + новую
базу, выбирая последнюю наблюдаемую версию. Catalog.article_provenance содержит
JSON происхождения; исходный индекс и выданные ZIP не меняются. Свежесть30суток,
известный timezone, отсутствие будущих дат/accessible_excerpt, длина текста и
точные дубли проверяются независимо от тематического ранжирования. Негодная для
выдачи запись сохраняется в полном каталоге с gate, без ослабления ради квот.
Telegram остаётся отдельным kind и не добавляется в news training.

Неизменённые chunks переиспользуются по article_id/content_hash/encoder SHA.
Тематические anchored candidates дополнительно кэшируются по текстовой версии,
семействам, энкодеру и версии алгоритма; reranker cache учитывает его SHA.
Изменение evidence/anchor алгоритма требует повышения anchored-v2 в build.py.
При первой сборке такого кэша ещё нет, поэтому тематический поиск выполняется
один раз для всего корпуса. Модельные векторы неизменившихся статей не считаются
заново. Ranking sidecar пересобирается SQL/эвристиками целиком; это не обучение.

Публикация проверяет согласованность DB/ranking/vectors и сохранение всех
прежних IDs. Immutable generations и current.json описаны в PUBLICATION.md.
Успешный fingerprint фиксируется только после publish. При сбое предыдущая
публикация остаётся; `--skip-collect` повторяет только индексацию уже собранного.
Неизменённый fingerprint пропускает дорогую сборку; раз в UTC-день обновляются
зависящие от даты gates. Pipeline не изменяет feedback/jobs/notes/assets.

## Подключение API и наблюдаемость

Compose читает `/catalog/releases` внутри уже смонтированного pipeline/output.
Локальный API: `ALFA_CATALOG_RELEASES=/absolute/pipeline/output/releases`.
Status: pipeline/output/live-status.json, через health.catalog_publication.collection.
Фазы, last_attempt/success, source results/cooldowns, число собранных/допущенных,
число новых/переиспользованных chunks, version и публикационный лаг различаются.
Количество collected не равно количеству релевантных/допущенных материалов.
Экран quality обновляет health каждые30сек; новые статьи видны в следующем запросе
ленты, уже открытая подборка не заменяется во время чтения.

Worker не запускается вместе с web автоматически: на сервере запустить эту же
команду отдельным supervised process с Chrome и постоянным runtime. Секрет LLM
ему не нужен. Рекомендуется один publisher/каталог и выделенный CPU/GPU worker.
API и web контейнеры не выполняют Selenium. Ограниченные проходы на данном Mac
проверены отдельно от инфраструктуры будущего сервера.

После падения перезапустите ту же команду с тем же runtime. При нехватке2GiB
worker приостанавливает цикл; никаких пользовательских данных не удаляет.
Worker сохраняет три последних generations и текущую. Старые удаляются только
если файл аренды всех читателей освобождена; активный HTTP-запрос сохраняет
свою версию до завершения. Все читатели generations должны использовать Snapshots
с lease; внешнему прямому читателю нужно создавать FileLease на время чтения.

Проверки: parser tests/test_live_media.py; pipeline tests/test_live.py и
 test_incremental_embeddings.py; service/tests/test_publication.py. Живой
проход нужно отличать от синтетических тестов и реального coverage всех издателей.
