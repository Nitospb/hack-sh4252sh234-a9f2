"use client";

import { usePersistentState } from "@/src/hooks/usePersistentState";
import Card from "@/src/components/UI/Card/Card";
import Toggle from "@/src/components/UI/Toggle/Toggle";
import type { Client } from "@/src/types";
import styles from "@/src/styles/Design.module.css";

const CompanyInterests = ({ client }: { client: Client }) => {
  const defaults: Record<string, boolean> = {
    "Стоимость финансирования": true,
    "Курсы валют": client.fts !== "Россия",
    "Цены на сырьё и топливо": true,
    Контрагенты: true,
    "Регулирование отрасли": true,
    "Налоги и отчётность": false,
    "Персонал и ФОТ": false,
  };
  const [interests, setInterests] = usePersistentState(
    `alfa-interests-${client.id}`,
    defaults,
  );

  return (
    <Card title={`Ваши интересы как ${client.user.role.toLowerCase()}`}>
      {Object.entries(interests).map(([label, checked]) => (
        <div className={styles.int} key={label}>
          {label}
          <Toggle
            label={label}
            checked={checked}
            onChange={(value) =>
              setInterests((previous) => ({ ...previous, [label]: value }))
            }
          />
        </div>
      ))}
    </Card>
  );
};

export default CompanyInterests;
