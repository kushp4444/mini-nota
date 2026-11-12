// The browser sees only same-origin application routes. ENGINE_URL stays private.
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
async function proxy(
  request: Request,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params;
  if (!(
    path[0] === "runs" &&
    (path.length === 1 ||
      path.length === 2 ||
      (path.length === 3 && ["events", "event-page", "cancel", "approve"].includes(path[2])) ||
      (path.length === 5 && path[2] === "artifacts"))
  ))
    return new Response("Not found", { status: 404 });
  const base = process.env.RUNNER_URL;
  if (!base)
    return Response.json(
      { detail: "Runner service is not configured" },
      { status: 503 },
    );
  try {
    const url = new URL(
      path.map(encodeURIComponent).join("/"),
      base.replace(/\/$/, "") + "/",
    );
    url.search = new URL(request.url).search;
    let body: string | undefined;
    if (request.method === "POST") {
      const chunks: Uint8Array[] = [];
      let size = 0;
      if (request.body) {
        const reader = request.body.getReader();
        try {
          while (true) {
            const {done, value} = await reader.read();
            if (done) break;
            size += value.byteLength;
            if (size > 4_000_000) {
              await reader.cancel();
              return Response.json({detail:"Request exceeds the recovery limit; keep local History and start a new run"}, {status:413});
            }
            chunks.push(value);
          }
        } finally { reader.releaseLock(); }
      }
      body = Buffer.concat(chunks).toString("utf8");
    }
    const response = await fetch(url, {
      method: request.method,
      headers: {
        "Content-Type": "application/json",
        Authorization: request.headers.get("Authorization") || "",
      },
      body,
      cache: "no-store",
    });
    return new Response(response.body, {
      status: response.status,
      headers: {
        "Content-Type":
          response.headers.get("Content-Type") || "application/json",
        "Cache-Control": "no-store",
        "X-Accel-Buffering": "no",
      },
    });
  } catch {
    return Response.json(
      { detail: "Runner service unavailable" },
      { status: 503 },
    );
  }
}
export const GET = proxy;
export const POST = proxy;
