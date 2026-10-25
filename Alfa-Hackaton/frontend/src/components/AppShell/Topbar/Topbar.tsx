"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { useClient } from "@/src/providers/ClientProvider";
import Avatar from "@/src/components/UI/Avatar/Avatar";
import Icon from "@/src/components/UI/Icon/Icon";
import styles from "@/src/styles/Design.module.css";

const Topbar = ({
  onMenu,
  menuOpen,
}: {
  onMenu: () => void;
  menuOpen: boolean;
}) => {
  const { client } = useClient();
  const live = usePathname() === "/feed";
  const [query, setQuery] = useState("");
  const router = useRouter();
  const handleSearch = (event: FormEvent) => {
    event.preventDefault();
    if (query.trim())
      router.push(`/feed?q=${encodeURIComponent(query.trim())}`);
  };

  if (live) return (
    <header className={styles.top} style={{ minHeight: 42, marginBottom: 12 }}>
      <button type="button" className={styles.menuButton} onClick={onMenu} aria-label="Открыть навигацию" aria-expanded={menuOpen} aria-controls="mobile-navigation"><Icon name="menu" /></button>
      <span style={{ fontSize: 12, color: "#9aa2af" }}>Бизнес <span style={{ margin: "0 10px", color: "#c7cdd6" }}>/</span> Аналитика</span>
      <button type="button" onClick={() => window.dispatchEvent(new Event("alfa:preferences"))} style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 8, padding: "7px 0", background: "transparent", border: 0, color: "#7c889a", fontSize: 12, cursor: "pointer" }}><Icon name="user" />Личные интересы</button>
    </header>
  );

  return (
    <header className={styles.top}>
      <button
        type="button"
        className={styles.menuButton}
        onClick={onMenu}
        aria-label="Открыть навигацию"
        aria-expanded={menuOpen}
        aria-controls="mobile-navigation"
        aria-haspopup="dialog"
      >
        <Icon name="menu" />
      </button>
      <Link className={styles.co} href={live ? "/feed" : "/clients"} title={live ? "Реальные новости" : "Сменить клиента"}>
        <Avatar text={live ? "Н" : client.short} />
        <div>
          <b>{live ? "Новостная аналитика" : client.name}</b>
          <small>
            {live ? "Выбор компании — в настройках ленты" : `${client.id} · группа ${client.group} · ${client.groupSize} юрлица`}
          </small>
        </div>
        <span className={styles.muted}>▾</span>
      </Link>
      <form className={styles.search} onSubmit={handleSearch}>
        <Icon name="search" />
        <input
          aria-label="Поиск по новостям"
          placeholder={live ? "Поиск по новостям" : "Поиск по платежам, контрагентам и новостям"}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
      </form>
      <span className={styles.demo}>{live ? "ЛОКАЛЬНЫЙ ПРОТОТИП" : "ДЕМО"}</span>
      <div className={styles.user}>
        <div>
          <b>{live ? "Локальный пользователь" : client.user.name}</b>
          <small>{live ? "Роль не указана" : client.user.role}</small>
        </div>
        <Avatar text={live ? "ЛП" : client.user.ini} background="var(--red)" />
      </div>
    </header>
  );
};

export default Topbar;
