import Badge from "@/src/components/UI/Badge/Badge";
import { DOCS } from "@/src/data/demo";
import { KIND_LABELS } from "@/src/utils/insights";
import type { Interpretation, PersonalizedEvent } from "@/src/types";
import styles from "@/src/styles/Design.module.css";

export const KindBadge = ({
  interpretation,
}: {
  interpretation: Interpretation;
}) => (
  <Badge tone={interpretation.kind}>
    {KIND_LABELS[interpretation.kind]}
    {interpretation.lvl ? ` · ${interpretation.lvl}` : ""}
  </Badge>
);

const InsightMeta = ({
  event,
  progress = false,
}: {
  event: PersonalizedEvent;
  progress?: boolean;
}) => (
  <div className={styles.meta}>
    <KindBadge interpretation={event.p} />
    {event.docs.some((id) => id.startsWith("d")) && (
      <Badge tone="bank">Позиция банка</Badge>
    )}
    <Badge tone="ai">Вывод AI</Badge>
    <span>
      {DOCS[event.docs[0]].k} · {event.ago} · {event.cat}
    </span>
    <span className={styles.rel}>
      {progress && (
        <>
          Релевантность{" "}
          <span className={styles.bar}>
            <i style={{ width: `${event.p.rel}%` }} />
          </span>
        </>
      )}
      {event.p.rel}%
    </span>
  </div>
);

export default InsightMeta;
