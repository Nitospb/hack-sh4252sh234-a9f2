"use client";

import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { useClient } from "@/src/providers/ClientProvider";
import PageHeader from "@/src/components/PageHeader/PageHeader";
import Card from "@/src/components/UI/Card/Card";
import Button from "@/src/components/UI/Button/Button";
import Badge from "@/src/components/UI/Badge/Badge";
import InfoBox from "@/src/components/UI/InfoBox/InfoBox";
import TextList from "@/src/components/UI/TextList/TextList";
import InsightMeta from "@/src/components/Insights/InsightMeta/InsightMeta";
import ArticleSection from "@/src/components/Insights/ArticleSection/ArticleSection";
import SourceList from "@/src/components/Insights/SourceList/SourceList";
import Promotion from "@/src/components/Insights/Promotion/Promotion";
import FeedbackCard from "@/src/components/Insights/FeedbackCard/FeedbackCard";
import FeatureTags from "@/src/components/Company/FeatureTags/FeatureTags";
import AnalystCard from "@/src/components/Analyst/AnalystCard/AnalystCard";
import TraceSummary from "@/src/components/Agent/TraceSummary/TraceSummary";
import { chatHref } from "@/src/utils/insights";
import styles from "@/src/styles/Design.module.css";

const Event = () => {
  const { client, allEvents } = useClient();
  const params = useSearchParams();
  const requested = params.get("id");
  const event = requested
    ? allEvents.find((item) => item.id === requested)
    : allEvents[0];

  if (!event)
    return (
      <>
        <PageHeader title="Разбор события" />
        <Card className={styles.empty}>
          <h3>Событие не значимо для {client.name}</h3>
          <p>
            Сервис отсеял его при персональном отборе: нет связи с признаками
            компании.
          </p>
          <Button href="/feed" variant="primary">
            К ленте
          </Button>
        </Card>
      </>
    );

  const { p } = event;
  return (
    <>
      <nav className={styles.crumbs} aria-label="Хлебные крошки">
        <Link href="/">Главная</Link> /{" "}
        <Link href="/feed">Новостная аналитика</Link> / Разбор события
      </nav>
      <div className={styles.grid}>
        <article className={styles.art}>
          <InsightMeta event={event} progress />
          <h1>{p.head}</h1>
          <p className={styles.lead}>{event.title}</p>
          <ArticleSection number="01" title="Что произошло?">
            <p>
              <Badge tone="fact">ФАКТ</Badge> {event.fact}
              <sup>
                <a href="#src">1</a>
              </sup>
            </p>
          </ArticleSection>
          <ArticleSection
            number="02"
            title="Почему это важно для вашей компании?"
          >
            <p>{p.why}</p>
            <FeatureTags features={p.feats} />
          </ArticleSection>
          <ArticleSection number="03" title="Какие последствия возможны?">
            <div className={styles.ro}>
              <InfoBox title="Риски" tone="bank">
                <TextList items={p.risks} />
              </InfoBox>
              <InfoBox title="Возможности" tone="fct">
                <TextList items={p.opps} />
              </InfoBox>
            </div>
            {p.assume && (
              <p>
                <Badge tone="watch">ДОПУЩЕНИЕ</Badge> {p.assume}
              </p>
            )}
          </ArticleSection>
          <ArticleSection
            number="04"
            title="Какие действия могут быть релевантны?"
            id="act"
          >
            {p.actions.length ? (
              <TextList items={p.actions} ordered />
            ) : (
              <p className={styles.muted}>
                Действий не требуется — достаточно наблюдать.
              </p>
            )}
            <Promotion promotion={p.promo} />
          </ArticleSection>
          <ArticleSection number="05" title="Как это оценивает банк?">
            <div className={styles.ro}>
              <InfoBox
                title={<Badge tone="bank">Позиция Альфа-Банка</Badge>}
                tone="bank"
              >
                <p>{event.bank}</p>
              </InfoBox>
              <InfoBox title={<Badge tone="ai">Сформировано AI</Badge>}>
                <TextList items={p.ai} />
              </InfoBox>
            </div>
          </ArticleSection>
          <ArticleSection number="06" title="На чём основан вывод?" id="src">
            <SourceList ids={event.docs} features={p.feats} />
          </ArticleSection>
          <div className={styles.act}>
            <Button href="tel:88001007733" variant="primary">
              Обсудить с менеджером
            </Button>
            <Button href={chatHref("", event.id)}>
              Задать уточняющий вопрос
            </Button>
            <Button href={`/trace?id=${event.id}`}>Журнал агента</Button>
          </div>
        </article>
        <aside className={`${styles.stack} ${styles.sticky}`}>
          <AnalystCard
            title="Спросить об этом событии"
            eventId={event.id}
            questions={[
              "Что будет при пессимистичном сценарии?",
              "Покажи расчёт в цифрах",
              "Кого ещё из наших контрагентов это затронет?",
            ]}
          />
          <TraceSummary event={event} />
          <FeedbackCard
            key={`${client.id}-${event.id}`}
            clientId={client.id}
            eventId={event.id}
          />
        </aside>
      </div>
    </>
  );
};

export default Event;
