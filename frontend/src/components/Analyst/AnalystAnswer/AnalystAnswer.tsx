import Link from "next/link";
import Badge from "@/src/components/UI/Badge/Badge";
import DataTable from "@/src/components/UI/DataTable/DataTable";
import SourceLinks from "@/src/components/Insights/SourceLinks/SourceLinks";
import TextList from "@/src/components/UI/TextList/TextList";
import { DOCS, EVENTS } from "@/src/data/demo";
import type { Client, PersonalizedEvent } from "@/src/types";
import styles from "@/src/styles/Design.module.css";

interface AnalystAnswerProps {
  question: string;
  event: PersonalizedEvent;
  client: Client;
  events: PersonalizedEvent[];
}

const AnswerSteps = ({ steps }: { steps: string[] }) => (
  <div className={styles.steps}>
    {steps.map((step) => (
      <span key={step}>✓ {step}</span>
    ))}
  </div>
);

const AnalystAnswer = ({
  question,
  event,
  client,
  events,
}: AnalystAnswerProps) => {
  const text = question.toLowerCase();
  if (/квартал|цифр|расчёт/.test(text))
    return (
      <>
        <AnswerSteps
          steps={["профиль клиента", "график платежей", "прогноз ставки банка"]}
        />
        {client.id === "U-10482" && event.id === "e1" ? (
          <>
            <p>
              Оценка влияния по кварталам при сценарии Альфа-Банка
              <sup>
                <Link href="/sources#d1">1</Link>
              </sup>
              :
            </p>
            <DataTable
              headers={["Квартал", "Ставка (прогноз банка)", "Доп. расходы"]}
              rows={[
                ["4К26", "14,0%", "15 млн ₽"],
                ["1К27", "14,0%", "15 млн ₽"],
                ["2К27", "13,5%", "11 млн ₽"],
                ["3К27", "13,0%", "7 млн ₽"],
              ]}
            />
            <p className={styles.small}>
              <Badge tone="bank">Банк</Badge> прогноз ставки ·{" "}
              <Badge tone="ai">AI</Badge> перерасчёт на ваш лимит
            </p>
          </>
        ) : (
          <>
            <p>{event.p.why}</p>
            <TextList items={[...event.p.ai, ...event.p.risks]} />
            <p className={styles.muted}>
              Для поквартального расчёта нужны сроки и объёмы контрактов
              компании.
            </p>
          </>
        )}
        <SourceLinks ids={event.docs} />
      </>
    );
  if (text.includes("контрагент"))
    return (
      <>
        <AnswerSteps
          steps={["граф платежей", "поиск новостей по контрагентам"]}
        />
        <p>
          По вашим контрагентам за 7 дней —{" "}
          {events.filter((item) => item.cat === "Контрагенты").length} значимых
          событий. Крупнейшие связи:
        </p>
        <DataTable
          headers={["Контрагент", "Отрасль", "Платежи, 6 мес.", "Роль"]}
          rows={client.counter}
        />
        <p>
          <Link className={styles.link} href="/profile#graph">
            Открыть граф связей →
          </Link>
        </p>
      </>
    );
  if (text.includes("банк") || text.includes("2027"))
    return (
      <>
        <AnswerSteps steps={["RAG: аналитика банка"]} />
        <p>
          <Badge tone="bank">Позиция Альфа-Банка</Badge> {EVENTS[0].bank}
          <sup>
            <Link href="/sources#d1">1</Link>
          </sup>
          <sup>
            <Link href="/sources#d2">2</Link>
          </sup>
        </p>
        <p>
          Первоисточник: <Link href="/sources#d1">«{DOCS.d1.t}»</Link>
        </p>
      </>
    );
  if (text.includes("пессимист"))
    return (
      <>
        <AnswerSteps steps={["сценарный анализ", "самопроверка"]} />
        <p>
          <Badge tone="ai">AI</Badge> В пессимистичном сценарии (событие
          затягивается на 2 квартала) эффект примерно в 1,8 раза сильнее
          базового: {event.p.risks[0]?.toLowerCase() ?? "влияние усиливается"}.
        </p>
        <p>
          <Badge tone="watch">ДОПУЩЕНИЕ</Badge>{" "}
          {event.p.assume ||
            "Сценарий построен моделью, в материалах банка его нет."}
        </p>
      </>
    );
  return (
    <>
      <AnswerSteps steps={["план", "профиль клиента", "RAG", "самопроверка"]} />
      <p>
        {event.p.head}. {event.p.why}
      </p>
      <p>
        <b>Что можно сделать:</b>{" "}
        {event.p.actions.join("; ").toLowerCase() || "наблюдать"}.
      </p>
      <SourceLinks ids={event.docs} />
    </>
  );
};

export default AnalystAnswer;
