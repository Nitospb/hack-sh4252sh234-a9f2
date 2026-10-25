"use client";

import { DOCS } from "@/src/data/demo";
import { useClient } from "@/src/providers/ClientProvider";
import PageHeader from "@/src/components/PageHeader/PageHeader";
import Card from "@/src/components/UI/Card/Card";
import Badge from "@/src/components/UI/Badge/Badge";
import DataTable from "@/src/components/UI/DataTable/DataTable";
import TextList from "@/src/components/UI/TextList/TextList";
import DocumentRow from "@/src/components/Sources/DocumentRow/DocumentRow";
import styles from "@/src/styles/Design.module.css";

const Sources = () => {
  const { events } = useClient();
  const documents = Object.entries(DOCS);
  const renderDocument = ([id, document]: (typeof documents)[number]) => (
    <DocumentRow
      key={id}
      id={id}
      document={document}
      bank={id.startsWith("d")}
      events={events.filter((event) => event.docs.includes(id))}
    />
  );

  return (
    <>
      <PageHeader
        title="Источники"
        description="Каждый вывод в ленте ссылается сюда. Материалы Альфа-Банка формируют экспертную позицию, а внешние новости дают факты."
      />
      <div className={styles.grid}>
        <section className={styles.stack}>
          <Card
            heading={
              <>
                Аналитика Центра макроэкономических исследований Альфа-Банка{" "}
                <Badge tone="bank">Позиция банка</Badge>
              </>
            }
          >
            {documents.filter(([id]) => id.startsWith("d")).map(renderDocument)}
          </Card>
          <Card
            heading={
              <>
                Внешние новости <Badge tone="fact">Факты</Badge>
              </>
            }
          >
            {documents.filter(([id]) => id.startsWith("n")).map(renderDocument)}
          </Card>
        </section>
        <aside className={`${styles.stack} ${styles.sticky}`}>
          <Card title="Подключённые ленты">
            <DataTable
              headers={["Источник", "За 7 дн."]}
              rows={[
                ["Интерфакс", "412"],
                ["ТАСС", "355"],
                ["РБК", "287"],
                ["Reuters", "148"],
                ["Сайты ведомств (ЦБ, Минтранс, Минфин)", "73"],
                ["Альфа-Банк · аналитика", "9"],
              ]}
            />
          </Card>
          <Card title="Как используются">
            <TextList
              ordered
              items={[
                "Парсер собирает и дедуплицирует новости",
                "Классификатор размечает тему, отрасль, участников",
                "Материалы банка индексируются для RAG",
                "Каждый вывод хранит ссылки на фрагменты",
              ]}
            />
          </Card>
        </aside>
      </div>
    </>
  );
};

export default Sources;
