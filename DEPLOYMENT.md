# Финальная поставка v15 — 26.10.2026

## Автоматический деплой на vpn.aezakmi.org

Workflow `.github/workflows/service.yml` после успешного CI на `main` входит
отдельным пользователем `alfadeploy` по SSH, переносит исходники в
`/opt/alfahack` через rsync, записывает `.env` из GitHub secret
`DEPLOY_ENV_FILE` и запускает `compose.yaml` с `compose.production.yaml`.
Production override подключает web к `traefik_traefik_proxy`, публикует
`alfa.aezakmi.org` через certresolver `le` без middleware и требует полный
каталог. API наружу не публикуется; state остаётся в named volume.

Секреты `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, `DEPLOY_KNOWN_HOSTS`
и `DEPLOY_ENV_FILE` настроены в GitHub Actions; значения не входят в Git.
Repository variable `ALFA_DEPLOY_READY` пока выключена: она разрешает job
деплоя только после размещения актуального serving-комплекта на сервере.
На текущем Mac serving bundle отсутствует, поэтому фактический запуск полного
корпуса на сервере зависит от отдельной передачи комплекта ниже. В
предоставленном `_env.team` ключ `ALFA_API_KEY` пустой: лента работает без
LLM, генерация разбора будет недоступна до установки действующего ключа.

Онлайн-приложение: Next.js → Python API → LLM-шлюз. LLM формирует и проверяет
анализ; детерминированные сравнения лишь дополняют его. Для serving используются
готовые векторы: Torch, Selenium, обучение и сборщики на сервере не нужны.

## Что передать на сервер

1. Исходники main этого репозитория, включая lockfiles и Dockerfiles.
2. Отдельный актуальный комплект `distribution/online-serving-final-2026-10-26-v15`:
   `release-manifest.json`, README и ВСЕ `project-data.tar.gz.part*`. Не использовать
   старый GitHub full-snapshot-v1 вместо этого комплекта. Данные не входят в Git.
3. Действующий ключ разрешённого LLM-шлюза — по закрытому каналу. `.env` текущего
   компьютера, личные профили и пользовательский state не входят в поставку.

Для новой установки нужны Docker Engine с Compose v2, Git и Python3 для
проверки/распаковки. Начальный ориентир диска — 15–20 ГБ свободно для данных,
образов и сборки; фактические ресурсы зависят от нагрузки. Это не результат
Linux/load-приёмки. На Mac проверена контейнерная сборка и работа с полными данными.

Фиксированный комплект: **13 316 документов = 11 904 новости + 1 412 TG**,
23 файла, 389,293,919 байт сжатых частей (около371 МиБ).
Поколение: `bc7e4689b6e59fc8b4c7097272eb9553ed52526405103e61d8c1239cd4133965`.
SHA-256 файла release-manifest.json: `ab1f44e70796fc3a14d78f0f37cf87d2c2d3a4fe9ab12cf2aa9117c47594f360`.
Предыдущие ZIP не изменялись. Комплект включает банк/PDF, каталог, ranking и
готовые векторы; LLM вызывается по API, его веса в комплекте не нужны.

## Чистая установка

Команды от корня НОВОГО checkout. Путь к полученной папке bundle подставить свой.
Восстановитель проверяет SHA частей и каждого файла, существующие несовпадающие
данные не перезаписывает. Не применять `--overwrite` к рабочей установке.

```bash
python3 tools/restore_release.py --no-download --directory /absolute/online-serving-final-2026-10-26-v15 --target "$PWD"
cp -n .env.example .env
chmod 600 .env
```

Локальным редактором заполнить `.env`: `ALFA_API_KEY`, случайный отдельный
`ALFA_INTERNAL_TOKEN` (например, `python3 -c 'import secrets; print(secrets.token_urlsafe(32))'`),
разрешённые `ALFA_BASE_URL`/`ALFA_MODEL` и согласованные суточные бюджеты.
Ключ LLM и internal token — разные секреты. Не помещать их в Git, browser env,
скриншоты, команды с опубликованными логами или Docker image.

```bash
docker compose -f compose.yaml -f compose.deploy.yaml config --quiet
docker compose -f compose.yaml -f compose.deploy.yaml up --build -d --wait --wait-timeout 180
docker compose -f compose.yaml -f compose.deploy.yaml ps
curl --fail http://127.0.0.1:3000/api/live/health
docker compose -f compose.yaml -f compose.deploy.yaml exec -T api python -m service.smoke --base http://web:3000/api/live
```

Overlay требует непустые секреты и `ALFA_REQUIRE_FULL=1`: при отсутствии полного
каталога/банковских assets запуск завершается ошибкой вместо синтетической подмены.
По умолчанию web доступен только через loopback3000, Python API наружу не публикуется.
Smoke не вызывает LLM; создаёт изолированную техническую историю. `health` должен
показать `grounded-agent-v15`, полный корпус и `analysis_availability.available=true`
при действующем ключе и свободной квоте. Наличие ключа ещё не доказывает его
действительность: отдельно выполнить один реальный разбор и проверить trace/цитаты.
Доступные компании, лента и PDF проверяются без LLM.

Текущий Mac использует9082; для него перед Compose задавать `ALFA_WEB_PORT=9082`.
Не менять порт текущего экземпляра ради проверки инструкции нового сервера.

## Доступ команде и жюри

Прототип использует browser user_id, полноценные IAM/tenant isolation не реализованы.
Internal token защищает межсервисные вызовы, не вход пользователя. До добавления
серверной авторизации использовать закрытый стенд/VPN или SSH-туннель:

```bash
ssh -L 3000:127.0.0.1:3000 user@server
```

Открыть локально `http://127.0.0.1:3000`. Для публичного демонстрационного адреса
оператору нужен HTTPS ingress с ограничением доступа и согласованный демо-набор.
Не открывать порт API и не выдавать private state через публичные ссылки.
Production Compose задаёт домен и TLS. Маршрут сейчас не содержит middleware;
проверку прав пользователя он не обеспечивает.

## Обновление и откат

Сначала проверить отсутствие queued/running jobs, затем сделать online backup:

```bash
docker compose -f compose.yaml -f compose.deploy.yaml exec -T api python -m service.backup backup --state /state --bundle /state/backups/before-update-UNIQUE
```

Сохранить копию backup на другом носителе через `docker cp`; bundle содержит
пользовательскую историю/контекст и передаётся приватно. Записать предыдущий commit.
Обновить код, собрать образы, выполнить `up -d --no-deps api web` с теми же двумя
Compose-файлами, проверить health/smoke. При проблеме вернуть предыдущий commit,
пересобрать и поднять на том же volume. State не удалять; для восстановления в
новую папку использовать `service.backup restore` по service/README.
Никогда не выполнять `down -v` или volume prune. Данные передаются отдельно и
не откатываются произвольным копированием файлов в активное поколение.

## Кэш и ограничения этой передачи

В поставке нет node_modules, .next, Python bytecode, Chrome-кэша, временных
окружений и логов. Они восстанавливаются из lockfiles; сборка идёт внутри Docker.
Данные, исходные ZIP, предыдущие комплекты, веса и mutable SQLite не удаляются
как кэш. Запущенные web/API используют собранные images, не локальную .next.

Все сборщики и automation telegram остановлены по команде пользователя.
Compose их не запускает. Новые новости автоматически не поступают до отдельной
команды возобновить сбор. Обучение также не запускается. Новая установка имеет
свежий локальный ledger, но общий бюджет внешнего шлюза от этого не сбрасывается.
OCR-сверка, независимый human gold и полноценная LLM-приёмка v15 остаются открытыми;
это не препятствует воспроизводимому запуску, но ограничивает заявления о качестве.
Остальной backlog — NEXT_AGENT_HANDOFF.md, политика LLM/локальных проверок —
.ai/service/SOURCE_COMPARISON.md.
