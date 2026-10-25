import Link from "next/link";
import PageHeader from "@/src/components/PageHeader/PageHeader";
import Card from "@/src/components/UI/Card/Card";
import DescriptionList from "@/src/components/UI/DescriptionList/DescriptionList";
import FlowLane from "@/src/components/Architecture/FlowLane/FlowLane";
import {
  ARCHITECTURE_LANES,
  SECURITY_POINTS,
  SCALING_POINTS,
} from "@/src/data/architecture";
import styles from "@/src/styles/Design.module.css";

const SCHEMA_EXAMPLE = {
  facts: [{ text: "…", source: "n1", status: "confirmed" }],
  bank_view: { text: "…", sources: ["d1"] },
  model_conclusions: [{ text: "…", origin: "llm" }],
  client_features: ["CL_PRODUCT_LOA_MARK=1"],
  relevance: 0.94,
  assumptions: ["…"],
};

const Architecture = () => (
  <>
    <PageHeader
      title="Архитектура решения"
      description="Как поток новостей превращается в персональный инсайт: агентная логика, безопасность и масштабирование."
      breadcrumbs={false}
    />
    <div className={styles.flow} style={{ marginBottom: 18 }}>
      {ARCHITECTURE_LANES.map((lane) => (
        <FlowLane key={lane.title} {...lane} />
      ))}
    </div>
    <div className={styles.g3}>
      <Card title="Безопасность AI-компонентов">
        <DescriptionList items={SECURITY_POINTS} />
      </Card>
      <Card title="Масштабирование">
        <DescriptionList items={SCALING_POINTS} />
      </Card>
      <Card title="Формат обмена между компонентами">
        <p
          className={`${styles.small} ${styles.muted}`}
          style={{ margin: "0 0 8px" }}
        >
          Каждый вывод хранит происхождение:
        </p>
        <pre>{JSON.stringify(SCHEMA_EXAMPLE, null, 2)}</pre>
        <Link className={`${styles.link} ${styles.blockLink}`} href="/trace">
          Пример в журнале агента →
        </Link>
      </Card>
    </div>
  </>
);

export default Architecture;
