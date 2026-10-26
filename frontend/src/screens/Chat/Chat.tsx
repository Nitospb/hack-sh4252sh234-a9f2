"use client";

import { useSearchParams } from "next/navigation";
import { useClient } from "@/src/providers/ClientProvider";
import Card from "@/src/components/UI/Card/Card";
import TextList from "@/src/components/UI/TextList/TextList";
import ChatConversation from "@/src/components/Analyst/ChatConversation/ChatConversation";
import QuestionSuggestions from "@/src/components/Analyst/QuestionSuggestions/QuestionSuggestions";
import styles from "@/src/styles/Design.module.css";

const Chat = () => {
  const { client, events, allEvents } = useClient();
  const params = useSearchParams();
  const event =
    allEvents.find((item) => item.id === params.get("ev")) ??
    events[0] ??
    allEvents[0];
  const initialQuestion = params.get("q") ?? "";

  return (
    <div className={styles.grid}>
      <ChatConversation
        key={`${client.id}-${event.id}-${initialQuestion}`}
        client={client}
        event={event}
        events={events}
        initialQuestion={initialQuestion}
      />
      <aside className={styles.stack}>
        <Card title="Что умеет аналитик">
          <TextList
            items={[
              "Отвечает на уточняющие вопросы по событию",
              "Показывает данные в другом разрезе: по кварталам, контрагентам, продуктам",
              "Ведёт к первоисточнику каждого вывода",
              "Разделяет позицию банка и выводы модели",
            ]}
          />
        </Card>
        <Card title="Ограничения">
          <p
            className={`${styles.small} ${styles.muted}`}
            style={{ margin: 0 }}
          >
            Аналитик не совершает операций и не видит данные других клиентов.
            Ответы — информационные и не являются инвестиционной рекомендацией.
          </p>
        </Card>
        <Card title="Недавние вопросы">
          <QuestionSuggestions
            eventId={event.id}
            questions={[
              "Как пошлина влияет на цены в регионе?",
              "Сравни с прошлым годом",
              "Риски по лизингу",
            ]}
          />
        </Card>
      </aside>
    </div>
  );
};

export default Chat;
