import Link from "next/link";
import Card from "@/src/components/UI/Card/Card";
import type { PersonalizedEvent } from "@/src/types";
import StepList from "../StepList/StepList";
import styles from "@/src/styles/Design.module.css";

const TraceSummary = ({ event }: { event: PersonalizedEvent }) => {
  const steps = [
    ["План анализа", "профиль, новость, аналитика банка"],
    ["Профиль клиента", event.p.feats.slice(0, 2).join(", ")],
    [
      "RAG по аналитике банка",
      `найдено ${event.docs.filter((id) => id.startsWith("d")).length} материала`,
    ],
    ["Самопроверка", event.p.assume || "противоречий не найдено"],
    [
      "Итоговый инсайт",
      `GLM-5.3-Flash · 4,1 с · ${event.docs.length + event.p.feats.length} ссылок`,
    ],
  ];

  return (
    <Card
      title="Как получен вывод"
      action={
        <Link className={styles.link} href={`/trace?id=${event.id}`}>
          Журнал
        </Link>
      }
    >
      <StepList
        items={steps.map(([title, detail], index) => ({
          title,
          detail,
          warning: index === 3 && Boolean(event.p.assume),
          marker: index === 3 && event.p.assume ? "!" : String(index + 1),
        }))}
      />
    </Card>
  );
};

export default TraceSummary;
