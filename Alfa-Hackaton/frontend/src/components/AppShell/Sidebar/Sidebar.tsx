"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useClient } from "@/src/providers/ClientProvider";
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
  const { events } = useClient();
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
        <NavigationItem href="/#accounts" label="Счета" icon="account" />
        <NavigationItem href="/#accounts" label="Платежи" icon="payment" />
        <NavigationItem
          href="/#accounts"
          label="Кредиты и гарантии"
          icon="chart"
        />
        <NavigationItem
          href="/#accounts"
          label="Зарплатный проект"
          icon="user"
        />
        <NavigationItem
          href="/feed"
          label="Новостная аналитика"
          icon="news"
          accent
          active={inAnalytics}
          badge={pathname === "/feed" ? undefined : events.length}
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
          label="Выбор клиента · демо"
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
        {pathname === "/feed" ? <>Рабочая лента<br />Реальные обезличенные данные</> : <>
        Персональный менеджер
        <br />
        <b style={{ color: "var(--ink)" }}>Ирина С.</b> ·{" "}
        <a href="tel:88001007733">8 800 100-77-33</a>
        </>}
      </div>
    </aside>
  );
};

export default Sidebar;
