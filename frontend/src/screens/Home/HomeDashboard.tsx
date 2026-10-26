"use client";

import Image from "next/image";
import Link from "next/link";
import { useState } from "react";
import Icon, { type IconName } from "@/src/components/UI/Icon/Icon";
import { useLive } from "@/src/providers/LiveProvider";
import { companyLabel } from "@/src/screens/Feed/recommendation-api";
import { OnboardingTrigger } from "@/src/screens/Workspace/Onboarding";
import Skeleton from "@/src/components/UI/Skeleton/Skeleton";
import LoadingSwap from "@/src/components/UI/Skeleton/LoadingSwap";
import s from "./HomeDashboard.module.css";

const visuals = {
  overview: "https://alfabank.servicecdn.ru/site-upload/1c/74/21424/d-mb-250925.png",
  company: "https://alfabank.servicecdn.ru/site-upload/8c/66/7344/D01_MB_KV_564x450.png",
  feed: "https://alfabank.servicecdn.ru/site-upload/16/f0/21424/cardpure-3.png",
  analysis: "https://alfabank.servicecdn.ru/site-upload/0e/d4/6088/MB_KV_328x192_D6E8FC.png",
};

const features: {
  label: string;
  title: string;
  description: string;
  points: string[];
  image: string;
  source: string;
  href: string;
  action: string;
  icon: IconName;
}[] = [
  {
    label: "Компания",
    title: "Сначала — ваш бизнес",
    description: "Выберите обезличенный профиль компании. Отрасль, регион и ваши уточнения задают контекст для ленты и разбора.",
    points: ["Исходные признаки показаны отдельно", "Роль меняет ракурс аналитики"],
    image: visuals.company,
    source: "https://alfabank.ru/corporate/salaryproject/",
    href: "/clients",
    action: "Выбрать компанию",
    icon: "building",
  },
  {
    label: "Новости",
    title: "Затем — события по делу",
    description: "Персональная лента собирает материалы по темам компании. Фильтры, поиск и реакции помогают находить важное.",
    points: ["Открывайте полный текст и первоисточник", "Сохраняйте полезные материалы"],
    image: visuals.feed,
    source: "https://alfabank.ru/sme/digital-bank/",
    href: "/feed",
    action: "Перейти в ленту",
    icon: "news",
  },
  {
    label: "Разбор",
    title: "Потом — влияние на компанию",
    description: "Выберите новость и запросите разбор возможных рисков, возможностей и действий. Вопрос аналитику продолжает тот же сценарий.",
    points: ["Выводы опираются на контекст компании", "Неизвестные условия названы явно"],
    image: visuals.analysis,
    source: "https://alfabank.ru/sme/profits/creditline/",
    href: "/feed",
    action: "Выбрать новость",
    icon: "chart",
  },
  {
    label: "Проверка",
    title: "И наконец — основания вывода",
    description: "Смотрите цитаты, новости и материалы банка. Журнал показывает шаги реального запуска анализа.",
    points: ["Ссылки ведут к оригиналам", "Неподтверждённые условия не выдаются за факты"],
    image: visuals.overview,
    source: "https://alfabank.ru/sme/digital-bank/",
    href: "/sources",
    action: "Проверить источники",
    icon: "document",
  },
];

const quickActions: { title: string; text: string; href: string; icon: IconName; theme: string; action: string }[] = [
  { title: "Найти важное", text: "Откройте подборку новостей для выбранной компании и настройте темы.", href: "/feed", icon: "news", theme: s.actionRose, action: "Открыть ленту" },
  { title: "Уточнить контекст", text: "Проверьте исходные признаки бизнеса и добавьте важные для анализа условия.", href: "/profile", icon: "building", theme: s.actionViolet, action: "Открыть профиль" },
  { title: "Проверить доказательства", text: "Найдите материалы банка и откройте первоисточник каждого тезиса.", href: "/sources", icon: "document", theme: s.actionBlue, action: "Открыть источники" },
];

export default function HomeDashboard() {
  const { company, health, error } = useLive();
  const [active, setActive] = useState(0);
  const feature = features[active];
  const newsCount = health?.counts.news;
  const primaryHref = company ? "/feed" : "/clients";

  return <div className={s.page}>
    <section className={s.hero} aria-labelledby="home-title">
      <div className={s.heroCopy}>
        <h1 id="home-title">Новости становятся <em>понятнее,</em>{" "}когда речь о вашем бизнесе</h1>
        <p>Сервис связывает события с профилем компании, помогает оценить возможное влияние и показывает источники каждого вывода.</p>
        <div className={s.heroActions}>
          <Link className={s.heroPrimary} href={primaryHref}>{company ? "Открыть ленту для компании" : "Выбрать компанию"}<Icon name="arrow" size={20} /></Link>
          <OnboardingTrigger className={s.heroSecondary} label="Посмотреть экскурсию" />
        </div>
      </div>
      <div className={s.heroVisual} aria-hidden="true">
        <div className={s.heroOrbit} />
        <div className={s.heroGlow} />
        <Image src={visuals.overview} alt="" fill sizes="(max-width: 900px) 80vw, 38vw" priority unoptimized className={s.heroImage} />
      </div>
    </section>

    <section className={s.contextBar} aria-label="Текущий контекст">
      <LoadingSwap className={s.contextCompany} loading={!health&&!error} placeholder={<Skeleton count={1} label="Загрузка компании"/>}>
        <span className={s.contextIcon}><Icon name="building" size={24} /></span>
        <div><span className={s.microLabel}>КОМПАНИЯ В ФОКУСЕ</span><strong>{company ? companyLabel(company) : error ? "Профиль недоступен" : "Загружаем компанию"}</strong><small>{company ? `${company.company_id} · ОКВЭД ${company.okved} · ${company.region}` : "Выберите компанию, чтобы увидеть персональную ленту"}</small></div>
      </LoadingSwap>
      <LoadingSwap className={s.contextMetric} loading={!health&&!error} placeholder={<Skeleton count={1} label="Загрузка каталога"/>}><strong>{newsCount === undefined ? "—" : newsCount.toLocaleString("ru-RU")}</strong><span>новостей в каталоге</span></LoadingSwap>
      <Link className={s.contextLink} href="/clients">{company ? "Сменить компанию" : "Выбрать компанию"}<Icon name="arrow" size={18} /></Link>
    </section>

    <section className={s.journey} aria-label="Как работает сервис">
      <div className={s.sectionIntro}><span className={s.sectionEyebrow}>КАК ЭТО РАБОТАЕТ</span><h2>От новости к ясному действию</h2><p>Четыре шага, в которых можно проверить контекст, материалы и ход анализа.</p></div>
      <div className={s.journeyRail}>
        {features.map((item, index) => <button type="button" key={item.label} className={`${s.railItem} ${active === index ? s.railActive : ""}`} onClick={() => setActive(index)} aria-current={active === index ? "step" : undefined}>
          <span className={s.railNumber}>0{index + 1}</span><Icon name={item.icon} size={23} /><span>{item.label}</span>
        </button>)}
      </div>
    </section>

    <section className={s.showcase} aria-labelledby="showcase-title">
      <div className={s.showcaseHeader}><div><span className={s.sectionEyebrow}>ВОЗМОЖНОСТИ СЕРВИСА</span><h2 id="showcase-title">Посмотрите, что можно сделать</h2></div><div className={s.slideControls}><span>0{active + 1} <i>/</i> 0{features.length}</span><button type="button" aria-label="Предыдущая возможность" onClick={() => setActive((active + features.length - 1) % features.length)}>‹</button><button type="button" aria-label="Следующая возможность" onClick={() => setActive((active + 1) % features.length)}>›</button></div></div>
      <div className={s.featureCard} key={active} role="region" aria-live="polite" aria-label={`${feature.label}: ${feature.title}`}>
        <div className={s.featureCopy}><span className={s.featureNumber}>0{active + 1} / 0{features.length} · {feature.label.toUpperCase()}</span><h3>{feature.title}</h3><p>{feature.description}</p><ul>{feature.points.map(point => <li key={point}><span><Icon name="check" size={17} /></span>{point}</li>)}</ul><Link href={feature.href} className={s.featureLink}>{feature.action}<Icon name="arrow" size={18} /></Link></div>
        <div className={s.featureVisual}><div className={s.featureCircle} /><Image src={feature.image} alt="" fill sizes="(max-width: 900px) 85vw, 35vw" unoptimized className={s.featureImage} /><a href={feature.source} target="_blank" rel="noreferrer" className={s.imageCredit}>Иллюстрация: Альфа-Банк ↗</a></div>
      </div>
      <div className={s.slideDots} aria-label="Выбрать возможность">{features.map((item, index) => <button type="button" key={item.label} className={active === index ? s.dotActive : ""} aria-label={`Показать шаг ${index + 1}: ${item.label}`} aria-pressed={active === index} onClick={() => setActive(index)} />)}</div>
    </section>

    <section className={s.actions} aria-labelledby="actions-title"><div className={s.sectionIntro}><span className={s.sectionEyebrow}>НАЧНИТЕ С ЗАДАЧИ</span><h2 id="actions-title">Что хотите сделать сейчас?</h2><p>Каждый раздел ведёт к конкретному действию, а не к пустому экрану.</p></div><div className={s.actionGrid}>{quickActions.map(item => <Link className={`${s.actionCard} ${item.theme}`} href={item.href} key={item.title}><span className={s.actionIcon}><Icon name={item.icon} size={26} /></span><h3>{item.title}</h3><p>{item.text}</p><span className={s.actionLink}>{item.action}<Icon name="arrow" size={17} /></span></Link>)}</div></section>

    <section className={s.bottomCallout}><div><span className={s.sectionEyebrow}>НУЖНА ПОМОЩЬ СО СТАРТОМ?</span><h2>Покажем всё прямо на экране</h2><p>Экскурсия проведёт по страницам и подсветит кнопки, поля и источники.</p></div><OnboardingTrigger className={s.bottomTrigger} label="Запустить экскурсию" /></section>
    {health && !health.llm_available && <p className={s.availability} role="status">Персональный разбор сейчас недоступен: {health.analysis_availability?.message || "LLM-шлюз отключён"}. Лента, профиль и источники продолжают работать.</p>}
  </div>;
}
