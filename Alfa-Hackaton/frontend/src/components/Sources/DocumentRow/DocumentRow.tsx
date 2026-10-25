import Link from "next/link";
import Avatar from "@/src/components/UI/Avatar/Avatar";
import Button from "@/src/components/UI/Button/Button";
import type { PersonalizedEvent, SourceDocument } from "@/src/types";
import { eventHref } from "@/src/utils/insights";
import styles from "@/src/styles/Design.module.css";

interface DocumentRowProps {
  id: string;
  document: SourceDocument;
  events: PersonalizedEvent[];
  bank?: boolean;
}

const DocumentRow = ({ id, document, events, bank }: DocumentRowProps) => (
  <div className={styles.doc} id={id}>
    <Avatar
      text={bank ? "А" : document.k[0]}
      size={40}
      radius={10}
      background={bank ? "var(--red)" : "var(--ink)"}
    />
    <div>
      <b>{document.t}</b>
      <br />
      <small>
        {document.k} · {document.date} · {document.type}
      </small>
      {events.length > 0 && (
        <div>
          <small>
            Используется в:{" "}
            {events.map((event, index) => (
              <span key={event.id}>
                {index > 0 && ", "}
                <Link
                  href={eventHref(event.id)}
                  style={{ color: "var(--red)" }}
                >
                  {event.title}
                </Link>
              </span>
            ))}
          </small>
        </div>
      )}
    </div>
    <Button href={`#${id}`} variant="outline">
      Открыть
    </Button>
  </div>
);

export default DocumentRow;
