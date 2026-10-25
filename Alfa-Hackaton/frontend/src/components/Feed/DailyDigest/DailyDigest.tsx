import Link from "next/link";
import Badge from "@/src/components/UI/Badge/Badge";
import { eventHref } from "@/src/utils/insights";
import type { Client, PersonalizedEvent } from "@/src/types";
import styles from "@/src/styles/Design.module.css";

const DailyDigest = ({
  client,
  events,
  excluded,
}: {
  client: Client;
  events: PersonalizedEvent[];
  excluded: number;
}) => {
  const stats = [
    [events.filter((event) => event.p.kind === "risk").length, "рисков"],
    [events.filter((event) => event.p.kind === "opp").length, "возможностей"],
    [
      new Set(
        events.flatMap((event) =>
          event.docs.filter((id) => id.startsWith("d")),
        ),
      ).size,
      "материалов банка",
    ],
    [excluded, "отсеяно"],
  ];

  return (
    <div className={styles.digest}>
      <div>
        <Badge tone="ai">Сводка дня · AI</Badge>
        <h2>Главное для {client.name.replace(/^(ООО|АО) /, "")}</h2>
        <ul>
          {events.slice(0, 3).map((event) => (
            <li key={event.id}>
              <Link href={eventHref(event.id)}>{event.p.head}</Link>
            </li>
          ))}
        </ul>
        {!events.length && <p>Нет событий выше выбранного порога.</p>}
      </div>
      <div className={styles.stat}>
        {stats.map(([value, label]) => (
          <div key={label}>
            <b>{value}</b>
            <small>{label}</small>
          </div>
        ))}
      </div>
    </div>
  );
};

export default DailyDigest;
