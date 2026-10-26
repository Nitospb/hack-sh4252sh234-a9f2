# Сторонние компоненты, данные и интеграции

Версии frontend закреплены в `frontend/package-lock.json`, online
Python — `service/requirements.lock`, ML/training/parser — в своих lockfiles.
Полные лицензии поставляются с пакетами; при распространении бинарных образов
сохраняйте их LICENSE/NOTICE. Этот перечень не передаёт права на исходные тексты.

| Компонент | Лицензия / использование |
|---|---|
| Python | PSF License; API и обработка данных |
| SQLite | Public Domain; каталог, FTS5 и состояние |
| Node.js | MIT и включённые third-party notices; web runtime |
| Next.js, React, React DOM | MIT; интерфейс и серверный BFF |
| `react-iconly` | MIT; набор Iconly v2 в активном интерфейсе по запросу пользователя |
| Swagger UI (`swagger-ui-dist`) | Apache-2.0; интерактивная документация API |
| TypeScript, jsonschema | Apache-2.0 / MIT соответственно |
| NumPy | BSD-3-Clause; готовые векторы и MMR |
| attrs, referencing, jsonschema-specifications | MIT; валидация JSON |
| rpds-py | MIT; структуры валидации |
| Tesseract / tessdata_fast | Apache-2.0; локальный OCR rus/eng |
| pypdfium2 / PDFium | Apache-2.0 OR BSD-3-Clause wrapper; PDFium BSD-style и bundled dependencies; см. установленные notices |
| Pillow | MIT-CMU; рендеры страниц для OCR |
| ESLint / Tailwind CSS | MIT; разработка интерфейса |
| Docker base images | Python slim Debian / Node Alpine; лицензии системных компонентов остаются внутри образов |

Знак Альфа-Банка в `frontend/public/alfa-bank-logo.svg`, `frontend/app/icon.svg`
и производном `favicon.ico` взят из [официального набора Alfa Laboratory](https://github.com/alfa-laboratory/icons/blob/master/packages/classic/src/LogoAlfabankSquareXlColorIcon.tsx).
Товарный знак принадлежит АО «Альфа-Банк».

Иллюстрации онбординга загружаются по URL с официального CDN Альфа-Банка;
исходные страницы: [Альфа-Бизнес](https://alfabank.ru/sme/digital-bank/),
[зарплатный проект](https://alfabank.ru/corporate/salaryproject/) и
[кредитная линия](https://alfabank.ru/sme/profits/creditline/). Файлы не
включены в репозиторий; права на изображения остаются у правообладателя.
Показ зависит от доступности CDN, ссылки на источники есть в модалке.
Публичные цветовые и размерные токены [Core Components](https://github.com/core-ds/core-components)
использованы как референс для локальных CSS-переменных; библиотека распространяется
под MIT. `/kit` — адаптация команды, не официальный продукт банка.

Модели и ML-библиотеки перечислены с ревизиями и ограничениями в
[news_matching/THIRD_PARTY_NOTICES.md](news_matching/THIRD_PARTY_NOTICES.md).
E5 MIT и reranker Apache-2.0 используются локально. Они не являются собственной
обученной на хакатоне моделью. Обучение пока не запускалось.
Состав Selenium/Chrome/извлечения текста:
[parser/THIRD_PARTY_NOTICES.md](parser/THIRD_PARTY_NOTICES.md).

Генеративный анализ обращается только к шлюзу организаторов и разрешённым ими
моделям. Это внешняя интеграция с серверным ключом и общим командным бюджетом;
модельные веса этих LLM в репозитории/образах не распространяются.
Параметр Qwen reasoning и его фактическое поведение контролируются по usage,
а не представляются гарантией экономии у любого совместимого шлюза.

CSV компаний/платежей и PDF банка предоставлены для задания. Новостные тексты,
изображения и Telegram-посты принадлежат источникам; URL, тип, дата и provenance
сохраняются. Лицензии кода не означают лицензию на публикацию полного корпуса.
Изображения хранятся ссылками. Telegram — внутренняя аналитика, не ML-training.

Синтетический smoke seed — авторские тестовые записи, явно помеченные;
`example.invalid` не является реальным новостным источником. Локальный user_id,
оболочка банка и internal token прототипа не имитируют настоящий банковский IAM.
В активных разделах нет выдуманных счетов/кредитов/личных менеджеров.
Старые макетные компоненты src/data остаются в исходниках для совместимости,
но не являются фактами активного API.
