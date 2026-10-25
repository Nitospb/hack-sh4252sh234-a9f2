import Link from "next/link";
import Card from "@/src/components/UI/Card/Card";
import KeyValueList from "@/src/components/UI/KeyValueList/KeyValueList";
import ProductTags from "../ProductTags/ProductTags";
import type { Client } from "@/src/types";
import styles from "@/src/styles/Design.module.css";

const CompanyContext = ({ client }: { client: Client }) => (
  <Card
    title="Контекст компании"
    action={
      <Link className={styles.link} href="/profile">
        Подробнее
      </Link>
    }
  >
    <KeyValueList
      items={[
        ["ОКВЭД", `${client.okved} · ${client.okvedName}`],
        ["Выручка", client.revenue],
        ["Сотрудники", client.workers],
        ["Регион", client.region],
        ["Группа", `${client.group} · ${client.groupSize} компании`],
      ]}
    />
    <ProductTags products={client.products} />
  </Card>
);

export default CompanyContext;
