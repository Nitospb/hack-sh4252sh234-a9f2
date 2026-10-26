import PageTransition from "@/src/components/UI/PageTransition/PageTransition";
import type { Metadata } from "next";
import Swagger from "./Swagger";
import styles from "./Docs.module.css";
import "swagger-ui-dist/swagger-ui.css";

export const metadata: Metadata = { title: "API · Swagger" };

export default function ApiDocsPage() {
  return (
    <PageTransition><section aria-label="Документация API" className={styles.page}>
      <h1>API · Swagger</h1>
      <p>Контракт локального API. Запросы анализа и диалога могут расходовать лимит LLM.</p>
      <Swagger />
    </section></PageTransition>
  );
}
