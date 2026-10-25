import { DOCS } from "@/src/data/demo";
import type { PersonalizedEvent, Client } from "@/src/types";
import styles from "@/src/styles/Design.module.css";

const AgentTimeline = ({
  event,
  client,
}: {
  event: PersonalizedEvent;
  client: Client;
}) => {
  const bank = event.docs.filter((id) => id.startsWith("d"));
  const steps = [
    {
      title: "Планирование",
      model: "Gemma 4 26B A4B",
      time: "0,3 с",
      text: "Цель: оценить влияние события на клиента. План: профиль → классификация события → поиск материалов банка → сопоставление → синтез → самопроверка.",
      tools: ["plan()"],
    },
    {
      title: "Классификация события",
      model: "Gemma 4 26B A4B",
      time: "0,4 с",
      text: `Категория: ${event.cat}. Извлечены факты, участники, дата. Дубликаты: объединено 3 публикации в одно событие.`,
      tools: ["classify_news(id)", "dedup()"],
    },
    {
      title: "Профиль клиента",
      model: "—",
      time: "0,1 с",
      text: `Загружены признаки: ${event.p.feats.join(", ")}.`,
      tools: [`get_client_profile(${client.id})`, "get_payments_graph()"],
    },
    {
      title: "Поиск аналитики банка (RAG)",
      model: "—",
      time: "0,6 с",
      text: bank.length
        ? `Найдено ${bank.length}: ${bank.map((id) => `«${DOCS[id].t}»`).join(", ")}.`
        : "Релевантных материалов банка не найдено (top-score 0,41 < 0,6).",
      tools: ["rag_search(alfa_research, k=5)"],
    },
    {
      title: "Самопроверка",
      model: "GLM-5.3-Flash",
      time: "0,9 с",
      text: event.p.assume
        ? `Обнаружен пробел: ${event.p.assume} Действие: повторный запрос профиля → данных нет → вывод помечен как допущение.`
        : "Проверены полнота и непротиворечивость: все выводы связаны с источниками.",
      tools: ["verify_claims()", "get_client_profile(retry)"],
      warning: Boolean(event.p.assume),
    },
    {
      title: "Синтез интерпретации",
      model: "GLM-5.3-Flash",
      time: "1,6 с",
      text: `Сформированы ответы на 6 вопросов. Позиция банка и выводы модели разделены. Релевантность: ${event.p.rel}%.`,
      tools: ["synthesize(schema=insight.v1)"],
      accent: true,
    },
    {
      title: "Валидация схемы и публикация",
      model: "—",
      time: "0,2 с",
      text: "JSON соответствует схеме, все ссылки на источники разрешены. Инсайт добавлен в ленту.",
      tools: ["validate_json()", "publish_feed()"],
    },
  ];

  return (
    <div className={styles.tl}>
      {steps.map((step, index) => (
        <div
          key={step.title}
          className={`${styles.st} ${step.warning ? styles.w : ""} ${step.accent ? styles.r : ""}`}
          data-n={step.warning ? "!" : index + 1}
        >
          <h4>
            {step.title}
            <span className={styles.mono}>
              {step.model} · {step.time}
            </span>
          </h4>
          <p>{step.text}</p>
          {step.tools.map((tool) => (
            <span className={styles.tool} key={tool}>
              {tool}
            </span>
          ))}
        </div>
      ))}
    </div>
  );
};

export default AgentTimeline;
