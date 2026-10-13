export async function POST(request: Request) {
  const body = await request.json();
  if (body.mode !== "baseline" && body.mode !== "model") {
    return Response.json({ error: { message: "Execution mode must be baseline or model" } }, { status: 422 });
  }
  const apiBase = backendApiUrl();
  try {
    const endpoint = body.mode === "model"
      ? (body.stream ? "/v1/investigations/stream" : "/v1/investigations")
      : "/v1/baselines/deterministic";
    const response = await fetch(`${apiBase}${endpoint}`, {
      method: "POST",
      headers: backendHeaders(),
      body: JSON.stringify({
        incident_id: body.incident_id,
        query: body.query,
        collection_ids: body.collection_ids,
        max_steps: body.max_steps,
        max_completion_tokens: body.max_completion_tokens,
      }),
    });
    return new Response(response.body, {
      status: response.status,
      headers: { "content-type": response.headers.get("content-type") || "application/json" },
    });
  } catch {
    return Response.json({ detail: "RootSignal API unavailable" }, { status: 503 });
  }
}
import { backendHeaders } from "@/lib/api-auth";
import { backendApiUrl } from "@/lib/backend-url";
