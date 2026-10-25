import Link from "next/link";
import type { ReactNode } from "react";
import Icon, { type IconName } from "@/src/components/UI/Icon/Icon";
import styles from "@/src/styles/Design.module.css";

interface NavigationItemProps {
  href: string;
  label: string;
  icon?: IconName;
  active?: boolean;
  nested?: boolean;
  accent?: boolean;
  badge?: ReactNode;
}

const NavigationItem = ({
  href,
  label,
  icon,
  active,
  nested,
  accent,
  badge,
}: NavigationItemProps) => (
  <Link
    href={href}
    className={`${styles.nav} ${active ? styles.on : ""} ${nested ? styles.nested : ""} ${accent ? styles.ai : ""}`}
    aria-current={active ? "page" : undefined}
  >
    {icon && <Icon name={icon} color={accent ? "var(--red)" : undefined} />}
    {label}
    {badge !== undefined && <span className={styles.tag}>{badge}</span>}
  </Link>
);

export default NavigationItem;
