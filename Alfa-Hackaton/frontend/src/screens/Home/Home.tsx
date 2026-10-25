"use client";

import Link from "next/link";
import { useClient } from "@/src/providers/ClientProvider";
import PageHeader from "@/src/components/PageHeader/PageHeader";
import SectionHeader from "@/src/components/SectionHeader/SectionHeader";
import StatCard from "@/src/components/UI/StatCard/StatCard";
import Icon from "@/src/components/UI/Icon/Icon";
import InsightHero from "@/src/components/Insights/InsightHero/InsightHero";
import InsightCard from "@/src/components/Insights/InsightCard/InsightCard";
import EmptyFeed from "@/src/components/Insights/EmptyFeed/EmptyFeed";
import CompanyContext from "@/src/components/Company/CompanyContext/CompanyContext";
import AnalystCard from "@/src/components/Analyst/AnalystCard/AnalystCard";
import TraceSummary from "@/src/components/Agent/TraceSummary/TraceSummary";
import styles from "@/src/styles/Design.module.css";

const Home = () => {
  const { client, events } = useClient();
  const hero = events[0];

  return (
    <>
      <PageHeader
        title={`Добрый день, ${client.user.name.split(" ")[0]}`}
        description={`Вторник, 20 октября 2026 · по вашей компании ${events.length} значимых событий`}
        breadcrumbs={false}
      />
      <div className={styles.row} id="accounts">
        {client.accounts.map(([label, value, detail]) => (
          <StatCard
            key={label}
            label={label}
            value={value}
            detail={detail}
            compact
            trend={detail.startsWith("−") ? "negative" : "positive"}
          />
        ))}
        <Link className={`${styles.card} ${styles.entry}`} href="/feed">
          <div className={styles.ic}>
            <Icon name="star" size={22} />
          </div>
          <div style={{ zIndex: 1 }}>
            <b>Что важно для бизнеса сегодня</b>
            <small>Новости и аналитика Альфа-Банка под ваш профиль</small>
          </div>
          <span className={styles.n}>{events.length} новых</span>
        </Link>
      </div>
      <div className={styles.grid}>
        <section>
          <SectionHeader
            title="Инсайты для вашей компании"
            action={
              <Link className={styles.link} href="/feed">
                Вся лента →
              </Link>
            }
          />
          {hero ? (
            <>
              <InsightHero event={hero} />
              <div className={styles.feed}>
                {events.slice(1, 4).map((event) => (
                  <InsightCard key={event.id} event={event} />
                ))}
              </div>
            </>
          ) : (
            <EmptyFeed text="Нет событий выше выбранного порога значимости. Измените настройки ленты." />
          )}
        </section>
        <aside className={`${styles.stack} ${styles.sticky}`}>
          <CompanyContext client={client} />
          <AnalystCard
            eventId={hero?.id}
            questions={[
              ...(hero
                ? [
                    `Как «${hero.title.toLowerCase()}» повлияет на нас по кварталам?`,
                  ]
                : []),
              "Покажи только новости по контрагентам",
              "Что банк думает о ставке на 2027?",
            ]}
          />
          {hero && <TraceSummary event={hero} />}
        </aside>
      </div>
    </>
  );
};

export default Home;
