"use client";

import Link from "next/link";
import { useClient } from "@/src/providers/ClientProvider";
import Card from "@/src/components/UI/Card/Card";
import FilterPills from "@/src/components/UI/FilterPills/FilterPills";
import FeatureTags from "@/src/components/Company/FeatureTags/FeatureTags";
import KeyValueList from "@/src/components/UI/KeyValueList/KeyValueList";
import styles from "@/src/styles/Design.module.css";

const FeedSidebar = ({
  period,
  onPeriodChange,
}: {
  period: string;
  onPeriodChange: (period: string) => void;
}) => {
  const { events, settings } = useClient();
  return (
    <aside className={`${styles.stack} ${styles.sticky}`}>
      <Card title="Период">
        <FilterPills
          label="Период событий"
          value={period}
          onChange={onPeriodChange}
          options={[
            { value: "today", label: "Сегодня" },
            { value: "7", label: "7 дней" },
            { value: "30", label: "30 дней" },
          ]}
        />
      </Card>
      <Card title="Почему вы видите эти события">
        <p
          className={`${styles.small} ${styles.muted}`}
          style={{ margin: "0 0 8px" }}
        >
          Ранжирование учитывает признаки вашей компании:
        </p>
        <FeatureTags
          features={[
            ...new Set(events.flatMap((event) => event.p.feats)),
          ].slice(0, 8)}
        />
        <Link className={`${styles.link} ${styles.blockLink}`} href="/profile">
          Уточнить контекст →
        </Link>
      </Card>
      <Card title="Подписка">
        <KeyValueList
          items={[
            ["Push", settings.push ? "риски «высокий»" : "выключены"],
            ["E-mail", settings.digest ? "утренняя сводка 8:30" : "выключен"],
          ]}
        />
        <Link className={`${styles.link} ${styles.blockLink}`} href="/settings">
          Настроить →
        </Link>
      </Card>
    </aside>
  );
};

export default FeedSidebar;
