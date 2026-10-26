# Alfa: персональная новостная аналитика бизнеса

**Передача разработчикам:** [TEAM_HANDOVER.md](TEAM_HANDOVER.md).
**Актуальный backlog и журнал:** [NEXT_AGENT_HANDOFF.md](NEXT_AGENT_HANDOFF.md).

Лента на локальных E5-векторах, реальные обезличенные профили компаний,
банковские исследования с OCR и ссылками на страницы, собственный агент
разбора событий, уточняющий диалог, настоящий trace и обратная связь.

## Быстрый запуск

Docker Engine/Desktop с Compose v2, из папки приложения:

```bash
cd Alfa-Hackaton
# Если .env ещё нет: cp .env.example .env
# ALFA_API_KEY заполняется локально, на сервере.
docker compose up --build -d
```

Открыть http://127.0.0.1:3000. Без полного корпуса запускается явно помеченный
синтетический smoke-набор; без ключа доступны лента и данные, генерация отключена.
`ALFA_REQUIRE_FULL=1` запрещает подстановку тестовых данных.
**[Полная инструкция: установка, данные, API, агент и эксплуатация](Alfa-Hackaton/service/README.md).**

Сценарий: главная → выбор компании → профиль/роль → лента → открытие новости →
персональный разбор → уточняющий вопрос → источник/PDF → журнал и оценка.
Неподтверждённые выводы заканчиваются needs_context/not_relevant.

## Данные и ML

Последний локальный корпус: **11 835 сайтовых новостей, 1 412 Telegram-постов,
85 525 исходных профилей / 85 514 уникальных компаний**, 49 915 E5-чанков.
Telegram остаётся внутренней аналитикой и исключён из новостного ML-training.
Исходные ID, 1 000 групп CSV и 10 000 композиционных bt_ тем сохранены.

Код хранится в Git; большие данные/веса отдельно. Публичный релиз
`full-snapshot-v1` содержит прежний командный снимок (6 095 новостей и
1 404 Telegram-поста), а не автоматически последние локальные данные.
Восстановление: `python3 tools/restore_release.py`, проверяет SHA-256.
Актуальное объединение и пересчёт: [DATA_UPDATE.md](Alfa-Hackaton/pipeline/DATA_UPDATE.md).
Оригинальные выданные ZIP не перезаписываются.

E5 и reranker — готовые предобученные модели. Собственного дообученного
checkpoint пока нет. **Обучение по просьбе пользователя не запускается**;
[данные, код и инструкция подготовлены](Alfa-Hackaton/training/README.md).
Сборщики ранее остановлены пользователем и не стартуют вместе с веб-сервисом.

Путь данных: локальный preprocessing → SQLite/npy → Python API → Next BFF
`/api/live` → веб-интерфейс. Для генерации разбора Python вызывает только
разрешённый LLM-шлюз организаторов. Ключ не передаётся браузеру.

## Компоненты

| Папка | Назначение |
|---|---|
| `Alfa-Hackaton/service` | контекст клиента, OCR/поиск банка, агент, jobs, tests, Docker |
| `Alfa-Hackaton/frontend` | Next.js: единый контекст и 11 рабочих маршрутов |
| `Alfa-Hackaton/recommendations` | API, MMR, реакции и пользовательское состояние |
| `Alfa-Hackaton/insight_generation` | разрешённый gateway, prompt/schema/grounding contract |
| `Alfa-Hackaton/pipeline` | объединение корпуса, embeddings, ranking, integrity checks |
| `Alfa-Hackaton/news_matching`, `taxonomy` | модели, тематические кандидаты и связи |
| `Alfa-Hackaton/training` | подготовленное обучение и отдельная оценка кандидата |
| `Alfa-Hackaton/parser` | отдельный сбор сайтов и Telegram, сейчас остановлен |
| `tools` | восстановление и упаковка релизов |

## Проверка

```bash
cd Alfa-Hackaton
python -m pip install -r service/requirements.lock
python -m unittest discover -s service/tests -v
python -m unittest discover -s recommendations
python -m unittest discover -s insight_generation
python -m service.smoke --base http://127.0.0.1:3000/api/live
cd frontend
npm ci
npm run lint
npm run build -- --webpack
```

Smoke/CI не запускают LLM, обучение и сбор. Настоящий платный сценарий проверяется
отдельно через интерфейс. Локальные диагностические отчёты не публикуются в Git.
Точность бизнес-выводов и precision/nDCG ещё требуют независимой ручной оценки;
успешные тесты или exact-quote validation не заменяют её.

Поставка — локальный прототип. Перед внешним размещением нужен authenticated
TLS ingress с банковским scope пользователя; localStorage ID не является IAM.
Лицензии, источники и границы имитаций:
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

[Отчёт следующему агенту и обновляемый журнал доработок](NEXT_AGENT_HANDOFF.md).

## Последние дополнения

- [Память явных уточнений и сравнение ответов](Alfa-Hackaton/service/DIALOGUE.md).
- [Калькулятор процентных и валютных сценариев](Alfa-Hackaton/service/SCENARIOS.md).
- [Слепая экспертная разметка и сравнение ранжирования](Alfa-Hackaton/evaluation/README.md).
- [Новые переносимые serving/training комплекты](tools/SERVING_BUNDLE.md).

Независимых экспертных меток пока0; наличие этих инструментов не является
измеренной точностью продукта. Данные и модели передаются отдельно от Git.
