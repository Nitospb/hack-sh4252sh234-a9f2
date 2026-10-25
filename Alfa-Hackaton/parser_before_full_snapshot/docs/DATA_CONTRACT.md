# Контракт данных и хранения

[Для агентов](../AGENTS.md) · [Архитектура](ARCHITECTURE.md) · [Эксплуатация](OPERATIONS.md)

## Область контракта

Основной контракт — JSON-объект статьи в articles.record и JSONL-экспорте. Он формируется Article.record(). schema_version сейчас равна 1. Таблицы содержат также индексы и состояние обработки, поэтому экспорт не является полным бэкапом runtime.

Новые необязательные поля добавлялись совместимо. При изменении значения существующего поля, ID, структуры дат или схемы связей требуется явно продумать чтение старых записей и миграцию. Старые records могут не содержать более новых полей images/topics: при чтении используй подходящие значения по умолчанию.

## Идентичность и версии

| Поле | Как получается | Назначение |
|---|---|---|
| `id` | SHA-256 UTF-8 нормализованного canonical_url | Стабильный ID публикации |
| `content_hash` | SHA-256 заголовка + перевод строки + текста после объединения пробелов и trim | Версия текстового содержания; регистр сохраняется |
| `text_hash` | SHA-256 текста после объединения пробелов, trim и casefold | Поиск точных совпадений текста без заголовка |
| `images[].id` | SHA-256 от article_id + перевод строки + исходного URL изображения | ID связи конкретного URL фото с новостью |
| `images[].sha256` | SHA-256 исходных байтов файла | Проверка файла и повторное использование одинаковых байтов внутри статьи |

Разные canonical URL остаются разными публикациями даже при одинаковом тексте. text_hash не объединяет записи и не обозначает общий сюжет. Смена даты, темы или картинки сама по себе не меняет content_hash.

## Поля статьи

| Поле | Тип и смысл |
|---|---|
| `schema_version` | int, сейчас 1 |
| `kind` | string, сейчас external_news, в том числе у корпоративных блогов |
| `source_id`, `source_name` | string, идентификатор адаптера и имя источника |
| `source_kind` | news_media, company_blog, community, regulator или think_tank в текущем каталоге; поле конфигурации, не определение моделью |
| `url` | string, адрес из очереди, изначально запрошенный браузером |
| `canonical_url` | string, принятый канонический URL внутри области источника |
| `title`, `text` | string, заголовок и основной текст; абзацы нормализуются, HTML удаляется |
| `description` | string/null, описание из метаданных |
| `authors` | list[string], возможно пустой |
| `language` | string, html lang или язык адаптера; автоматическое определение языка не выполняется |
| `publisher_country` | string, страна издателя; не страна события |
| `published_at` | ISO-8601 UTC с часовым поясом или null |
| `published_at_raw` | исходная строка даты или null |
| `publication_date_status` | source, missing, timezone_missing или unparsed |
| `modified_at` | распознанная дата изменения UTC или null |
| `fetched_at` | UTC, время извлечения этой версии статьи |
| `first_seen_at`, `last_seen_at` | UTC, добавляются экспортом из колонок articles; не входят в исходный Article.record |
| `text_scope` | extracted_article или accessible_excerpt |
| `extraction_method` | source_xpath, jsonld_article_body или trafilatura |
| `quality_flags` | list[string], причины ограничений/сомнений |
| `source_tags` | list[string], ключевые слова издателя |
| `topics` | list[string], темы, найденные словарными эвристиками в статье |
| `source_topics` | list[string], темы из конфигурации источника; не заменяют topics |
| `relevance_score` | int 0–100, эвристический балл всех тематик вместе |
| `raw_html_path` | путь к gzip DOM относительно runtime |
| `images` | list[object], кандидаты изображений и результаты их обработки |
| `main_image_path` | путь основного сохранённого изображения относительно runtime или null |
| `images_status` | агрегатный статус изображений, правила ниже |

Пустой массив и null имеют разный смысл. Не подставляй пустую строку или нулевую дату вместо неизвестного значения.

Возможные quality_flags текущего извлечения: publication_date_missing, publication_date_timezone_missing, publication_date_unparsed, publisher_marks_paid_content, canonical_outside_article_allowlist, subscription_offer_removed, possible_press_release. Во время сетевого сбора runner также добавляет publication_date_in_future для опубликованной даты более чем на два дня впереди текущего времени. Этот флаг не создаётся самим parse_date.

`accessible_excerpt` ставится при явном isAccessibleForFree=false в выбранном JSON-LD. В таком случае скрытый JSON-LD articleBody не используется. `extracted_article` не доказывает полноту: не любой сайт объявляет платность одинаково, а доступный текст может быть неполным.

## Даты и свежесть

Дата берётся из JSON-LD, meta property/name/itemprop и time datetime. parse_date разбирает ISO-формат, включая Z. Дата без timezone не получает автоматически Europe/Moscow или UTC. URL-дата используется только как подсказка для очереди и не записывается в published_at.

При сборе известная опубликованная дата старше source.max_age_days приводит к skipped. Перед загрузкой также применяется более грубый отсев по URL-дате с запасом в один день. Неизвестная дата сохраняется; слишком далёкая будущая дата помечается, но сама по себе не запрещает запись в общий корпус.

`audit`/`reextract` повторяют извлечение из DOM, а не сетевой путь runner. Они сохраняют исходный fetched_at и не применяют заново все проверки возраста/будущей даты из collect_source. Это важно при сравнении результатов разных команд.

## Тематики

classify использует regex-словари для ai, business, economy, finance, technology и energy на нескольких языках. Совпадения в title+description учитываются с весом 3, в первых 12 000 символах текста — с весом 1. Балл каждой темы ограничен 10, общий relevance_score — удвоенная сумма, ограниченная 100. Любое ненулевое совпадение добавляет тему.

Это не вероятность, не прогноз, не оценка достоверности и не отдельная оценка финансовой важности. Политическая статья с упоминанием банка может попасть в finance. Финансовая подборка отбирается по topics, а не только по профилю сайта.

## Объект изображения

| Поле | Смысл |
|---|---|
| `id`, `article_id` | ID связи и ID статьи |
| `url` | исходный URL картинки; порядок и значения параметров CDN сохраняются |
| `role` | lead — метаданные главного фото, body — изображение внутри статьи |
| `origin` | jsonld, og:image:secure_url, og:image, twitter:image, twitter:image:src или article_img |
| `alt`, `caption` | описание и подпись, если удалось извлечь |
| `status` | pending, saved, filtered или failed |
| `local_path` | путь относительно runtime или null |
| `sha256`, `bytes` | контрольная сумма и размер байтов |
| `width`, `height`, `mime_type` | проверенные размеры и MIME по фактическому формату |
| `downloaded_at` | время сохранения файла UTC |
| `error` | причина сбоя или фильтрации |

У кандидата pending часть полей отсутствует. У filtered после проверки ранее сохранённого файла могут остаться размеры/хеш, но local_path будет null. Для отображения локального файла проверяй status=saved и непустой local_path, а не только наличие sha256.

Ограничения: площадь минимум 160 000 пикселей, короткая сторона минимум 200, максимум 40 мегапикселей и 10 MiB. Допускаются JPEG/PNG/WebP/GIF/AVIF; SVG не принимается. Байты не перекодируются. Одинаковые байты по двум URL одной статьи могут образовать две связи, указывающие на один файл.

Кандидатов извлекается не более 30; за проход выполняется максимум 12 попыток загрузки и сохраняется максимум 6 связей со статусом saved. lead выбирается до первого успешного варианта; затем другие lead-варианты не требуются. body-кандидаты отбираются отдельно. Основным становится первый saved, включая body, если lead не получен.

Агрегат images_status вычисляется в следующем порядке:

1. Нет элементов — not_found.
2. Есть хотя бы один pending — pending, даже если уже есть saved.
3. Есть saved и failed — partial.
4. Есть saved без failed — saved; filtered не мешает этому статусу.
5. Без saved есть failed — failed.
6. Остались только filtered — filtered.

Состояние фото никак не определяет допустимость новости в articles.

## Файловые пути

```text
raw/<первые 2 символа sha>/<sha DOM>.html.gz
images/<article_id>/<sha256 байтов>.<расширение>
images/<article_id>/manifest.json
```

Manifest содержит article_id, canonical_url, title, main_image_path и массив images. Для чтения файлов разрешай local_path относительно **того runtime, откуда получен экспорт**, а не относительно текущего каталога приложения.

```python
import json
from pathlib import Path

runtime = Path("runtime")
with (runtime / "articles.jsonl").open(encoding="utf-8") as stream:
    for line in stream:
        article = json.loads(line)
        for image in article.get("images", []):
            if image.get("status") == "saved" and image.get("local_path"):
                path = runtime / image["local_path"]
                # article['id'] == image['article_id']; используйте path в потребителе.
```

Не полагайся на любой файл, найденный в каталоге статьи: там могут оставаться старые или неиспользуемые данные. Для актуальных связей используй JSON/БД/manifest. Автоматического удаления неиспользуемых файлов сейчас нет.

## Таблицы SQLite

| Таблица | Ключ | Назначение |
|---|---|---|
| `frontier` | source_id, url | Адрес, обнаружение, состояние, attempts, next_attempt, lease_until, last_error, priority |
| `articles` | id; canonical_url UNIQUE | Текущая версия JSON и служебные колонки времени/хеша |
| `revisions` | article_id, content_hash | Текстовые версии с JSON и fetched_at |
| `source_state` | source_id | next_discovery, cooldown_until, last_navigation, last_success, last_error |
| `runs` | id | Начало, завершение и JSON-результат обработки источника |
| `article_images` | article_id, image_id | Порядок и JSON связи с картинкой; local_path хранится внутри JSON record |
| `quarantined_articles` | id | Исходная запись, причина и время исключения из рабочего корпуса |

Полноценные внешние ключи между этими таблицами схемой не заданы. Согласованность поддерживают транзакционные методы Store; прямой SQL должен учитывать все связанные представления.

Карантин удаляет активную запись и активные image-связи, но сохраняет DOM и revisions. Последующий audit читает также карантин и может восстановить запись. Store.set_images обновляет запись текущего content_hash в revisions; медиа не являются независимыми неизменяемыми историческими снапшотами.

## Экспорт

JSONL — UTF-8, один JSON-объект на строку. Экспорт берёт последние статьи и добавляет first_seen_at/last_seen_at. Запись ведётся во временный файл, затем заменяет целевой. Порядок — first_seen_at, затем id; это не порядок свежести публикаций.

| Параметр | Поведение |
|---|---|
| без фильтров | все активные статьи, включая старые и с неизвестной датой |
| `--max-age-days N` | исключает известные даты старше N дней и более чем на два дня в будущем; неизвестные даты оставляет |
| `--require-date` | исключает неизвестные опубликованные даты |
| `--topics finance economy` | достаточно пересечения хотя бы по одной теме |
| `--full-text-only` | исключает известные accessible_excerpt; полноту остальных не подтверждает |

Автоматический financial-news.jsonl использует темы finance/economy, а finance-politics-news.jsonl — finance/economy/politics. Оба ограничивают возраст 14 днями и не требуют известной даты. audit/reextract обновляют общий articles.jsonl и coverage, **не** тематические подборки; после них при необходимости вызови export явно.

Будущий потребитель эмбеддингов может связывать вектор с парой article_id/content_hash и версией модели/подготовки текста. Сам сборщик векторы, event ID и кластеризацию не создаёт.
