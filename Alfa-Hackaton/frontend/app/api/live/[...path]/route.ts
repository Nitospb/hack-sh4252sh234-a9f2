import type { NextRequest } from "next/server";
const allowed = new Set(["health", "companies", "company", "article", "news", "feed", "insight", "events", "profile", "saved"]);
async function forward(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  if (path.length !== 1 || !allowed.has(path[0])) return Response.json({ error: "Not found" }, { status: 404 });
  if (request.method === "POST") {
    const origin = request.headers.get("origin");
    // Next's dev URL may use localhost while the browser uses 127.0.0.1.
    // Compare the browser origin with the actual request Host, preserving
    // same-origin protection for both supported loopback addresses.
    if (origin && (new URL(origin).host.toLowerCase() !== request.headers.get("host")?.toLowerCase() || !["http:", "https:"].includes(new URL(origin).protocol))) return Response.json({ error: "Invalid origin" }, { status: 403 });
  }
  const body = request.method === "POST" ? await request.text() : undefined;
  if (body && body.length > 65536) return Response.json({ error: "Request too large" }, { status: 413 });
  try {
    const response = await fetch(`http://127.0.0.1:${process.env.ALFA_API_PORT || "8091"}/${path[0]}${request.nextUrl.search}`, {
      method: request.method, headers: { "Content-Type": "application/json" }, body,
      cache: "no-store", signal: AbortSignal.timeout(path[0] === "insight" ? 125000 : 30000),
    });
    return new Response(await response.text(), { status: response.status, headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" } });
  } catch { return Response.json({ error: "Сервис данных недоступен. Запустите recommendations/server.py." }, { status: 503 }); }
}
export const GET = forward;
export const POST = forward;
