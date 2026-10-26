# Порядок будущего запуска

Все команды ниже выполняются из `Alfa-Hackaton/` под Python 3.12 с
`training/requirements.lock`. В текущем сеансе выполнена только подготовка,
`--check-only` и проверки без обучения E5. Команды с --run приведены
**для будущей прямой команды пользователя обучить**.

## 1. Восстановить данные и веса

Для другого компьютера нужны:

- исходники приложения и training/;
- `training/data/news-v1` (проверяется manifest) либо финальный снимок `0900`,
  original object_families.json и текущий catalog.sqlite для воспроизведения
  очереди разметки;
- `news_matching/models/e5-torch/` и `e5-tokenizer/` из полного релиза;
- для повторной индексации/ранжирования — также reranker, taxonomy и исходные
  live/snapshot файлы согласно pipeline/DATA_UPDATE.md.

Обучение не требует Chrome, запуска сборщиков, raw HTML, картинок, Telegram,
ALFA_API_KEY или доступа к персональному Telegram. Для уже готового bundle
не нужны большие исходные очереди парсера/платёжные таблицы.

При необходимости воспроизвести bundle:

```bash
python -m training.prepare --output training/data/news-v1
```

Существующий bundle не перезаписывается. Для новой версии используйте новый
путь и обновите data_dir в копии конфигурации. Относительные пути в JSON
разрешаются относительно самого JSON, а не текущего каталога shell.

## 2. Проверить готовность, пока не обучая

```bash
python -m training.train --config training/configs/mac-m4.json --check-only
python -m unittest discover -s training/tests -v
```

Ожидается 6 124/766/765 пар, 383 updates/epoch, 1 149 updates всего,
training_started=false. supervised config пока должен отказать из-за
отсутствия одобренных положительных и отрицательных примеров. Не обходите
эту проверку пустыми/автоматическими labels.

Проверьте свободную память и минимум 4 GiB места для атомарных сохранений.
Лучше иметь дополнительный запас; одновременно не запускайте сборщики,
второе обучение и пересчёт каталога. Установка зависимостей использует сеть,
само обучение загружает веса только с диска. Для CUDA можно скопировать
конфигурацию и задать device=cuda; это однопроцессное обучение на одном GPU.
CPU поддержан, но может быть значительно медленнее. MPS лимит отключать нельзя.

## 3. Когда пользователь разрешит обучение

```bash
python -m training.train --config training/configs/mac-m4.json --run
```

Первым считается baseline на validation, затем тренируются только train
пары. Устройство выбирается auto: CUDA, затем MPS, затем CPU. На M4 профиль
рассчитан на 16 GiB с micro batch=2. Последний неполный batch обрабатывается,
singleton присоединяется к предыдущему, чтобы оставались negatives.

Планируемое время по прежней аппаратной пробе — порядок часов; именно этот
тренер с gradient replay ещё не запускался на E5. Ранний замер 0,39 с относился
к другому простому шагу batch=2; его нельзя умножать на 1 149 logical updates.
Дополнительный cache forward, checkpoint I/O и evaluation тоже занимают время.

После разрешения можно сначала проверить 20 настоящих updates с сохранением:

```bash
python -m training.train --config training/configs/mac-m4.json \
  --run --stop-after-updates 20
```

Это уже настоящее обучение, сейчас эту команду не выполнять. Затем продолжить
тот же запуск, а не начинать второй:

```bash
python -m training.train --config training/configs/mac-m4.json --run \
  --resume training/output/e5-title-body-m4/checkpoints/latest
```

## 4. Остановка, ошибка и продолжение

Ctrl+C/SIGTERM устанавливает флаг; дождитесь завершения текущего logical
update и сохранения. Статус остановки появится в run-status.json. При аварийном
завершении можно потерять updates после последнего checkpoint, но исходные
данные/рабочая модель останутся нетронутыми.

В checkpoint хранятся optimizer/RNG и точный cursor по детерминированной
перестановке train. Resume сверяет SHA-256 bundle, базовых весов, tokenizer,
кода и learning config. Пути/устройство можно менять, гиперпараметры и данные —
нет. После изменения математики/эпох используйте новый эксперимент; не
подменяйте fingerprint. Перенос MPS→CUDA поддерживает восстановление параметров
и AdamW, но битовое совпадение вычислений разных устройств не обещается.

На старте сохранён исходный полный checkpoint; затем latest обновляется каждые
100 updates и на границе эпох/остановке. best хранит лучшие веса по validation.
Старые поколения удаляются после полной публикации нового. При падении между
rename предыдущий complete checkpoint восстанавливается из .previous.
После OOM не отключайте memory limit: возобновите совместимый запуск на более
свободном/большем устройстве или начните новый с меньшей длиной/micro batch.

## 5. Финальная оценка без переобучения

После выбора best по validation один раз сравните baseline и best на test:

```bash
python -m training.evaluate --config training/configs/mac-m4.json \
  --split test --output training/output/e5-title-body-m4/baseline-test.json
python -m training.evaluate --config training/configs/mac-m4.json \
  --model training/output/e5-title-body-m4/best/model \
  --split test --output training/output/e5-title-body-m4/candidate-test.json
python -m training.compare \
  --baseline training/output/e5-title-body-m4/baseline-test.json \
  --candidate training/output/e5-title-body-m4/candidate-test.json \
  --output training/output/e5-title-body-m4/comparison.json
```

Recall@1/5/10, MRR@10, nDCG@10 считаются на одинаковом frozen наборе.
У title/body один релевантный собственный текст, нет gold тематической
релевантности. У supervised — только human judged pool, не весь каталог.
При улучшении title/body нельзя заявлять доказанное улучшение бизнес-ленты.
Нужна ручная оценка объектов, разные источники/языки, контроль false positives.
Test не используется для выбора checkpoint или подбора порогов.

## 6. Подготовка кандидата для ленты

Автоматической замены production нет. После оценки и разрешённой пользователем
интеграции сначала соберите **отдельный** каталог:

```bash
python pipeline/build.py --backend mps \
  --encoder-dir training/output/e5-title-body-m4/best/model \
  --output pipeline/output-candidate
python pipeline/ranked_catalog.py \
  --catalog pipeline/output-candidate/catalog.sqlite \
  --output pipeline/output-candidate/ranking.sqlite
python pipeline/validate_catalog.py --output pipeline/output-candidate \
  --training ../imports/alfa-final-dataset-2026-10-25-0900/data/training-news.jsonl
```

--backend cpu с --encoder-dir использует Torch CPU; без --encoder-dir это
прежний ONNX. --backend cuda использует Torch CUDA. Новый checkpoint даёт
новый hash; статьи и object-family vectors пересчитываются одним энкодером.
Для кандидата нельзя оставлять default output: CLI требует отдельный путь.
Старые пороги cosine/reranker — начальные, после обучения их нужно проверить
и при необходимости настраивать только по validation. Не добивайтесь прежнего
количества accepted изменением labels/порогов без проверки качества.

Проверьте ленту на реальных компаниях/ролях, разнообразие и отсутствие
повторов; не теряйте feedback.sqlite. Сохраните предыдущие веса/каталог для
отката. Только после отдельного решения о качестве/внедрении публикуйте новый
каталог и перезапускайте API. ONNX исходной модели остаётся исходным; новый
Torch checkpoint не превращается автоматически в обновлённый INT8 ONNX.
Экспорт/квантизация нового ONNX не входит в этот код, для внедрения используйте
поддержанный Torch backend или отдельный проверенный экспорт.
