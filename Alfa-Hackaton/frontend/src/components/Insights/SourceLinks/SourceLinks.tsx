import Link from "next/link";
import { DOCS } from "@/src/data/demo";
import styles from "@/src/styles/Design.module.css";

const SourceLinks = ({ ids, eventId }: { ids: string[]; eventId?: string }) => (
  <div className={styles.src}>
    Источники:{" "}
    {ids.map((id, index) => (
      <Link key={id} href={`/sources#${id}`}>
        [{index + 1}]{" "}
        {DOCS[id].k === "Альфа-Банк"
          ? `«${DOCS[id].t}»`
          : `${DOCS[id].k}, ${DOCS[id].date}`}
      </Link>
    ))}
    {eventId && <Link href={`/trace?id=${eventId}`}>как получен вывод</Link>}
  </div>
);

export default SourceLinks;
