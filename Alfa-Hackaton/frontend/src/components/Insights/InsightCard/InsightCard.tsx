import Link from "next/link";
import type { PersonalizedEvent } from "@/src/types";
import { eventHref, getEventTitle } from "@/src/utils/insights";
import InsightMeta from "../InsightMeta/InsightMeta";
import Promotion from "../Promotion/Promotion";
import styles from "@/src/styles/Design.module.css";

const InsightCard = ({ event }: { event: PersonalizedEvent }) => (
  <Link className={styles.item} href={eventHref(event.id)}>
    <InsightMeta event={event} />
    <h4>{getEventTitle(event)}</h4>
    <p>{event.p.why}</p>
    <span className={styles.go} aria-hidden="true">
      ›
    </span>
    <Promotion promotion={event.p.promo} />
  </Link>
);

export default InsightCard;
