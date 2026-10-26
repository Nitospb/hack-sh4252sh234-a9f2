"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import NavigationItem from "../NavigationItem/NavigationItem";
import styles from "@/src/styles/Design.module.css";

const ANALYTICS_ROUTES = [
  "/feed",
  "/event",
  "/chat",
  "/profile",
  "/sources",
  "/trace",
  "/settings",
];
const SUB_ITEMS = [
  ["/feed", "Лента инсайтов"],
  ["/chat", "Спросить аналитика"],
  ["/profile", "Контекст компании"],
  ["/sources", "Источники"],
  ["/trace", "Журнал агента"],
  ["/settings", "Настройки ленты"],
];

interface SidebarProps {
  mobile?: boolean;
  onNavigate?: () => void;
}

const Sidebar = ({ mobile = false, onNavigate }: SidebarProps) => {
  const pathname = usePathname();
  const inAnalytics = ANALYTICS_ROUTES.includes(pathname);

  return (
    <aside
      className={`${styles.side} ${mobile ? styles.mobileSide : ""}`}
      onClick={(event) => {
        if (
          event.target instanceof Element &&
          event.target.closest("a[href]")
        ) {
          onNavigate?.();
        }
      }}
    >
      <Link className={styles.logo} href="/">
        <i>А</i>Альфа-Бизнес
      </Link>
      <nav aria-label="Основная навигация">
        <NavigationItem
          href="/"
          label="Главная"
          icon="home"
          active={pathname === "/"}
        />
        <NavigationItem
          href="/feed"
          label="Новостная аналитика"
          icon="news"
          accent
          active={inAnalytics}
        />
        {inAnalytics &&
          SUB_ITEMS.map(([href, label]) => (
            <NavigationItem
              key={href}
              href={href}
              label={label}
              active={pathname === href}
              nested
            />
          ))}
        <NavigationItem href="/sources" label="Документы" icon="document" />
        <div className={styles.grp}>Для команды банка</div>
        <NavigationItem
          href="/clients"
          label="Выбор компании"
          icon="user"
          active={pathname === "/clients"}
        />
        <NavigationItem
          href="/quality"
          label="Качество и метрики"
          icon="chart"
          active={pathname === "/quality"}
        />
        <NavigationItem
          href="/architecture"
          label="Архитектура"
          icon="settings"
          active={pathname === "/architecture"}
        />
      </nav>
      <div className={styles.sp} />
      <div className={styles.help}>
        Локальный прототип<br />Обезличенные данные
      </div>
    </aside>
  );
};

export default Sidebar;
