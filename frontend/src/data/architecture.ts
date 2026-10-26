export interface ArchitectureNode {
  title: string;
  description: string;
  tone?: "bank" | "agent";
}

export const ARCHITECTURE_LANES: {
  title: string;
  nodes: ArchitectureNode[];
}[] = [
  {
    title: "1 · Сбор",
    nodes: [
      {
        title: "Парсер новостей",
        description: "RSS, API лент, сайты ведомств",
      },
      {
        title: "Аналитика Альфа-Банка",
        description: "PDF → чанки → векторный индекс",
        tone: "bank",
      },
      { title: "Данные клиентов", description: "3 CSV датасета → PostgreSQL" },
    ],
  },
  {
    title: "2 · Обработка",
    nodes: [
      { title: "Дедупликация", description: "MinHash + кластеризация" },
      { title: "Классификация", description: "тема, отрасль ОКВЭД, сущности" },
      { title: "Граф связей", description: "платежи + общие физлица" },
    ],
  },
  {
    title: "3 · Отбор",
    nodes: [
      {
        title: "Кандидаты",
        description: "совпадение ОКВЭД / продуктов / контрагентов",
      },
      {
        title: "Ранжирование",
        description: "скоринг по признакам клиента + feedback",
      },
      { title: "Порог значимости", description: "по умолчанию 40%" },
    ],
  },
  {
    title: "4 · Агент интерпретации",
    nodes: [
      {
        title: "Планировщик",
        description: "какие данные и шаги нужны",
        tone: "agent",
      },
      {
        title: "Инструменты",
        description: "profile · rag_search · graph · news",
        tone: "agent",
      },
      {
        title: "Самопроверка",
        description: "полнота, противоречия → повтор",
        tone: "agent",
      },
      {
        title: "Синтез",
        description: "JSON по схеме insight.v1",
        tone: "agent",
      },
    ],
  },
  {
    title: "5 · Доставка",
    nodes: [
      { title: "API ленты", description: "FastAPI · OpenAPI" },
      { title: "Интернет-банк", description: "виджет на главной, лента, чат" },
      { title: "Мониторинг", description: "метрики, логи, экспертная очередь" },
    ],
  },
];

export const SECURITY_POINTS: [string, string][] = [
  [
    "Разграничение доступа",
    "агент работает в контексте одного SYNTHETIC_U, row-level политики в БД",
  ],
  [
    "Чувствительные данные",
    "идентификаторы физлиц и суммы маскируются до передачи в LLM",
  ],
  ["Журнал", "каждый вызов инструмента и модели пишется в trace с хешем входа"],
  [
    "Ограничения действий",
    "инструменты только на чтение, операции в банке недоступны",
  ],
  [
    "Prompt injection",
    "текст новостей передаётся как данные, инструкции из него игнорируются",
  ],
];

export const SCALING_POINTS: [string, string][] = [
  [
    "Новые отрасли",
    "таксономия ОКВЭД → темы задаётся конфигом, без переобучения",
  ],
  ["Новые источники", "коннектор = класс с интерфейсом fetch/normalize"],
  ["Новые типы клиентов", "признаки описаны схемой, веса настраиваются"],
  [
    "Нагрузка",
    "событие обрабатывается один раз, интерпретация — только для прошедших отбор пар (≈ 2–4% от всех)",
  ],
  ["Кэш", "одинаковые пары «событие × сегмент» переиспользуются"],
];
