"use client";

import Script from "next/script";

export default function Swagger() {
  return (
    <>
      <div id="swagger-ui" />
      <Script
        src="/docs/swagger-ui.js"
        strategy="afterInteractive"
        onReady={() => {
          const swagger = window as typeof window & {
            SwaggerUIBundle?: (options: Record<string, unknown>) => void;
          };
          swagger.SwaggerUIBundle?.({
            url: "/api/live/openapi.json",
            dom_id: "#swagger-ui",
            deepLinking: true,
            docExpansion: "list",
          });
        }}
      />
    </>
  );
}
