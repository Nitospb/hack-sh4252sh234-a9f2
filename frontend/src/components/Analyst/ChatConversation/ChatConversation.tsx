"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import Badge from "@/src/components/UI/Badge/Badge";
import QuestionForm from "../QuestionForm/QuestionForm";
import AnalystAnswer from "../AnalystAnswer/AnalystAnswer";
import type { Client, PersonalizedEvent } from "@/src/types";
import { eventHref } from "@/src/utils/insights";
import styles from "@/src/styles/Design.module.css";

interface ChatConversationProps {
  client: Client;
  event: PersonalizedEvent;
  events: PersonalizedEvent[];
  initialQuestion: string;
}

const SUGGESTIONS = [
  "Покажи расчёт по кварталам",
  "Что будет при пессимистичном сценарии?",
  "Какие контрагенты затронуты?",
  "Что думает банк о ставке на 2027?",
];

const ChatConversation = ({
  client,
  event,
  events,
  initialQuestion,
}: ChatConversationProps) => {
  const [questions, setQuestions] = useState<string[]>(
    initialQuestion ? [initialQuestion] : [],
  );
  const messages = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (messages.current)
      messages.current.scrollTop = messages.current.scrollHeight;
  }, [questions]);
  const handleAsk = (question: string) =>
    setQuestions((previous) => [...previous, question]);

  return (
    <section className={styles.chatw} aria-label="Чат с аналитиком">
      <div className={styles.ctx}>
        <span className={styles.muted}>Контекст:</span>
        <Badge>{client.name}</Badge>
        <Link href={eventHref(event.id)} style={{ textDecoration: "none" }}>
          <Badge tone="ai">{event.title}</Badge>
        </Link>
      </div>
      <div ref={messages} className={styles.msgs} role="log" aria-live="polite">
        <div className={`${styles.m} ${styles.a}`}>
          <p>
            Здравствуйте, {client.user.name.split(" ")[0]}! Я разобрал событие{" "}
            <b>«{event.title}»</b> для {client.name}.
          </p>
          <p>
            {event.p.head}. Спросите, если нужно подробнее, в другом разрезе или
            со ссылкой на первоисточник.
          </p>
        </div>
        {questions.map((question, index) => (
          <div className={styles.messagePair} key={`${index}-${question}`}>
            <div className={`${styles.m} ${styles.u}`}>{question}</div>
            <div className={`${styles.m} ${styles.a}`}>
              <AnalystAnswer
                question={question}
                event={event}
                client={client}
                events={events}
              />
            </div>
          </div>
        ))}
      </div>
      <div className={styles.sugg}>
        {SUGGESTIONS.map((suggestion) => (
          <button
            className={styles.pill}
            key={suggestion}
            onClick={() => handleAsk(suggestion)}
          >
            {suggestion}
          </button>
        ))}
      </div>
      <QuestionForm
        onSubmit={handleAsk}
        placeholder="Спросите о событии, компании или рынке…"
      />
    </section>
  );
};

export default ChatConversation;
