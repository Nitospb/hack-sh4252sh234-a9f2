"use client";

import { CLIENTS, EVENTS } from "@/src/data/demo";
import PageHeader from "@/src/components/PageHeader/PageHeader";
import SectionHeader from "@/src/components/SectionHeader/SectionHeader";
import Card from "@/src/components/UI/Card/Card";
import { KindBadge } from "@/src/components/Insights/InsightMeta/InsightMeta";
import ClientCard from "@/src/components/Clients/ClientCard/ClientCard";
import ClientSearch from "@/src/components/Clients/ClientSearch/ClientSearch";
import styles from "@/src/styles/Design.module.css";

const Clients = () => (
  <>
    <PageHeader
      title="Выбор клиента"
      description="Демо-режим для жюри: выберите компанию из обезличенного датасета — лента, интерпретации и рекомендации пересчитаются под её контекст."
      breadcrumbs={false}
    />
    <div className={styles.g3}>
      {CLIENTS.map((client) => (
        <ClientCard key={client.id} client={client} />
      ))}
    </div>
    <SectionHeader
      title="Как одна новость читается для разных клиентов"
      description="событие e1 · ключевая ставка 14%"
      spaced
    />
    <div className={styles.g3}>
      {CLIENTS.map((client) => {
        const interpretation = EVENTS[0].per[client.id];
        if (!interpretation) return null;
        return (
          <Card key={client.id}>
            <div className={styles.meta}>
              <KindBadge interpretation={interpretation} />
              <span className={styles.rel}>{interpretation.rel}%</span>
            </div>
            <h3 style={{ margin: "10px 0 6px" }}>{interpretation.head}</h3>
            <p className={styles.muted}>{client.name}</p>
            <p>{interpretation.why}</p>
          </Card>
        );
      })}
    </div>
    <SectionHeader title="Другой клиент из датасета" spaced />
    <ClientSearch />
  </>
);

export default Clients;
