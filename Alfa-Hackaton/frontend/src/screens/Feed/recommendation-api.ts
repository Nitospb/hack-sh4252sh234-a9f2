export type Company = {
  company_id: string; source_record_id: string; okved: string; activity: string;
  region: string; display_label?: string; available_count: number; industry_count: number; topic_count: number;
};
export type Interest = { family_key: string; object: string; relation: string; reason: string; topic_ids: string[] };
export type Context = Company & { interests: Interest[]; interest_counts: Record<string, number> };
export type Match = { family_key: string; name: string; relation: string; company_reason: string; evidence: string };
export type IndustryMatch = { sector_id: string; score: number; evidence: string; reason: string; relation: string };
export type Story = { story_id:string;member_count:number;visible_evidence_count:number;distinct_hosts:number;dedup_safe:boolean;
 items:{article_id:string;title:string;source:string;url:string;published_at:string;text?:string}[];
 numeric_variants:{unit:string;values:{value:string;evidence:{article_id:string;quote:string}[]}[]}[];limitations:string[] };
export type Article = { story?:Story|null;story_id?:string;story_publications?:number;
  article_id: string; title: string; source: string; url: string; published_at: string | null; kind: string;
  status?: string; text?: string; excerpt?: string; matched_objects?: Match[]; matched_industries?: IndustryMatch[];
  review_required?: boolean; match_level?: string; recommended_lane?: string; reading_minutes?: number;
  recommendation_reasons?: { kind: string; text: string }[]; components?: Record<string, number>;
};
export type ArticleState = { liked?: boolean; saved?: boolean; hidden?: boolean; disliked?: boolean; viewed?: boolean };
export type Profile = { role: string; topic_ids: string[]; article_states: Record<string, ArticleState>; stats: { viewed: number; saved: number; liked: number } };
export type CollectionStatus = { phase?: string; running?: boolean; stale?: boolean; cooldown_sources?: number; last_attempt?: string; last_publish_success?: string; collected_articles?: number; eligible_articles?: number; error_type?: string | null; source_health?: {source_id:string;cooldown_until:number;last_error?:string|null}[] };
export type Health = { analysis_availability?:{available:boolean;reason:string;message:string;resets_at:string|null;policy:string}; bank_retrieval?:{mode:string;semantic_passages:number;encoder_compatible:boolean;quality_measured:boolean}; catalog_publication?: { enabled: boolean; serving_version?: string|null; reload_error?: string|null; publication_lag_seconds?: number|null; pending_serving_reload?: boolean; collection?: CollectionStatus }; dataset_kind?: "synthetic" | "collected"; counts: { news: number; telegram_post: number; companies: number }; catalog_updated_at: string; llm_available: boolean; ranking_version?: string };
export type FeedResult = { request_id: string; items: Article[]; shortfall: number; eligible_catalog: number; company_topic_count: number; mode: string };
export type Explanation = { company_id?: string; source_record_id?: string; role?: string; mode: string; title: string; event: string; why_for_company: string[]; questions: string[]; limitations: string[]; ai_generated: boolean; source: { id: string; url: string; published_at: string }; llm_available: boolean };
export const ROLES = [
  { id: "general", label: "Общие интересы", detail: "Главное о бизнесе и вашей отрасли" },
  { id: "director", label: "Руководитель", detail: "Рынки, стратегия и развитие бизнеса" },
  { id: "finance", label: "Финансовый директор", detail: "Финансирование, экономика и риски" },
  { id: "accountant", label: "Главный бухгалтер", detail: "Налоги, отчётность и изменения правил" },
  { id: "treasurer", label: "Казначей", detail: "Ликвидность, ставки и валютные курсы" },
  { id: "procurement", label: "Закупки", detail: "Поставщики, цены и логистика" },
  { id: "it", label: "IT и технологии", detail: "ИИ, инфраструктура и безопасность" },
];
export const RELATIONS: Record<string, string> = { declared_activity: "Деятельность компании", activity_scope_candidate: "Смежное направление", operating_exposure: "Операционные интересы", industry_context: "Ваша отрасль" };
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/live/${path}`, { ...init, cache: "no-store" });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Не удалось получить данные");
  return result;
}

export function post<T>(path: string, payload: unknown) {
  return api<T>(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
}
export function displayDate(value: string | null, full = false) {
  return value ? new Date(value).toLocaleString("ru-RU", { timeZone: "Europe/Moscow", day: "numeric", month: full ? "long" : "short", ...(full ? { hour: "2-digit", minute: "2-digit" } : {}) }) : "Дата не установлена";
}
export function companyLabel(company: Company) {
  return company.display_label || company.activity?.split(";")[0] || company.company_id;
}
export function articleHeadline(article: Article) {
  if (article.kind !== "telegram_post" || article.title.length < 150) return article.title;
  const sentence = article.title.match(/^(.{40,}?[.!?])(?:\s|$)/)?.[1];
  if (sentence) return sentence;
  return article.title.slice(0, 164).replace(/\s+\S*$/, "") + "…";
}
