"use client";

import Image from "next/image";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import { createPortal } from "react-dom";
import Drawer from "@/src/components/UI/Drawer/Drawer";
import Button from "@/src/components/UI/Button/Button";
import Icon from "@/src/components/UI/Icon/Icon";
import s from "./Onboarding.module.css";

const STATUS_KEY = "alfa-onboarding-seen-v1";
const STEP_KEY = "alfa-onboarding-step-v1";
const TOUR_KEY = "alfa-onboarding-tour-v1";
const steps = [
  { title: "Выберите компанию", text: "Найдите обезличенный профиль по ID, ОКВЭД или виду деятельности. Выбор определяет контекст всей аналитики.", href: "/clients", link: "Выбор компании", image: "https://alfabank.servicecdn.ru/site-upload/1c/74/21424/d-mb-250925.png", source: "https://alfabank.ru/sme/digital-bank/", tint: "#f1f0fb" },
  { title: "Уточните роль и контекст", text: "Проверьте исходные признаки компании, добавьте важные условия и укажите свою роль. Сведения с ваших слов остаются отдельными от подтверждённых фактов.", href: "/profile", link: "Контекст компании", image: "https://alfabank.servicecdn.ru/site-upload/8c/66/7344/D01_MB_KV_564x450.png", source: "https://alfabank.ru/corporate/salaryproject/", tint: "#eef7f7" },
  { title: "Откройте персональную ленту", text: "Лента показывает материалы с учётом компании, роли и реакций. Откройте новость, чтобы увидеть текст и первоисточник.", href: "/feed", link: "Новостная аналитика", image: "https://alfabank.servicecdn.ru/site-upload/16/f0/21424/cardpure-3.png", source: "https://alfabank.ru/sme/digital-bank/", tint: "#f3f2fb" },
  { title: "Получите разбор", text: "По выбранной новости запросите анализ рисков и возможностей, проверьте цитаты и задайте уточняющий вопрос. Генерация доступна, когда включён LLM-шлюз и есть бюджет.", href: "/feed", link: "Начать с ленты", image: "https://alfabank.servicecdn.ru/site-upload/0e/d4/6088/MB_KV_328x192_D6E8FC.png", source: "https://alfabank.ru/sme/profits/creditline/", tint: "#eef5fc" },
];
const tourSteps = [
  { route: "/clients", target: "company-search", title: "Найдите компанию", text: "Введите ID, ОКВЭД или деятельность. В результатах нажмите «Выбрать»: лента и разборы откроются в контексте этой компании." },
  { route: "/profile", target: "company-facts", title: "Проверьте контекст", text: "Здесь исходные признаки компании. Ниже можно добавить условия со своих слов; они останутся отдельно от подтверждённых фактов." },
  { route: "/settings", target: "role-settings", title: "Укажите свою роль", text: "Выберите роль и сохраните её. Она меняет ракурс анализа и рекомендации; изменить её можно в любой момент." },
  { route: "/feed", target: "feed-tabs", title: "Выберите разрез ленты", text: "«Для вас» показывает персональную подборку. «Сохранённое» и «Все новости» помогают посмотреть материалы с другой стороны." },
  { route: "/feed", target: "feed-card", title: "Откройте новость", text: "Нажмите «Читать» на карточке: там полный текст и первоисточник. Кнопки «Полезно», «Сохранить» и «Не интересно» помогают настроить ленту." },
  { route: "/event", target: "analysis-panel", title: "Запросите разбор", text: "Нажмите «Подготовить персональный разбор»: агент оценит риски и возможности для компании. Если генерация недоступна, полный текст новости остаётся доступен ниже." },
  { route: "/sources", target: "sources-panel", title: "Проверьте источники", text: "Здесь ищутся материалы банка и открываются оригиналы PDF. В разборе можно сверить цитату с документом и страницей." },
  { route: "/trace", target: "trace-panel", title: "Посмотрите ход анализа", text: "Журнал показывает реальные запуски, шаги агента и использованные инструменты. Так можно проверить, откуда взялся вывод." },
];
type Spotlight = { step: number; path: string; top: number; left: number; width: number; height: number };

export default function Onboarding() {
  const pathname = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState(0);
  const [leaving, setLeaving] = useState(false);
  const [tourActive, setTourActive] = useState(false);
  const [tourStep, setTourStep] = useState(0);
  const [spotlight, setSpotlight] = useState<Spotlight | null>(null);
  const [viewport, setViewport] = useState({ width: 0, height: 0 });
  const transitionTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => {
    if (transitionTimer.current) clearTimeout(transitionTimer.current);
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => {
      try {
        const status = window.localStorage.getItem(STATUS_KEY);
        if (status === "1" || status === "closed" || status === "completed") return;
        const savedTour = Number(window.localStorage.getItem(TOUR_KEY));
        if (window.localStorage.getItem(TOUR_KEY) !== null && Number.isInteger(savedTour) && savedTour >= 0 && savedTour < tourSteps.length) {
          setTourStep(savedTour);
          setTourActive(true);
          if (window.location.pathname !== tourSteps[savedTour].route) router.push(tourSteps[savedTour].route);
          return;
        }
        const savedStep = Number(window.localStorage.getItem(STEP_KEY));
        if (Number.isInteger(savedStep) && savedStep >= 0 && savedStep < steps.length) setStep(savedStep);
      } catch { /* Storage may be unavailable; the Sheet still opens. */ }
      setOpen(true);
    }, 0);
    return () => clearTimeout(timer);
  }, [router]);

  function move(next: number) {
    if (leaving) return;
    const commit = () => {
      setStep(next);
      setLeaving(false);
      try { window.localStorage.setItem(STEP_KEY, String(next)); } catch { /* In-memory progress still works. */ }
    };
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) { commit(); return; }
    setLeaving(true);
    transitionTimer.current = setTimeout(commit, 180);
  }

  function finish(status: "closed" | "completed") {
    if (transitionTimer.current) clearTimeout(transitionTimer.current);
    try {
      window.localStorage.setItem(STATUS_KEY, status);
      window.localStorage.removeItem(STEP_KEY);
      window.localStorage.removeItem(TOUR_KEY);
    } catch { /* The current session can still be dismissed. */ }
    setOpen(false);
    setTourActive(false);
  }

  function startTour() {
    if (transitionTimer.current) clearTimeout(transitionTimer.current);
    try { window.localStorage.setItem(TOUR_KEY, "0"); } catch { /* Tour still works for this visit. */ }
    setOpen(false);
    setTourStep(0);
    setTourActive(true);
    router.push(tourSteps[0].route);
  }

  function moveTour(next: number) {
    if (next === tourSteps.length) { finish("completed"); return; }
    setTourStep(next);
    try { window.localStorage.setItem(TOUR_KEY, String(next)); } catch { /* In-memory progress still works. */ }
    if (next === 5) {
      const articleId = document.querySelector<HTMLElement>('[data-onboarding="feed-card"]')?.dataset.articleId;
      if (articleId) { router.push(`/event?article_id=${encodeURIComponent(articleId)}`); return; }
    }
    router.push(tourSteps[next].route);
  }

  function leaveForRoute() {
    if (transitionTimer.current) clearTimeout(transitionTimer.current);
    setLeaving(false);
    setOpen(false);
  }

  const openAgain = useCallback(() => {
    if (transitionTimer.current) clearTimeout(transitionTimer.current);
    try {
      window.localStorage.removeItem(STATUS_KEY);
      window.localStorage.setItem(STEP_KEY, "0");
      window.localStorage.removeItem(TOUR_KEY);
    } catch { /* The Sheet remains usable without storage. */ }
    setStep(0);
    setLeaving(false);
    setTourActive(false);
    setOpen(true);
  }, []);

  useEffect(() => {
    window.addEventListener("alfa:open-onboarding", openAgain);
    return () => window.removeEventListener("alfa:open-onboarding", openAgain);
  }, [openAgain]);

  useEffect(() => {
    if (!tourActive) return;
    const main = document.getElementById("main-content");
    if (!main) return;
    const previous = main.style.paddingBottom;
    main.style.paddingBottom = "420px";
    return () => { main.style.paddingBottom = previous; };
  }, [tourActive]);

  useEffect(() => {
    if (!tourActive || pathname !== tourSteps[tourStep].route) return;
    const selector = `[data-onboarding="${tourSteps[tourStep].target}"]`;
    let scrolled = false;
    const measure = () => {
      const exact = document.querySelector<HTMLElement>(selector);
      const target = exact || document.querySelector<HTMLElement>(pathname === "/feed" ? '[data-onboarding="feed-tabs"]' : '[data-onboarding="workspace-heading"]');
      setViewport({ width: window.innerWidth, height: window.innerHeight });
      if (!target) { setSpotlight(null); return; }
      if (exact && !scrolled) {
        scrolled = true;
        exact.scrollIntoView({ block: "start", behavior: "instant" });
      }
      const rect = target.getBoundingClientRect();
      setSpotlight({ step: tourStep, path: pathname, top: rect.top, left: rect.left, width: rect.width, height: rect.height });
    };
    const timer = setTimeout(measure, 100);
    const root = document.getElementById("main-content");
    const observer = new MutationObserver(measure);
    if (root) observer.observe(root, { childList: true, subtree: true });
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    return () => {
      clearTimeout(timer);
      observer.disconnect();
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure, true);
    };
  }, [tourActive, tourStep, pathname]);

  useEffect(() => {
    if (!tourActive) return;
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") finish("closed"); };
    window.addEventListener("keydown", escape);
    return () => window.removeEventListener("keydown", escape);
  }, [tourActive]);

  const current = steps[step];
  const tour = tourSteps[tourStep];
  const visibleSpotlight = spotlight?.step === tourStep && spotlight.path === pathname ? spotlight : null;
  const tipWidth = Math.min(370, viewport.width - 24);
  const tipBelow = !visibleSpotlight || visibleSpotlight.top + visibleSpotlight.height + 330 <= viewport.height || visibleSpotlight.top < 330;
  const tipLeft = visibleSpotlight ? Math.max(12, Math.min(visibleSpotlight.left + visibleSpotlight.width / 2 - tipWidth / 2, viewport.width - tipWidth - 12)) : Math.max(12, (viewport.width - tipWidth) / 2);
  const tipTop = visibleSpotlight ? (tipBelow ? visibleSpotlight.top + visibleSpotlight.height + 20 : 0) : Math.max(12, (viewport.height - 300) / 2);
  const arrowLeft = visibleSpotlight ? Math.max(24, Math.min(tipWidth - 24, visibleSpotlight.left + visibleSpotlight.width / 2 - tipLeft)) : 30;
  const tipStyle: CSSProperties = { width: tipWidth > 0 ? tipWidth : 340, left: tipLeft, ...(tipBelow ? { top: Math.max(12, tipTop) } : { bottom: Math.max(12, viewport.height - visibleSpotlight!.top + 20) }) };
  return <>
    <Drawer id="onboarding" open={open} onClose={() => finish("closed")} label="Новостная аналитика для вашего бизнеса" closeLabel="Закрыть онбординг" side="right" mobileBottom width="min(760px, 100%)">
        <div className={s.sheetContent} data-sheet-scroll>
          <div className={s.content} data-sheet-scroll>
            <span className={s.eyebrow}>БЫСТРЫЙ СТАРТ</span>
            <h2 id="onboarding-title">Новостная аналитика для вашего бизнеса</h2>
            <p className={s.intro} id="onboarding-intro">Четыре шага от выбора компании до проверяемого разбора новости.</p>
            <div className={s.progress} aria-label={`Шаг ${step + 1} из ${steps.length}`}>
              {steps.map((item, index) => <span key={item.title} className={index <= step ? s.active : ""} />)}
            </div>
            <div className={`${s.stage} ${leaving ? s.leaving : ""}`} aria-live="polite">
              <p className={s.count}>Шаг {step + 1} из {steps.length}</p>
              <h3>{current.title}</h3>
              <p>{current.text}</p>
              <Button variant="text" href={current.href} onClick={leaveForRoute}>{current.link} <Icon name="arrow" size={16} /></Button>
            </div>
            <div className={s.actions}>
              <Button variant="primary" onClick={startTour}>Показать в интерфейсе</Button>
              {step > 0 && <Button disabled={leaving} onClick={() => move(step - 1)}>Назад</Button>}
              {step < steps.length - 1
                ? <Button disabled={leaving} onClick={() => move(step + 1)}>Смотреть шаги</Button>
                : <Button disabled={leaving} onClick={() => finish("completed")}>Завершить без экскурсии</Button>}
            </div>
            <Button variant="text" onClick={() => finish("closed")}>Больше не показывать</Button>
          </div>
          <div className={`${s.visual} ${leaving ? s.visualLeaving : ""}`} style={{ backgroundColor: current.tint }}>
            {steps.map((item, index) => <div key={item.image} className={`${s.imageLayer} ${index === step ? s.imageActive : ""}`}>
              <Image src={item.image} alt="" fill sizes="(max-width: 700px) 100vw, 320px" unoptimized />
            </div>)}
            <span className={s.visualIndex}>0{step + 1} / 0{steps.length}</span>
            <a className={s.credit} href={current.source} target="_blank" rel="noreferrer">Иллюстрация: Альфа-Банк ↗</a>
          </div>
        </div>
    </Drawer>
    {tourActive && pathname === tour.route && createPortal(
      <div className={s.tourLayer}>
        {visibleSpotlight
          ? <div key={`${tourStep}:${pathname}`} className={s.spotlight} style={{ top: Math.max(0, visibleSpotlight.top - 7), left: Math.max(0, visibleSpotlight.left - 7), width: visibleSpotlight.width + 14, height: visibleSpotlight.height + 14 }} />
          : <div className={s.tourScrim} />}
        <div key={tourStep} className={s.tourTip} role="dialog" aria-label={`Экскурсия: ${tour.title}`} aria-modal="false" style={tipStyle} tabIndex={-1}>
          {visibleSpotlight && <span className={`${s.tourArrow} ${tipBelow ? s.arrowUp : s.arrowDown}`} style={{ left: arrowLeft }} />}
          <div className={s.tourTop}><span>ЭКСКУРСИЯ · {tourStep + 1}/{tourSteps.length}</span><Button variant="text" size={32} onClick={() => finish("closed")} aria-label="Закрыть экскурсию"><Icon name="close" size={18} /></Button></div>
          <h2>{tour.title}</h2>
          <p>{tour.text}</p>
          <div className={s.tourActions}>
            {tourStep > 0 && <Button onClick={() => moveTour(tourStep - 1)}>Назад</Button>}
            <Button variant="primary" onClick={() => moveTour(tourStep + 1)}>{tourStep === tourSteps.length - 1 ? "Завершить" : <>Далее <Icon name="arrow" size={16} /></>}</Button>
          </div>
          <Button variant="text" size={32} onClick={() => finish("closed")}>Больше не показывать</Button>
        </div>
      </div>, document.body,
    )}
  </>;
}

export function OnboardingTrigger({ className = "", label = "Как начать работу" }: { className?: string; label?: string }) {
  return <Button className={className} onClick={() => window.dispatchEvent(new Event("alfa:open-onboarding"))}>{label}</Button>;
}
