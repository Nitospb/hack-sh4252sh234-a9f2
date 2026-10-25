import type { PersonalizedEvent } from "@/src/types";

export const createInsightObject = (
  event: PersonalizedEvent,
  clientId: string,
) => {
  const bank = event.docs.filter((id) => id.startsWith("d"));
  const p = event.p;
  return {
    event_id: event.id,
    client_id: clientId,
    relevance: p.rel / 100,
    kind: p.kind,
    facts: [{ text: event.fact, source: event.docs[0], status: "confirmed" }],
    client_features: p.feats,
    why_relevant: p.why,
    risks: p.risks,
    opportunities: p.opps,
    actions: p.actions,
    bank_view: bank.length ? { text: event.bank, sources: bank } : null,
    model_conclusions: p.ai.map((text) => ({ text, origin: "llm" })),
    assumptions: p.assume ? [p.assume] : [],
    native_ad: p.promo?.t ?? null,
  };
};
