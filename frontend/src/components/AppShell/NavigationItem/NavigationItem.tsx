import Link from "next/link";
import type { ReactNode } from "react";
import Icon, { type IconName } from "@/src/components/UI/Icon/Icon";
import styles from "@/src/styles/Design.module.css";

interface NavigationItemProps {
  href: string;
  label: string;
  icon?: IconName;
  active?: boolean;
  badge?: ReactNode;
}

const NavigationItem = ({
  href,
  label,
  icon,
  active,
  badge,
}: NavigationItemProps) => (
  <Link
    href={href}
    className={`${styles.nav} ${active ? styles.on : ""}`}
    aria-current={active ? "page" : undefined}
    aria-label={label}
    title={label}
  >
    {icon && <Icon name={icon} size={23} />}
    <span className={styles.navLabel}>{label}</span>
    {badge !== undefined && <span className={styles.tag}>{badge}</span>}
  </Link>
);

export default NavigationItem;
