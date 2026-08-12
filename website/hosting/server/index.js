const latestArtifact =
  "/downloads/AgentBridge-0.9.0.622-AutoCAD-2024.zip";

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/download/latest") {
      return Response.redirect(new URL(latestArtifact, url), 307);
    }

    if (!env?.ASSETS?.fetch) {
      return new Response("Static asset binding is unavailable.", {
        status: 503,
        headers: { "content-type": "text/plain; charset=utf-8" },
      });
    }

    return env.ASSETS.fetch(request);
  },
};
