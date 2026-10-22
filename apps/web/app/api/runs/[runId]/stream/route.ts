import { NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(
  req: NextRequest,
  context: { params: Promise<{ runId: string }> }
) {
  const { runId } = await context.params;

  if (!runId) {
    return new Response(JSON.stringify({ error: "Missing runId" }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    });
  }

  const backendUrl = process.env.BACKEND_URL || "http://localhost:8000";
  const upstreamUrl = `${backendUrl}/api/v1/runs/${encodeURIComponent(
    runId
  )}/stream`;

  const headers = new Headers();
  headers.set("Accept", "text/event-stream");
  headers.set("Cache-Control", "no-cache");

  // Forward cookie for auth
  const cookie = req.headers.get("cookie");
  if (cookie) {
    headers.set("cookie", cookie);
  }

  // Forward Last-Event-ID for resuming stream
  const lastEventId = req.headers.get("last-event-id");
  if (lastEventId) {
    headers.set("last-event-id", lastEventId);
  }

  try {
    const upstreamRes = await fetch(upstreamUrl, {
      method: "GET",
      headers,
      cache: "no-store",
    });

    if (!upstreamRes.ok || !upstreamRes.body) {
      return new Response(
        JSON.stringify({
          error: "Upstream SSE connection failed",
          status: upstreamRes.status,
          statusText: upstreamRes.statusText,
        }),
        {
          status: upstreamRes.status || 502,
          headers: { "Content-Type": "application/json" },
        }
      );
    }

    return new Response(upstreamRes.body, {
      status: 200,
      headers: {
        "Content-Type": "text/event-stream; charset=utf-8",
        "Cache-Control": "no-cache, no-transform",
        Connection: "keep-alive",
        "X-Accel-Buffering": "no",
      },
    });
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return new Response(
      JSON.stringify({ error: "Failed to connect to upstream SSE", message }),
      {
        status: 502,
        headers: { "Content-Type": "application/json" },
      }
    );
  }
}
