"use client";
import { useState } from "react";
import Link from "next/link";
import { ROLES, type Context, type Profile } from "./recommendation-api";
import s from "./CompanyContext.module.css";
export default function CompanyContext({context,profile,onRole}:{context:Context;profile:Profile;onRole:(role:string)=>Promise<void>}) {
 const [saving,setSaving]=useState(false);const [error,setError]=useState("");
 async function changeRole(role:string){setSaving(true);setError("");try{await onRole(role);}catch(e){setError(String(e));}finally{setSaving(false);}}
 const business=context.business_context;
 return <section className={s.card} aria-label="Ваша роль и деятельность компании">
  <h2>Ваша роль в компании</h2><label className={s.roleLabel} htmlFor="sidebar-role">Подборка с учётом вашей работы</label><select id="sidebar-role" className={s.select} value={profile.role} disabled={saving} onChange={e=>changeRole(e.target.value)}>{ROLES.map(r=><option key={r.id} value={r.id}>{r.label}</option>)}</select>
  <p className={s.roleDetail} role="status">{saving?"Сохраняем роль…":ROLES.find(r=>r.id===profile.role)?.detail}</p>{error&&<p role="alert" className={s.error}>{error}</p>}
  <div className={s.section}><h3>Деятельность компании</h3><strong className={s.activity}>{business?.activity_group || context.activity}</strong><p className={s.description}>{context.activity}</p><span className={s.okved}>ОКВЭД {context.okved}</span></div>
  <div className={s.section}><h3>Контрагенты и связи</h3>{business?.partner_sectors.length ? <div className={s.partners}>{business.partner_sectors.map(partner=><div className={s.partner} key={partner.label}><span className={s.dot}/><div><strong>{partner.label}</strong><small>{partner.kinds.includes("outgoing_payment")&&partner.kinds.includes("incoming_payment")?"Платежи в обе стороны":partner.kinds.includes("outgoing_payment")?"Получатели платежей":partner.kinds.includes("incoming_payment")?"Отправители платежей":"Общая группа в исходных данных"} · компаний: {partner.company_count}</small></div></div>)}</div>:<p className={s.description}>В исходных данных нет сведений о контрагентах.</p>}<p className={s.note}>По данным связей компании. Платежи не подтверждают зависимость бизнеса.</p></div>
  <Link href="/profile" className={s.link}>Подробнее о компании ↗</Link>
 </section>;
}
