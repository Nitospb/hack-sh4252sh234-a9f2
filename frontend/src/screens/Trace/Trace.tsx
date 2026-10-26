"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useClient } from "@/src/providers/ClientProvider";
import PageHeader from "@/src/components/PageHeader/PageHeader";
import Card from "@/src/components/UI/Card/Card";
import Badge from "@/src/components/UI/Badge/Badge";
import StatCard from "@/src/components/UI/StatCard/StatCard";
import StepList from "@/src/components/Agent/StepList/StepList";
import AgentTimeline from "@/src/components/Agent/AgentTimeline/AgentTimeline";
import { createInsightObject } from "@/src/utils/insightObject";
import { eventHref } from "@/src/utils/insights";
import styles from "@/src/styles/Design.module.css";

const Trace = () => {
  const { client, allEvents } = useClient();
  const params = useSearchParams();
  const event =
    allEvents.find((item) => item.id === params.get("id")) ?? allEvents[0];

  return (
    <>
      <PageHeader title="Журнал агента" />
      <p className={styles.sub}>
        Запуск{" "}
        <span className={styles.mono}>
          run_{event.id}_{client.id.slice(2)}
        </span>{" "}
        · «{event.title}» → {client.name} ·{" "}
        <Link className={styles.link} href={eventHref(event.id)}>
          открыть инсайт
        </Link>
      </p>
      <div className={`${styles.g4} ${styles.statGrid}`}>
        <StatCard label="Шагов" value="7" />
        <StatCard label="Время" value="4,1 с" />
        <StatCard label="Токенов" value="11 840" />
        <StatCard
          label="Источников"
          value={event.docs.length + event.p.feats.length}
        />
      </div>
      <div className={styles.grid}>
        <section>
          <AgentTimeline event={event} client={client} />
          <Card
            heading={
              <>
                Итоговый объект инсайта <Badge>insight.schema.json v1</Badge>
              </>
            }
          >
            <pre>
              {JSON.stringify(createInsightObject(event, client.id), null, 2)}
            </pre>
          </Card>
        </section>
        <aside className={`${styles.stack} ${styles.sticky}`}>
          <Card title="Запуски по клиенту" className={styles.runs}>
            {allEvents
              .filter((item) => item.p.rel >= 40)
              .map((item) => (
                <Link
                  key={item.id}
                  href={`/trace?id=${item.id}`}
                  className={item.id === event.id ? styles.on : ""}
                >
                  <span
                    className={styles.statusDot}
                    style={{
                      background: item.p.assume
                        ? "var(--amber)"
                        : "var(--green)",
                    }}
                  />
                  <b>{item.title}</b>
                  <span
                    className={`${styles.muted} ${styles.small}`}
                    style={{ marginLeft: "auto" }}
                  >
                    {item.p.rel}%
                  </span>
                </Link>
              ))}
          </Card>
          <Card title="Контроль безопасности">
            <StepList
              items={[
                {
                  marker: "✓",
                  title: `Доступ только к профилю ${client.id}`,
                  detail: "row-level политика по SYNTHETIC_U",
                },
                {
                  marker: "✓",
                  title: "PII замаскированы",
                  detail: "SYNTHETIC_F не передаются в LLM",
                },
                {
                  marker: "✓",
                  title: "Инструменты только на чтение",
                  detail: "агент не может инициировать операции",
                },
                {
                  marker: "✓",
                  title: "Бюджет токенов",
                  detail: "использовано 3,2% дневного лимита",
                },
              ]}
            />
          </Card>
        </aside>
      </div>
    </>
  );
};

export default Trace;
