import { EVENTS } from "@/src/data/demo";
import type { Client, FeedSettings, PersonalizedEvent } from "@/src/types";

export const DEFAULT_SETTINGS: FeedSettings = {
  threshold: 40,
  opportunities: true,
  group: true,
  promotions: true,
  push: true,
  digest: true,
  weekly: false,
  telegram: false,
};

export const PRODUCTS: Record<string, string> = {
  RKO: "РКО",
  LOA: "Кредит",
  LEA: "Лизинг",
  GAR: "Гарантии",
  ZPP: "Зарплатный",
  DEP: "Депозит",
  FACT: "Факторинг",
};

export const KIND_LABELS = {
  risk: "Риск",
  opp: "Возможность",
  watch: "Наблюдать",
};

export const getClientEvents = (client: Client): PersonalizedEvent[] =>
  EVENTS.flatMap((event) => {
    const interpretation = event.per[client.id];
    return interpretation ? [{ ...event, p: interpretation }] : [];
  }).sort((first, second) => second.p.rel - first.p.rel);

export const getVisibleEvents = (client: Client, settings: FeedSettings) =>
  getClientEvents(client).filter(
    (event) =>
      event.p.rel >= settings.threshold &&
      (settings.opportunities || event.p.kind !== "opp"),
  );

export const eventHref = (id: string) => `/event?id=${id}`;
export const chatHref = (question = "", eventId = "") =>
  `/chat?${new URLSearchParams({ ...(question && { q: question }), ...(eventId && { ev: eventId }) })}`;

export const getEventTitle = (event: PersonalizedEvent) =>
  `${event.title}: ${event.p.head.charAt(0).toLowerCase()}${event.p.head.slice(1)}`;
