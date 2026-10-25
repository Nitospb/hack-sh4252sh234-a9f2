"use client";

import { useRouter } from "next/navigation";
import { useClient } from "@/src/providers/ClientProvider";
import Card from "@/src/components/UI/Card/Card";
import Button from "@/src/components/UI/Button/Button";
import Avatar from "@/src/components/UI/Avatar/Avatar";
import KeyValueList from "@/src/components/UI/KeyValueList/KeyValueList";
import ProductTags from "@/src/components/Company/ProductTags/ProductTags";
import { KindBadge } from "@/src/components/Insights/InsightMeta/InsightMeta";
import { eventHref, getClientEvents } from "@/src/utils/insights";
import type { Client } from "@/src/types";
import styles from "@/src/styles/Design.module.css";

const ClientCard = ({ client }: { client: Client }) => {
  const { client: current, selectClient } = useClient();
  const router = useRouter();
  const events = getClientEvents(client).filter((event) => event.p.rel >= 40);
  const handleSelect = (href: string) => {
    selectClient(client.id);
    router.push(href);
  };

  return (
    <Card
      className={`${styles.cl} ${current.id === client.id ? styles.on : ""}`}
    >
      <div className={styles.hd}>
        <Avatar text={client.short} size={44} />
        <div>
          <b>{client.name}</b>
          <div className={`${styles.muted} ${styles.small}`}>
            {client.id} · {client.clType}
          </div>
        </div>
      </div>
      <KeyValueList
        items={[
          ["ОКВЭД", `${client.okved} · ${client.okvedName}`],
          ["Выручка", client.revenue],
          ["Стадия", `${client.stage} · ${client.age}`],
          ["Регион", client.region],
          ["ФТС", client.fts],
          [
            "Пользователь",
            `${client.user.name}, ${client.user.role.toLowerCase()}`,
          ],
        ]}
      />
      <ProductTags products={client.products} />
      <div className={`${styles.muted} ${styles.small}`}>
        Топ-3 события в ленте · всего {events.length}
      </div>
      <div className={styles.mini}>
        {events.slice(0, 3).map((event) => (
          <button
            className={styles.miniEvent}
            key={event.id}
            onClick={() => handleSelect(eventHref(event.id))}
          >
            <KindBadge interpretation={event.p} />
            <span>{event.title}</span>
            <b>{event.p.rel}%</b>
          </button>
        ))}
      </div>
      <Button
        variant={current.id === client.id ? "dark" : "primary"}
        onClick={() => handleSelect("/")}
      >
        {current.id === client.id
          ? "Текущий клиент · открыть"
          : "Войти как клиент"}
      </Button>
    </Card>
  );
};

export default ClientCard;
