import type { ReactNode } from "react";
import styles from "@/src/styles/Design.module.css";

const ArticleSection = ({
  number,
  title,
  id,
  children,
}: {
  number: string;
  title: string;
  id?: string;
  children: ReactNode;
}) => (
  <section className={styles.qa} id={id}>
    <h4>
      <i>{number}</i>
      {title}
    </h4>
    {children}
  </section>
);

export default ArticleSection;
