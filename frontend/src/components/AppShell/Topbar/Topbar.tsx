"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";
import { useLive } from "@/src/providers/LiveProvider";
import Icon from "@/src/components/UI/Icon/Icon";
import styles from "@/src/styles/Design.module.css";
import s from "./Topbar.module.css";

export default function Topbar({onMenu,menuOpen}:{onMenu:()=>void;menuOpen:boolean}) {
 const {company,error}=useLive();
 const searchInput=useRef<HTMLInputElement>(null);
 useEffect(() => { if (searchInput.current) searchInput.current.value=new URLSearchParams(window.location.search).get("q") || ""; }, []);
 return <header className={s.header}>
  <button type="button" className={styles.menuButton} onClick={onMenu} aria-label="Открыть навигацию" aria-expanded={menuOpen} aria-controls="mobile-navigation"><Icon name="menu"/></button>
  <form action="/feed" className={s.search} role="search">
   <Icon name="search" size={20}/><input ref={searchInput} type="search" name="q" aria-label="Поиск по всем новостям" placeholder="Найти новость, тему или событие" autoComplete="off"/>
   <button type="submit">Найти</button>
  </form>
  <Link href="/clients" className={s.company}><Icon name="account" size={19}/><span>{company ? company.company_id : error ? "Профиль недоступен" : "Загрузка профиля…"}<small>{company ? company.region : error ? "Попробуйте обновить" : ""}</small></span></Link>
  <Link href="/settings" className={s.settings} aria-label="Роль и интересы"><Icon name="settings" size={20}/></Link>
 </header>;
}
