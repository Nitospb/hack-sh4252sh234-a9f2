import Link from "next/link";
import styles from "@/src/styles/Design.module.css";

interface PageHeaderProps {
  title: string;
  description?: string;
  breadcrumbs?: boolean;
}

const PageHeader = ({
  title,
  description,
  breadcrumbs = true,
}: PageHeaderProps) => (
  <>
    {breadcrumbs && (
      <nav className={styles.crumbs} aria-label="Хлебные крошки">
        <Link href="/">Главная</Link> /{" "}
        <Link href="/feed">Новостная аналитика</Link> / <span>{title}</span>
      </nav>
    )}
    <h1>{title}</h1>
    {description && <p className={styles.sub}>{description}</p>}
  </>
);

export default PageHeader;
