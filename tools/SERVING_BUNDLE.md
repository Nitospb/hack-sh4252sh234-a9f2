# Переносимый комплект веб-сервиса

Из корня репозитория, Python3.12 с numpy:

```bash
python tools/serving_bundle.py --output distribution/online-serving-YYYY-MM-DD
python tools/restore_release.py --no-download --directory distribution/online-serving-YYYY-MM-DD --target /absolute/NEW-checkout
```

Упаковщик удерживает FileLease выбранного поколения от pruning, проверяет его
content-addressed manifest и validate(). В архив попадает только это поколение,
размещённое в обычном pipeline/output для первого запуска, без устаревшего
current.json/leases/runtime. Assets копируются SQLite backup; PDF проверяются по
SHA базы банка. release-manifest.json перечисляет SHA/размер каждого файла и части,
версию каталога, code commit, время и исключения. Существующий output не затирается.
Восстановитель проверяет части до распаковки, SHA каждого файла и безопасные пути.

Комплект для online serving использует готовые векторы. Для обучения, пересборки
или live-индексации дополнительно нужен исходный model/data kit из RUNBOOK и
DATA_UPDATE. Это не замена архива исходных данных и не backup пользовательского
state. .env, ключи, feedback, jobs, notes, кэш, очереди и веса не включаются.
Секрет получить отдельно. Полный режим запуска: ALFA_REQUIRE_FULL=1.

Фактическая локальная проверка26.10:
- distribution/online-serving-2026-10-26: 23файла, 13 295документов,
  2 133 489 051байт исходных данных, 389 114 209байт сжатых частей.
- Восстановление в новый git archive checkout, запуск отдельного API9093 с новым
  state и пустым ключом: все11 smoke-проверок прошли, PDF доступен, LLM не вызван.
- Временный API остановлен; рабочий API9082 и live-worker не затронуты.
- Это локальная приёмка на Mac. Чистая Linux-машина и публикация полного
  model/data-release остаются отдельными проверками. Исходные ZIP не изменены.

Файлы данных не добавлять в Git и не публиковать автоматически. Передавать
команде согласованным каналом. Комплект не содержит пользовательских заметок,
но содержит исходные обезличенные профили и банковские материалы.

## Комплект с подготовленным обучением

`--with-training` дополнительно включает news_matching/models и training/data/news-v1.
Он не запускает обучение. В комплекте есть исходные E5/reranker/tokenizers и
готовые splits/weak pairs; исходные очереди и вся taxonomy для полной пересборки
по-прежнему передаются отдельно.

```bash
python tools/serving_bundle.py --with-training --output distribution/serving-training-kit-YYYY-MM-DD
```

Проверенный serving-training-kit-2026-10-26: 51файл,13 298документов,
2 998 534 564байт без сжатия,895 872 300байт частей. Восстановлен в НОВЫЙ git
archive checkout; training.train --check-only показал training_started=false,
6 124/766/765пар, исходный SHA модели и manifest совпали. Это не обученный checkpoint.
Ни один из комплектов не перезаписывает исходные финальные ZIP.

После проверок временные restore-check папки удалены для освобождения диска.
Сами новые комплекты и JSON-отчёты проверок сохранены.
