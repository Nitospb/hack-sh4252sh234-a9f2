"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { useSearchParams } from "next/navigation";
import { api, post, ROLES, RELATIONS, displayDate, companyLabel, articleHeadline, type Article, type ArticleState, type Company, type Context, type Explanation, type FeedResult, type Health, type Profile } from "./recommendation-api";
import s from "./RecommendationFeed.module.css";
import Link from "next/link";
import { StoryEvidence } from "@/src/components/StoryEvidence/StoryEvidence";
import { useLive } from "@/src/providers/LiveProvider";

type IconName = "switch" | "arrow" | "search" | "close" | "bookmark" | "like" | "hide" | "spark" | "settings" | "refresh" | "building" | "user" | "check" | "external" | "info";
function Icon({ name, size = 17 }: { name: IconName; size?: number }) {
  const paths: Record<IconName, ReactNode> = {
    switch: <><path d="M4 7h15m-4-4 4 4-4 4M20 17H5m4 4-4-4 4-4" /></>,
    arrow: <><path d="M5 12h14m-5-5 5 5-5 5" /></>,
    search: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 4 4" /></>,
    close: <path d="m6 6 12 12M6 18 18 6" />,
    bookmark: <path d="M6 4h12v17l-6-4-6 4z" />,
    like: <><path d="M7 10h3l3-7c3 0 2 5 2 7h4c1 0 2 1 1.8 2l-1.4 7c-.2 1-1 2-2 2H7zM3 10h4v11H3z" /></>,
    hide: <><path d="M3 3 21 21M10 5a12 12 0 0 1 11 7 15 15 0 0 1-4 5M6 6a15 15 0 0 0-4 6c4 8 12 9 17 5" /><path d="M9 9a4 4 0 0 0 6 6" /></>,
    spark: <><path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z" /></>,
    settings: <><path d="M4 6h16M4 12h16M4 18h16" /><circle cx="9" cy="6" r="2" fill="currentColor" stroke="none" /><circle cx="16" cy="12" r="2" fill="currentColor" stroke="none" /><circle cx="8" cy="18" r="2" fill="currentColor" stroke="none" /></>,
    refresh: <><path d="M20 7v5h-5M4 17v-5h5" /><path d="M6 7a7 7 0 0 1 12-1l2 3M4 15l2 3a7 7 0 0 0 12-1" /></>,
    building: <><path d="M5 21V4h14v17M3 21h18M9 21v-5h6v5M9 8h1m4 0h1M9 12h1m4 0h1" /></>,
    user: <><circle cx="12" cy="8" r="4" /><path d="M4 21v-2a8 8 0 0 1 16 0v2" /></>,
    check: <path d="m5 12 4 4L19 6" />,
    external: <><path d="M14 3h7v7m0-7L10 14M10 3H4v17h16v-6" /></>,
    info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v6m0-10v1" /></>,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}

function Dialog({ open, onClose, title, subtitle, children, footer, article = false }: { open: boolean; onClose: () => void; title: string; subtitle?: string; children: ReactNode; footer?: ReactNode; article?: boolean }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => { const d = ref.current; if (open && !d?.open) d?.showModal(); if (!open && d?.open) d.close(); }, [open]);
  return <dialog ref={ref} className={`${s.dialog} ${article ? s.articleDialog : ""}`} onCancel={onClose} onClick={e => { if (e.target === ref.current) onClose(); }} aria-label={title}>
    <div className={s.dialogHeader}><div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div><button className={s.iconButton} onClick={onClose} aria-label="Закрыть окно"><Icon name="close" size={21} /></button></div>
    <div className={s.dialogBody}>{children}</div>{footer && <div className={s.dialogFooter}>{footer}</div>}
  </dialog>;
}

function CompanyPicker({ open, onClose, featured, selected, onSelect }: { open: boolean; onClose: () => void; featured: Company[]; selected: Company | null; onSelect: (c: Company) => void }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Company[]>([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!open || !query.trim()) return;
    const abort = new AbortController();
    const timer = setTimeout(() => { setPending(true); setError(""); api<{ items: Company[] }>(`companies?q=${encodeURIComponent(query)}&limit=12`, { signal: abort.signal }).then(r => setResults(r.items)).catch(e => { if (!abort.signal.aborted) setError(String(e)); }).finally(() => { if (!abort.signal.aborted) setPending(false); }); }, 250);
    return () => { clearTimeout(timer); abort.abort(); };
  }, [open, query]);
  const list = query.trim() ? results : featured;
  return <Dialog open={open} onClose={onClose} title="Сменить компанию" subtitle="Выберите профиль из разных отраслей или найдите компанию по ID и ОКВЭД.">
    <label className={s.searchLabel} htmlFor="company-search">Поиск компании</label><div className={s.searchBox}><Icon name="search" /><input id="company-search" placeholder="ID компании, ОКВЭД или деятельность" value={query} onChange={e => setQuery(e.target.value)} /></div>
    <p className={s.micro}>В исходных данных нет названий компаний. Профили обозначены деятельностью и настоящим обезличенным ID.</p>
    {error && <p className={s.error}>{error}</p>}{pending && <p className={s.micro}>Ищем компании…</p>}
    <div className={s.companyChoices}>{list.map(c => <button key={c.source_record_id} className={s.companyChoice} aria-pressed={selected?.source_record_id === c.source_record_id} onClick={() => { onSelect(c); onClose(); }}><span className={s.companyIcon}><Icon name="building" /></span><span><strong>{companyLabel(c)}</strong><small>{c.company_id} · ОКВЭД {c.okved}<br />{c.region}</small><span className={s.coverage}>{c.topic_count} тем · {c.available_count} материалов в пуле</span></span></button>)}</div>
    {!pending && query && !list.length && <div className={s.empty}>Компании не найдены. Попробуйте другой ID или код.</div>}
  </Dialog>;
}

function Preferences({ open, onClose, context, profile, onSave }: { open: boolean; onClose: () => void; context: Context | null; profile: Profile | null; onSave: (role: string, ids: string[]) => Promise<void> }) {
  const [role, setRole] = useState("general"); const [topics, setTopics] = useState<string[]>([]); const [pending, setPending] = useState(false); const [error, setError] = useState("");
  useEffect(() => { if (!open) return; const timer = setTimeout(() => { setRole(profile?.role || "general"); setTopics(profile?.topic_ids || []); setError(""); }, 0); return () => clearTimeout(timer); }, [open, profile]);
  const interests = context?.interests || [];
  async function save() { setPending(true); try { await onSave(role, topics); onClose(); } catch (e) { setError(String(e)); } finally { setPending(false); } }
  return <Dialog open={open} onClose={onClose} title="Настроить под себя" subtitle="Роль и выбранные темы дополняют интересы компании. Должность не определяется автоматически." footer={<><span>{topics.length} личных тем выбрано</span><button className={s.primary} disabled={pending} onClick={save}>{pending ? "Сохраняем…" : "Применить настройки"}</button></>}>
    <h3 className={s.modalSection}>Что вам ближе по работе?</h3><div className={s.roleGrid}>{ROLES.map(r => <button key={r.id} className={`${s.roleChoice} ${role === r.id ? s.active : ""}`} aria-pressed={role === r.id} onClick={() => setRole(r.id)}><span className={s.checkmark}>{role === r.id && <Icon name="check" size={10} />}</span><span><strong>{r.label}</strong><small>{r.detail}</small></span></button>)}</div>
    <h3 className={s.modalSection}>Темы, которые хочется видеть чаще</h3><div className={s.modalChips}>{interests.filter(i => i.topic_ids.length).slice(0, 36).map(i => { const id = i.topic_ids[0], checked = topics.includes(id); return <button key={i.family_key} title={RELATIONS[i.relation]} className={`${s.modalChip} ${checked ? s.active : ""}`} aria-pressed={checked} onClick={() => setTopics(previous => checked ? previous.filter(t => t !== id) : [...previous, id])}>{i.object}</button>; })}</div>
    <p className={s.micro}>Смежные и операционные интересы — предположения по профилю бизнеса. Выбор темы не подтверждает специализацию компании.</p>{error && <p className={s.error}>{error}</p>}
  </Dialog>;
}

function ArticleReader({ article, company, role, open, onClose }: { article: Article | null; company: Company | null; role: string; open: boolean; onClose: () => void }) {
  const [body, setBody] = useState<Article | null>(null); const [explanation, setExplanation] = useState<Explanation | null>(null); const [tab, setTab] = useState("brief"); const [error, setError] = useState("");
  useEffect(() => {
    if (!open || !article) return;
    const abort = new AbortController();
    api<Article>(`article?article_id=${article.article_id}`, { signal: abort.signal }).then(setBody).catch(e => { if (!abort.signal.aborted) setError(String(e)); });
    if (company) api<Explanation>(`insight?${new URLSearchParams({ company_id: company.company_id, source_record_id: company.source_record_id, article_id: article.article_id, role })}`, { signal: abort.signal }).then(r => setExplanation({...r, company_id: company.company_id, source_record_id: company.source_record_id, role})).catch(e => { if (!abort.signal.aborted) setError(String(e)); });
    return () => abort.abort();
  }, [open, article, company, role]);
  const currentBody = body?.article_id === article?.article_id ? body : null;
  const currentExplanation = explanation?.source?.id === article?.article_id && explanation?.company_id === company?.company_id && explanation?.source_record_id === company?.source_record_id && explanation?.role === role ? explanation : null;
  return <Dialog open={open} onClose={onClose} title="Новость и контекст" article subtitle={article ? `${article.source} · ${displayDate(article.published_at, true)} МСК` : ""}>
    {article && <><StoryEvidence story={currentBody?.story}/><h2 className={s.articleTitle}>{articleHeadline(article)}</h2><a className={s.originLink} href={/^https?:\/\//.test(article.url) ? article.url : undefined} target="_blank" rel="noopener noreferrer">Перейти к первоисточнику <Icon name="external" size={13} /></a>
      <p><Link className={s.primary} href={`/event?article_id=${encodeURIComponent(article.article_id)}`}>Персональный разбор и диалог с аналитиком →</Link></p><div className={s.drawerTabs}><button className={`${s.tab} ${tab === "brief" ? s.selected : ""}`} onClick={() => setTab("brief")}>Кратко и по делу</button><button className={`${s.tab} ${tab === "text" ? s.selected : ""}`} onClick={() => setTab("text")}>Полный текст</button></div>
      {tab === "text" ? currentBody ? <div className={s.articleText}>{currentBody.text}</div> : <p className={s.micro}>Загружаем текст…</p> : <>
        <section className={s.analysisSection}><h3>Что произошло</h3><p>{currentExplanation?.event || article.excerpt || "Загружаем контекст…"}</p></section>
        <section className={s.analysisSection}><h3>Почему вам показано</h3>{(currentExplanation?.why_for_company?.length ? currentExplanation.why_for_company : article.recommendation_reasons?.map(r => r.text) || ["Общая деловая повестка"]).slice(0, 2).map((t, i) => <p key={i}>{t}</p>)}</section>
        {!!currentExplanation?.questions?.length && <section className={s.analysisSection}><h3>Что проверить в вашей компании</h3><ul>{currentExplanation.questions.map(q => <li key={q}>{q}</li>)}</ul></section>}
        <p className={s.modeLabel}>Краткий экстракт источника и объяснение тематической связи. Это не персональная финансовая оценка и не позиция банка.</p>
        {!!currentExplanation?.limitations?.length && <p className={s.micro}>{currentExplanation.limitations[0]}</p>}
      </>}{error && <p className={s.error}>{error}</p>}</>}
  </Dialog>;
}

function NewsCard({ article: a, state, user, company, requestId, onEvent, onRead }: { article: Article; state: ArticleState; user: string; company: Company | null; requestId: string; onEvent: (a: Article, kind: string, eventId?: string) => Promise<void>; onRead: (a: Article) => void }) {
  const ref = useRef<HTMLElement>(null); const [pending, setPending] = useState(""); const [error, setError] = useState(""); const sent = useRef(false);
  useEffect(() => {
    if (!company || !requestId || !ref.current) return;
    let timer: ReturnType<typeof setTimeout> | undefined; let visible = false; let stopped = false;
    function schedule() {
      clearTimeout(timer);
      if (visible && document.visibilityState === "visible" && !sent.current) timer = setTimeout(() => {
        if (stopped || document.visibilityState !== "visible") return;
        sent.current = true;
        onEvent(a, "view", `view:${requestId}:${a.article_id}`).catch(() => { sent.current = false; });
      }, 1000);
    }
    const observer = new IntersectionObserver(entries => { visible = entries[0].intersectionRatio >= .5; schedule(); }, { threshold: [.5] });
    observer.observe(ref.current); document.addEventListener("visibilitychange", schedule);
    return () => { stopped = true; clearTimeout(timer); observer.disconnect(); document.removeEventListener("visibilitychange", schedule); };
  }, [a, company, user, requestId, onEvent]);
  async function react(kind: string) { setPending(kind); setError(""); try { await onEvent(a, kind); } catch (e) { setError(String(e)); } finally { setPending(""); } }
  const industry = a.matched_industries?.[0]; const object = a.matched_objects?.[0];
  const primary = object?.name || (industry ? "Ваша отрасль" : a.recommended_lane === "personal" ? "Ваши интересы" : "Деловая повестка");
  const reason = industry ? "Тема из отраслевого контекста, близкого к деятельности компании" : object ? object.relation === "declared_activity" ? `Тема «${object.name}» связана с деятельностью компании` : object.relation === "operating_exposure" ? "Может быть полезно для операционных задач бизнеса" : "Может быть интересно для смежных направлений бизнеса" : a.recommended_lane === "personal" ? "С учётом вашей роли и прочитанных материалов" : "Общая деловая повестка: экономика, правила и рынки";
  const excerpt = a.title.length < 170 && a.excerpt?.startsWith(a.title) && /\s/.test(a.excerpt.charAt(a.title.length)) && a.excerpt.length > a.title.length + 35 ? a.excerpt.slice(a.title.length).replace(/^[\s.!?:—–-]+/, "") : a.excerpt;
  const colors = ["#59728f", "#a26963", "#678d82", "#88729b", "#a28c62"];
  const color = colors[Array.from(a.source || "").reduce((v, c) => v + c.charCodeAt(0), 0) % colors.length];
  return <article ref={ref} className={s.card} data-article-id={a.article_id}>
    <div className={s.cardHeader}><span className={s.sourceIcon} style={{ background: color }}>{a.source.replace("@", "").slice(0, 1).toUpperCase()}</span><span className={s.sourceName}>{a.source}</span><span className={s.sourceKind}>{a.kind === "telegram_post" ? "Telegram" : "Сайт"}</span><time dateTime={a.published_at || undefined}>{displayDate(a.published_at)}</time><span>· {a.reading_minutes || 2} мин</span></div>
    <h2><button className={s.titleButton} onClick={() => onRead(a)}>{articleHeadline(a)}</button></h2>
    {excerpt && <p className={s.excerpt}>{excerpt}</p>}
    <div className={s.tags}><span className={`${s.tag} ${s.tagPrimary}`}>{primary}</span>{object && <span className={s.tag}>{RELATIONS[object.relation] || "По теме"}</span>}{a.recommended_lane === "personal" && <span className={s.tag}>С учётом вашей роли</span>}</div>
    <div className={s.reason}><Icon name="spark" size={13} /><button onClick={() => onRead(a)} title="Посмотреть основания рекомендации">{reason.length > 180 ? reason.slice(0, 177) + "…" : reason}</button></div>
    <div className={s.actions}>{company && <><button className={s.action} aria-pressed={!!state.liked} disabled={!!pending} onClick={() => react(state.liked ? "unlike" : "like")}><Icon name="like" size={16} />{state.liked ? "Нравится" : "Полезно"}</button><button className={s.action} aria-pressed={!!state.saved} disabled={!!pending} onClick={() => react(state.saved ? "unsave" : "save")}><Icon name="bookmark" size={15} />{state.saved ? "Сохранено" : "Сохранить"}</button><button className={s.action} disabled={!!pending} onClick={() => react("hide")} title="Скрыть и учитывать при подборе"><Icon name="hide" size={16} />Не интересно</button></>}<button className={s.readButton} onClick={() => onRead(a)}>Читать <Icon name="arrow" size={15} /></button></div>
    {error && <p className={s.inlineError} role="alert">{error}</p>}
  </article>;
}

const EMPTY_PROFILE: Profile = { role: "general", topic_ids: [], article_states: {}, stats: { viewed: 0, liked: 0, saved: 0 } };
export default function RecommendationFeed() {
  const live = useLive();
  const urlQuery = useSearchParams().get("q") || "";
  const [health, setHealth] = useState<Health | null>(null); const [featured, setFeatured] = useState<Company[]>([]); const [company, setCompany] = useState<Company | null>(null); const [context, setContext] = useState<Context | null>(null); const [profile, setProfile] = useState<Profile>(EMPTY_PROFILE); const [user, setUser] = useState("");
  const [view, setView] = useState("personal"); const [kind, setKind] = useState("all"); const [strict, setStrict] = useState(false); const [search, setSearch] = useState(""); const [searchOpen, setSearchOpen] = useState(false);
  const [items, setItems] = useState<Article[]>([]); const [loading, setLoading] = useState(true); const [moreLoading, setMoreLoading] = useState(false); const [error, setError] = useState(""); const [total, setTotal] = useState(0); const [shortfall, setShortfall] = useState(0); const [page, setPage] = useState(0); const [requestId, setRequestId] = useState("");
  const [companyOpen, setCompanyOpen] = useState(false); const [preferencesOpen, setPreferencesOpen] = useState(false); const [methodOpen, setMethodOpen] = useState(false); const [settingsOpen, setSettingsOpen] = useState(false); const [article, setArticle] = useState<Article | null>(null); const [toast, setToast] = useState<{ text: string; undo?: { article: Article; kind: string } } | null>(null);
  const generation = useRef(0); const contextGeneration = useRef(0); const sessionRequests = useRef<Record<string, string>>({}); const latestQuery = useRef("");
  useEffect(() => { const timer = setTimeout(() => { if (urlQuery) { setSearch(urlQuery); setSearchOpen(true); setView("all"); } }, 0); return () => clearTimeout(timer); }, [urlQuery]);
  useEffect(() => { if (!toast) return; const timer = setTimeout(() => setToast(null), 5000); return () => clearTimeout(timer); }, [toast]);
  useEffect(() => { const open = () => setCompanyOpen(true); const preferences = () => setPreferencesOpen(true); window.addEventListener("alfa:company-switch", open); window.addEventListener("alfa:preferences", preferences); return () => { window.removeEventListener("alfa:company-switch", open); window.removeEventListener("alfa:preferences", preferences); }; }, []);

  const chooseCompany = useCallback(async (c: Company, uid: string) => {
    const revision = ++contextGeneration.current; generation.current++; setLoading(true); setError(""); setItems([]); setCompany(c); setContext(null); setPage(0); setProfile(EMPTY_PROFILE); setToast(null);
    try {
      const q = new URLSearchParams({ company_id: c.company_id, source_record_id: c.source_record_id, user_id: uid });
      const [details, personal] = await Promise.all([api<Context>(`company?${q}`), api<Profile>(`profile?${q}`)]);
      if (revision !== contextGeneration.current) return;
      setContext({ ...details, display_label: c.display_label, available_count: c.available_count, industry_count: c.industry_count }); setProfile(personal); localStorage.setItem("alfa-active-company-v2", c.source_record_id); window.dispatchEvent(new CustomEvent("alfa:company", { detail: c }));
    } catch (e) { if (revision === contextGeneration.current) { setError(String(e)); setLoading(false); } }
  }, []);

  useEffect(() => {
    let cancelled = false;
    const uid = localStorage.getItem("alfa-live-user") || crypto.randomUUID(); localStorage.setItem("alfa-live-user", uid);
    Promise.all([api<Health>("health"), api<{ items: Company[] }>("companies?limit=8")]).then(async ([h, c]) => {
      if (cancelled) return; setHealth(h); setUser(uid); setFeatured(c.items);
      const saved = localStorage.getItem("alfa-active-company-v2");
      const selected = c.items.find(item => item.source_record_id === saved) || (saved ? await api<Company>(`company?${new URLSearchParams({ company_id: saved.split(":line:")[0], source_record_id: saved })}`) : c.items[0]);
      if (selected) chooseCompany(selected, uid); else { setLoading(false); setError("Профили компаний пока недоступны"); }
    }).catch(e => { if (!cancelled) { setError(String(e)); setLoading(false); } });
    return () => { cancelled = true; };
  }, [chooseCompany]);

  const queryKey = [health?.ranking_version, company?.source_record_id, user, profile.role, profile.topic_ids.join(","), view, kind, strict].join("|");
  useEffect(() => { latestQuery.current = queryKey; }, [queryKey]);
  const fetchPage = useCallback(async (nextPage: number, append: boolean, fresh = false) => {
    if (!user || !company || !context) return;
    const capturedKey = queryKey; const revision = ++generation.current;
    if (append) setMoreLoading(true); else { setLoading(true); setError(""); }
    try {
      if (view === "personal") {
        const key = `alfa-ranked-v3:${capturedKey}:${nextPage}`;
        if (fresh) { delete sessionRequests.current[key]; sessionStorage.removeItem(key); }
        sessionRequests.current[key] ||= sessionStorage.getItem(key) || crypto.randomUUID(); sessionStorage.setItem(key, sessionRequests.current[key]);
        const q = new URLSearchParams({ company_id: company.company_id, source_record_id: company.source_record_id, user_id: user, limit: "24", scope: "interest", mode: strict ? "strict" : "ranked", role: profile.role, kind, request_id: sessionRequests.current[key] });
        const result = await api<FeedResult>(`feed?${q}`);
        if (revision !== generation.current || latestQuery.current !== capturedKey) return;
        setItems(previous => append ? [...previous, ...result.items.filter(a => !previous.some(p => p.article_id === a.article_id))] : result.items); setRequestId(result.request_id); setShortfall(result.shortfall); setTotal(result.eligible_catalog); setPage(nextPage);
      } else {
        const q = new URLSearchParams({ company_id: company.company_id, user_id: user, kind, limit: "30", offset: String(nextPage * 30), q: view === "all" ? search : "" });
        const result = await api<{ items: Article[]; total: number }>(`${view === "saved" ? "saved" : "news"}?${q}`);
        if (revision !== generation.current || latestQuery.current !== capturedKey) return;
        setItems(previous => append ? [...previous, ...result.items] : result.items); setTotal(result.total); setPage(nextPage); setShortfall(0); setRequestId("");
      }
    } catch (e) { if (revision === generation.current) setError(String(e)); }
    finally { if (revision === generation.current) { setLoading(false); setMoreLoading(false); } }
  }, [user, company, context, queryKey, view, strict, profile.role, kind, search]);

  useEffect(() => { const timer = setTimeout(() => fetchPage(0, false), 200); return () => clearTimeout(timer); }, [fetchPage]);
  function invalidate() { generation.current++; setItems([]); setLoading(true); setPage(0); }

  const recordEvent = useCallback(async (a: Article, event: string, id?: string) => {
    if (!company || !user) return;
    const owner = contextGeneration.current;
    await post("events", { company_id: company.company_id, user_id: user, article_id: a.article_id, kind: event, event_id: id || crypto.randomUUID() });
    if (owner !== contextGeneration.current) return;
    const changes: Record<string, Partial<ArticleState>> = { like: { liked: true }, unlike: { liked: false }, save: { saved: true }, unsave: { saved: false }, hide: { hidden: true }, unhide: { hidden: false }, view: { viewed: true }, open: { viewed: true } };
    setProfile(previous => {
      const before = previous.article_states[a.article_id] || {}; const next = { ...before, ...changes[event] };
      return { ...previous, article_states: { ...previous.article_states, [a.article_id]: next }, stats: { ...previous.stats, viewed: previous.stats.viewed + (!before.viewed && next.viewed ? 1 : 0), saved: previous.stats.saved + (Number(!!next.saved) - Number(!!before.saved)), liked: previous.stats.liked + (Number(!!next.liked) - Number(!!before.liked)) } };
    });
    if (event === "hide") { setItems(previous => previous.filter(item => item.article_id !== a.article_id)); setToast({ text: "Новость скрыта. Учтём при следующем подборе.", undo: { article: a, kind: "unhide" } }); }
    if (event === "save") setToast({ text: "Добавлено в сохранённое" });
    if (event === "unsave" && view === "saved") setItems(previous => previous.filter(item => item.article_id !== a.article_id));
  }, [company, user, view]);

  async function savePreferences(role: string, topicIds: string[]) {
    if (!company) return;
    await post("profile", { company_id: company.company_id, user_id: user, role, topic_ids: topicIds });
    live.refresh(); invalidate(); setProfile(previous => ({ ...previous, role, topic_ids: topicIds })); setToast({ text: "Настройки сохранены. Обновляем рекомендации." });
  }
  function openArticle(a: Article) { localStorage.setItem("alfa-active-article-v1", a.article_id);  setArticle(a); if (company) recordEvent(a, "open").catch(() => {}); }
  const displayed = items.filter(a => (view !== "personal" || !profile.article_states[a.article_id]?.hidden) && (kind === "all" || a.kind === kind) && (!search || view === "all" || `${a.title} ${a.source} ${a.matched_objects?.map(m => m.name).join(" ")}`.toLowerCase().includes(search.toLowerCase())));
  const currentRole = ROLES.find(r => r.id === profile.role) || ROLES[0]; const sources = new Set(displayed.map(a => a.source)).size;
  const mainInterests = context?.interests.filter(i => i.relation !== "operating_exposure") || [];
  const mix = [{ label: "Компания и отрасль", value: 60, color: "#8c9fb7" }, { label: "Общее для бизнеса", value: 10, color: "#c1cbd8" }, { label: "Популярность", value: 10, color: "#d8dee7" }, { label: "Личные интересы", value: 20, color: "#dfbcb5" }];

  return <div className={s.page}>
    <header className={s.header}><div><p className={s.eyebrow}>АЛЬФА-БИЗНЕС / НОВОСТНАЯ АНАЛИТИКА</p><h1>Важное для вашего бизнеса</h1><p className={s.subtitle}>Новости вашей отрасли, новые возможности и деловая повестка.</p></div><button className={s.switch} onClick={() => setCompanyOpen(true)} aria-label="Сменить компанию" aria-haspopup="dialog"><span className={s.companyIcon}><Icon name="building" size={19} /></span><span><strong>{company ? companyLabel(company) : "Выберите компанию"}</strong><small>Сменить компанию · {company?.company_id}</small></span><span className={s.chevron}><Icon name="switch" size={16} /></span></button></header>
    <div className={s.quickbar} aria-label="Быстрое переключение компании">{featured.map(c => <button key={c.source_record_id} className={`${s.quick} ${company?.source_record_id === c.source_record_id ? s.active : ""}`} aria-pressed={company?.source_record_id === c.source_record_id} onClick={() => { if (c.source_record_id !== company?.source_record_id) chooseCompany(c, user); }}>{companyLabel(c)}</button>)}<button className={s.quick} onClick={() => setCompanyOpen(true)}>Все компании ↗</button></div>
    <div className={s.layout}><section className={s.stream} aria-label="Новостная лента">
      <div className={s.toolbar}><div className={s.tabs}>{[["personal", "Для вас"], ["saved", "Сохранённое"], ["all", "Все новости"]].map(([id, label]) => <button key={id} className={`${s.tab} ${view === id ? s.selected : ""}`} aria-pressed={view === id} onClick={() => { if (view !== id) { invalidate(); setView(id); setSearch(""); } }}>{label}{id === "saved" && profile.stats.saved > 0 && <span className={s.count}>{profile.stats.saved}</span>}</button>)}<button className={s.searchButton} aria-label="Искать новости" aria-expanded={searchOpen} onClick={() => setSearchOpen(previous => !previous)}><Icon name="search" size={19} /></button></div></div>
      {searchOpen && <div className={s.searchBox}><Icon name="search" size={16} /><input aria-label="Поиск новостей" placeholder={view === "all" ? "Поиск во всём корпусе" : "Найти в текущей подборке"} value={search} onChange={e => setSearch(e.target.value)} /><button aria-label="Очистить поиск" onClick={() => setSearch("")}><Icon name="close" size={15} /></button></div>}
      <div className={s.filterRow}><div className={s.segments}>{[["all", "Все источники"], ["news", "Сайты"], ["telegram_post", "Telegram"]].map(([id, label]) => <button key={id} className={`${s.segment} ${kind === id ? s.chosen : ""}`} aria-pressed={kind === id} onClick={() => { if (kind !== id) { invalidate(); setKind(id); } }}>{label}</button>)}</div><button className={s.settingsButton} onClick={() => setSettingsOpen(true)}><Icon name="settings" size={13} />{strict ? "Строгий отбор" : "Настроить ленту"}</button></div>
      <div className={s.summaryRow}><span>{loading ? "Подбираем материалы" : view === "personal" ? `${displayed.length} новостей · ${sources} источников · без повторов` : view === "saved" ? `${displayed.length} сохранённых материалов` : `${total.toLocaleString("ru-RU")} материалов в корпусе`}</span><button onClick={() => fetchPage(0, false, true)} disabled={loading || moreLoading}><Icon name="refresh" size={12} />Обновить</button></div>
      {error && <div className={s.error} role="alert">{error}</div>}
      <div className={s.cards} aria-busy={loading}>{loading ? [0, 1, 2].map(i => <div className={s.skeleton} key={i} aria-hidden="true" />) : displayed.length ? displayed.map(a => <NewsCard key={`${company?.source_record_id}:${a.article_id}`} article={a} state={profile.article_states[a.article_id] || {}} user={user} company={view === "all" ? null : company} requestId={view === "personal" ? requestId : ""} onEvent={recordEvent} onRead={openArticle} />) : <div className={s.empty}><Icon name={view === "saved" ? "bookmark" : "search"} size={27} /><strong>{view === "saved" ? "Сохраните то, к чему хотите вернуться" : "Пока нет подходящих материалов"}</strong>{view === "saved" ? "Нажмите «Сохранить» на любой новости в ленте." : strict ? "В строгом режиме совпадений мало. Попробуйте рекомендательный подбор в настройках." : "Попробуйте другой источник или компанию. Прочитанные и скрытые новости не повторяются."}</div>}</div>
      {!loading && view !== "saved" && displayed.length > 0 && <div className={s.loadMore}><button className={s.secondary} disabled={moreLoading || (view === "all" && items.length >= total) || (view === "personal" && shortfall > 0)} onClick={() => fetchPage(page + 1, true)}>{moreLoading ? "Подбираем ещё…" : view === "personal" ? "Ещё 24 новости ↓" : "Показать ещё ↓"}</button></div>}
      {!loading && view === "personal" && shortfall > 0 && <p className={s.micro}>Свежая подборка короче: подходящие непрочитанные материалы заканчиваются. Мы не заполняем её повторами.</p>}
    </section><aside className={s.sidebar}>
      <section className={s.contextCard}><div className={s.sectionTitle}><h2>Ваш контекст</h2><button className={s.iconButton} onClick={() => setPreferencesOpen(true)} aria-label="Настроить личные интересы"><Icon name="settings" size={15} /></button></div><button className={s.roleBadge} style={{ border: 0, width: "100%", textAlign: "left", cursor: "pointer" }} onClick={() => setPreferencesOpen(true)}><Icon name="user" size={17} /><span><strong>{currentRole.label}</strong><small>Настроить личные интересы ↗</small></span></button>
        <span className={s.smallLabel}>ДЕЯТЕЛЬНОСТЬ И СМЕЖНЫЕ ТЕМЫ</span><div className={s.interestChips}>{mainInterests.slice(0, 7).map(i => <span key={i.family_key} className={s.interestChip} title={RELATIONS[i.relation]}>{i.object}</span>)}</div><button className={s.textButton} onClick={() => setPreferencesOpen(true)}>Все {context?.interests.length || 0} тем и интересов →</button><p className={s.micro}>Профиль по ОКВЭД {company?.okved}. Операционные интересы — отдельные предположения, а не специализации.</p>
      </section>
      <section className={s.contextCard}><div className={s.sectionTitle}><h2>Как устроена подборка</h2><button className={s.iconButton} onClick={() => setMethodOpen(true)} aria-label="Как работают рекомендации"><Icon name="info" size={15} /></button></div><div className={s.mix}>{mix.map(m => <i key={m.label} style={{ width: `${m.value}%`, background: m.color }} />)}</div><div className={s.mixLegend}>{mix.map(m => <div key={m.label} className={s.legendRow}><i className={s.dot} style={{ background: m.color }} />{m.label}<strong>{m.value}%</strong></div>)}</div><p className={s.micro}>Веса ранжирования. Разнообразие тем и источников учитывается отдельно.</p></section>
      <section className={s.learnCard}><div className={s.learnIcon}><Icon name="spark" size={22} /></div><h3>Лента узнаёт ваши интересы</h3><p>Отмечайте полезное и скрывайте лишнее. Просмотры и реакции помогают подбирать следующие новости.</p><button className={s.textButton} onClick={() => setPreferencesOpen(true)}>Настроить под себя →</button></section>
      <div className={s.dataNote}><div className={s.footerInfo}><i className={s.statusDot} />{health ? `${(health.counts.news + health.counts.telegram_post).toLocaleString("ru-RU")} материалов · сайты и Telegram` : "Подключаем источники"}</div><p>Обновлено {health ? displayDate(health.catalog_updated_at) : "…"}. Тематическая связь не подтверждает финансовый эффект. Точность ещё не измерена на ручной разметке.</p></div>
    </aside></div>
    <CompanyPicker open={companyOpen} onClose={() => setCompanyOpen(false)} featured={featured} selected={company} onSelect={c => chooseCompany(c, user)} />
    <Preferences open={preferencesOpen} onClose={() => setPreferencesOpen(false)} context={context} profile={profile} onSave={savePreferences} />
    <ArticleReader open={!!article} onClose={() => setArticle(null)} article={article} company={company} role={profile.role} />
    <Dialog open={settingsOpen} onClose={() => setSettingsOpen(false)} title="Настроить ленту" subtitle="Выберите глубину отбора. Источники и история просмотров учитываются в обоих режимах."><fieldset className={s.fieldset}><legend>Подбор материалов</legend><label className={s.settingRow}><input type="radio" name="feed-policy" checked={!strict} onChange={() => { invalidate(); setStrict(false); }} /><span><strong>Рекомендательная лента</strong><br />Деятельность, отраслевой контекст и общие интересы бизнеса. Ранжирование и разнообразие через MMR.</span></label><label className={s.settingRow}><input type="radio" name="feed-policy" checked={strict} onChange={() => { invalidate(); setStrict(true); }} /><span><strong>Только строгие тематические совпадения</strong><br />Для проверки качества разметки. Подходящих новостей пока немного.</span></label></fieldset><button className={s.textButton} onClick={() => { setSettingsOpen(false); setPreferencesOpen(true); }}>Изменить роль и личные темы →</button></Dialog>
    <Dialog open={methodOpen} onClose={() => setMethodOpen(false)} title="Рекомендации, которые учитывают вас" subtitle="Почему подборка отличается у компаний и меняется после ваших действий."><div className={s.methodList}>{[["Интересы бизнеса", "Темы связаны с ОКВЭД компании. Деятельность, смежные направления и операционные интересы различаются."], ["Ранжирование 60 / 10 / 10 / 20", "Компания и отрасль, общая деловая повестка, популярность и личные интересы. Это веса оценки, а не фиксированные квоты карточек."], ["Разнообразие через MMR", "Отбираем полезное и уменьшаем близость к уже выбранным материалам. Учитываем разные источники; точные и близкие дубли исключаем."], ["Учёт настоящих просмотров", "Просмотр записывается, когда хотя бы половина карточки видна не менее секунды в активной вкладке. Открытие, полезность и сохранение — отдельные сигналы."], ["Без искусственного заполнения", "Прочитанные и скрытые материалы исключаются. Когда доступный корпус заканчивается, подборка может быть короче 24 новостей."]].map(([title, text], i) => <div className={s.methodStep} key={title}><span className={s.stepNumber}>{i + 1}</span><p><strong>{title}</strong>{text}</p></div>)}</div></Dialog>
    {toast && <div className={s.toast} role="status">{toast.text}{toast.undo && <button onClick={async () => { const undo = toast.undo!; await recordEvent(undo.article, undo.kind); setItems(previous => [undo.article, ...previous]); setToast(null); }}>Отменить</button>}</div>}
  </div>;
}
