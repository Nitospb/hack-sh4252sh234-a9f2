"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import NavigationItem from "../NavigationItem/NavigationItem";
import styles from "@/src/styles/Design.module.css";

interface SidebarProps {
  mobile?: boolean;
  onNavigate?: () => void;
}

const Sidebar = ({ mobile = false, onNavigate }: SidebarProps) => {
  const pathname = usePathname();

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
        <Image src="/alfa-bank-logo.svg" width={48} height={48} alt="" unoptimized />
        <span>Альфа-Бизнес</span>
      </Link>
      <nav aria-label="Основная навигация">
        <NavigationItem href="/" label="Главная" icon="home" active={pathname === "/"} />
        <NavigationItem href="/feed" label="Новостная аналитика" icon="news" active={pathname === "/feed" || pathname === "/event"} />
        <NavigationItem href="/chat" label="Спросить аналитика" icon="chat" active={pathname === "/chat"} />
        <NavigationItem href="/profile" label="Контекст компании" icon="user" active={pathname === "/profile"} />
        <NavigationItem href="/sources" label="Источники" icon="document" active={pathname === "/sources"} />
        <NavigationItem href="/trace" label="Журнал агента" icon="chart" active={pathname === "/trace"} />
        <div className={styles.grp}>Для команды банка</div>
        <NavigationItem href="/clients" label="Выбор компании" icon="building" active={pathname === "/clients"} />
        <NavigationItem href="/quality" label="Качество и метрики" icon="account" active={pathname === "/quality"} />
        <NavigationItem href="/architecture" label="Архитектура" icon="menu" active={pathname === "/architecture"} />
        <NavigationItem href="/docs" label="API · Swagger" icon="info" active={pathname === "/docs"} />
        <NavigationItem href="/kit" label="Библиотека компонентов" icon="star" active={pathname === "/kit"} />
      </nav>
      <div className={styles.sp} />
      <NavigationItem href="/settings" label="Настройки" icon="settings" active={pathname === "/settings"} />
      <div className={styles.help}>
        Локальный прототип<br />Обезличенные данные
      </div>
    </aside>
  );
};

export default Sidebar;
