export type InsightKind = "risk" | "opp" | "watch";

export interface SourceDocument {
  t: string;
  k: string;
  date: string;
  type: string;
}

export interface Client {
  id: string;
  name: string;
  short: string;
  user: { name: string; ini: string; role: string };
  okved: string;
  okvedName: string;
  revenue: string;
  workers: string;
  age: string;
  stage: string;
  region: string;
  city: string;
  okfs: string;
  orgType: string;
  clType: string;
  fts: string;
  group: string;
  groupSize: number;
  products: Record<string, number>;
  accounts: string[][];
  facts: string[];
  counter: string[][];
}

export interface Interpretation {
  rel: number;
  kind: InsightKind;
  lvl: string;
  head: string;
  why: string;
  risks: string[];
  opps: string[];
  actions: string[];
  ai: string[];
  feats: string[];
  assume: string;
  promo?: { t: string; d: string };
}

export interface NewsEvent {
  id: string;
  cat: string;
  ago: string;
  title: string;
  fact: string;
  docs: string[];
  bank: string;
  per: Record<string, Interpretation | undefined>;
}

export interface PersonalizedEvent extends NewsEvent {
  p: Interpretation;
}

export interface FeedSettings {
  threshold: number;
  opportunities: boolean;
  group: boolean;
  promotions: boolean;
  push: boolean;
  digest: boolean;
  weekly: boolean;
  telegram: boolean;
}
