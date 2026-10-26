# Дизайн-система интерфейса аналитики

Основа — публичная библиотека Альфа-Банка [Core Components](https://github.com/core-ds/core-components)
и её [Storybook](https://core-ds.github.io/core-components/master/?path=/docs/components-overview--docs).
На 26.10.2026 публичный `core-ds/core-components` активен; старый
`alfa-laboratory/arui-feather` помечен как deprecated. Внутренние макеты Figma
и закрытые продуктовые правила не использовались. Наша страница `/kit` —
адаптация публичных референсов, а не официальная сборка Core.

## Источники и решения

| Что | Официальный источник | Как применено |
|---|---|---|
| Цвета | [Палитра](https://github.com/core-ds/core-components/blob/master/packages/vars/src/colors-bluetint.css), [бренд](https://github.com/core-ds/core-components/blob/master/packages/vars/src/colors-brand.css) | Красный `#EF3124`, почти чёрный текст, белые и серые поверхности, статусные цвета в `frontend/src/styles/alfa-tokens.css` |
| Отступы и радиусы | [Отступы](https://github.com/core-ds/core-components/blob/master/packages/vars/src/gaps.css), [радиусы](https://github.com/core-ds/core-components/blob/master/packages/vars/src/border-radius.css) | Шаги 4/8/12/16/20/24/32/40/48 и радиусы 8/10/12/16/24 |
| Типографика | [Руководство](https://github.com/core-ds/core-components/blob/master/docs/typography.stories.mdx), [переменные](https://github.com/core-ds/core-components/blob/master/packages/vars/src/typography-vars.css) | Системный шрифт Core; проприетарные гарнитуры не скачиваются |
| Кнопки | [Варианты и размеры](https://github.com/core-ds/core-components/blob/master/packages/button/src/docs/description.mdx), [токены](https://github.com/core-ds/core-components/blob/master/packages/button/src/vars.css) | Accent, primary, secondary, outlined, text; высоты 32/40/48/56. Старые имена `variant` в нашем API сохранены |
| Поля и формы | [Input](https://github.com/core-ds/core-components/blob/master/packages/input/src/docs/description.mdx), [доступность форм](https://github.com/core-ds/core-components/blob/master/docs/forms.stories.mdx) | `TextField` с подписью, подсказкой, ошибкой и disabled; на десктопе подпись внутри, на мобильном снаружи |
| Пиктограммы | [React Iconly](https://github.com/jrgarciadev/react-iconly) | По запросу пользователя `UI/Icon` использует набор Iconly v2 в стиле `light`, пакет `react-iconly@2.2.10` под MIT |
| Доступность | [Руководство](https://github.com/core-ds/core-components/blob/master/docs/accessibility.stories.mdx), [общие переменные](https://github.com/core-ds/core-components/blob/master/packages/vars/src/common.css) | Нативные элементы, текстовые подписи, фокус синим `#2288FA`; роль статуса не передаётся одним цветом |

Факты, позиция банка, оценка AI и пользовательские условия остаются разными
смысловыми категориями нашего продукта. Их метки и состояния на `/kit` — наша
адаптация; Core не задаёт для них бизнес-смысл и не удостоверяет факты.

## Использование в коде

- Добавляйте общие цветовые, пространственные и размерные значения в
  `frontend/src/styles/alfa-tokens.css` с проверкой публичного источника.
- Используйте `UI/Button`, `UI/TextField`, `UI/FilterPills`, `UI/Toggle`,
  `UI/Badge`, `UI/Card` и `UI/Icon`; примеры находятся на `/kit`.
- Сохраняйте `aria-label`, `aria-invalid`, сообщения об ошибках и порядок
  фокуса. Для мобильного веба интерактивные контролы делайте не ниже 48 px,
  кроме явно компактных элементов.
- Локальные алиасы `--red`, `--ink`, `--bg` в `app/globals.css` служат для
  совместимости существующих экранов. Новые компоненты должны обращаться к
  семантическим токенам.

Общая рамка приложения основана на приложенном пользователем референсе:
прозрачная компактная колонка навигации с подписями пунктов, скруглённый знак,
горизонтальные вкладки и светлые карточки. Иконки Iconly — отдельное решение пользователя,
они не входят в Core Components. При изменениях проверяйте `/kit`, ленту и
основные рабочие маршруты на широком и узком экране, затем выполняйте
frontend lint/build. Внутренние экранные CSS ещё требуют дальнейшей миграции
от жёстко записанных цветов и отдельной UX-приёмки.
