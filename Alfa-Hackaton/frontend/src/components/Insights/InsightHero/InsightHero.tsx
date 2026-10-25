import Button from "@/src/components/UI/Button/Button";
import InfoBox from "@/src/components/UI/InfoBox/InfoBox";
import TextList from "@/src/components/UI/TextList/TextList";
import type { PersonalizedEvent } from "@/src/types";
import { chatHref, eventHref, getEventTitle } from "@/src/utils/insights";
import InsightMeta from "../InsightMeta/InsightMeta";
import SourceLinks from "../SourceLinks/SourceLinks";
import styles from "@/src/styles/Design.module.css";

const InsightHero = ({ event }: { event: PersonalizedEvent }) => (
  <article className={styles.hero}>
    <InsightMeta event={event} progress />
    <h3>{getEventTitle(event)}</h3>
    <div className={styles.why}>
      <b>Почему вам:</b>
      <span>{event.p.why}</span>
    </div>
    <div className={styles.cols}>
      <InfoBox title="Как оценивает Альфа-Банк" tone="bank">
        <p style={{ margin: 0 }}>{event.bank}</p>
      </InfoBox>
      <InfoBox title="Что это значит для вас">
        <TextList items={[...event.p.risks, ...event.p.opps].slice(0, 2)} />
      </InfoBox>
    </div>
    <div className={styles.act}>
      <Button href={eventHref(event.id)} variant="primary">
        Разбор полностью
      </Button>
      <Button href={chatHref("", event.id)}>Задать вопрос</Button>
      {event.p.actions[0] && (
        <Button href={`${eventHref(event.id)}#act`}>
          {event.p.actions[0]}
        </Button>
      )}
    </div>
    <SourceLinks ids={event.docs} eventId={event.id} />
  </article>
);

export default InsightHero;
