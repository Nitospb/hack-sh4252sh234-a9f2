import { readFile } from "node:fs/promises";
import { join } from "node:path";

export async function GET() {
  const file = join(process.cwd(), "node_modules", "swagger-ui-dist", "swagger-ui-bundle.js");
  return new Response(await readFile(file), {
    headers: {
      "Content-Type": "text/javascript; charset=utf-8",
      "Cache-Control": "public, max-age=3600",
      "X-Content-Type-Options": "nosniff",
    },
  });
}
