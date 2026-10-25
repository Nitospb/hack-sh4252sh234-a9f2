"use client";

import { useClient } from "@/src/providers/ClientProvider";
import PageHeader from "@/src/components/PageHeader/PageHeader";
import StatCard from "@/src/components/UI/StatCard/StatCard";
import Card from "@/src/components/UI/Card/Card";
import Badge from "@/src/components/UI/Badge/Badge";
import DataTable from "@/src/components/UI/DataTable/DataTable";
import TextList from "@/src/components/UI/TextList/TextList";
import CompanyFeatures from "@/src/components/Company/CompanyFeatures/CompanyFeatures";
import CompanyGraph from "@/src/components/Company/CompanyGraph/CompanyGraph";
import CompanyInterests from "@/src/components/Company/CompanyInterests/CompanyInterests";
import ContextEditor from "@/src/components/Company/ContextEditor/ContextEditor";
import styles from "@/src/styles/Design.module.css";

const Profile = () => {
  const { client } = useClient();
  return (
    <>
      <PageHeader
        title="Контекст компании"
        description="На этих признаках сервис отбирает события и строит интерпретации. Если что-то неверно, уточните, и лента пересчитается."
      />
      <div className={`${styles.g4} ${styles.statGrid}`}>
        <StatCard
          label="Выручка"
          value={client.revenue}
          detail="REVENUE_COMPANY"
        />
        <StatCard
          label="ОКВЭД"
          value={client.okved}
          detail={client.okvedName}
        />
        <StatCard
          label="Сотрудники"
          value={client.workers}
          detail="по данным ФНС"
        />
        <StatCard
          label="Группа компаний"
          value={`${client.groupSize} юрлица`}
          detail={client.group}
        />
      </div>
      <div className={styles.grid}>
        <section className={styles.stack}>
          <CompanyFeatures client={client} />
          <Card
            id="graph"
            heading={
              <>
                Связи и контрагенты{" "}
                <Badge>
                  df_Uid_payment_hack.csv · df_Fid_Uid_link_hack.csv
                </Badge>
              </>
            }
          >
            <CompanyGraph client={client} />
            <DataTable
              headers={["Контрагент", "Отрасль", "Платежи, 6 мес.", "Роль"]}
              rows={client.counter}
              caption="● зелёный — платят вам, ● красный — вы платите, пунктир — общие физлица (SYNTHETIC_F) с компаниями группы"
            />
          </Card>
        </section>
        <aside className={`${styles.stack} ${styles.sticky}`}>
          <Card
            heading={
              <>
                Выведенный бизнес-контекст <Badge tone="ai">AI</Badge>
              </>
            }
          >
            <TextList items={client.facts} />
            <p className={`${styles.small} ${styles.muted}`}>
              Сформировано по признакам и платежам. Последнее обновление:
              сегодня, 06:00.
            </p>
          </Card>
          <CompanyInterests key={`${client.id}-interests`} client={client} />
          <ContextEditor key={`${client.id}-context`} clientId={client.id} />
        </aside>
      </div>
    </>
  );
};

export default Profile;
