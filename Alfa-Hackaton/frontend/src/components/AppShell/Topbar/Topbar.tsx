"use client";
import Link from "next/link";
import { useLive } from "@/src/providers/LiveProvider";
import Icon from "@/src/components/UI/Icon/Icon";
import styles from "@/src/styles/Design.module.css";
export default function Topbar({onMenu,menuOpen}:{onMenu:()=>void;menuOpen:boolean}){
 const {company}=useLive();
 return <header className={styles.top} style={{minHeight:48,marginBottom:12}}><button type="button" className={styles.menuButton} onClick={onMenu} aria-label="Открыть навигацию" aria-expanded={menuOpen} aria-controls="mobile-navigation"><Icon name="menu"/></button><Link href="/" style={{fontSize:13,color:"#687589"}}>Бизнес / Аналитика</Link><Link href="/clients" style={{marginLeft:"auto",fontSize:13,color:"#687589"}}>{company?`${company.company_id} · ${company.region}`:"Загружаем профиль"}</Link><Link href="/settings" style={{fontSize:12,color:"#687589"}}>Роль и интересы</Link></header>;
}
