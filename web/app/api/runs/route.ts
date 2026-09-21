export async function GET(request: Request) {
  const apiBase = process.env.INCIDENTLAB_API_URL || "http://127.0.0.1:8000";
  const runId = new URL(request.url).searchParams.get("run_id");
  const cursor = new URL(request.url).searchParams.get("cursor");
  const incidentId = new URL(request.url).searchParams.get("incident_id");
  const mode = new URL(request.url).searchParams.get("mode");
  const review = new URL(request.url).searchParams.get("review");
  const params = new URLSearchParams({ limit: "20" });
  if (cursor) params.set("cursor", cursor);
  if (incidentId) params.set("incident_id", incidentId);
  if (mode) params.set("mode", mode);
  if (review) params.set("review", review);
  const endpoint = runId
    ? `/v1/runs/${encodeURIComponent(runId)}`
    : `/v1/runs?${params.toString()}`;
  try {
    const response = await fetch(`${apiBase}${endpoint}`, { cache: "no-store" });
    return new Response(await response.text(), {
      status: response.status,
      headers: { "content-type": "application/json" },
    });
  } catch {
    return Response.json({ error: { message: "RootSignal API unavailable" } }, { status: 503 });
  }
}

export async function POST(request: Request) {
  const apiBase = process.env.INCIDENTLAB_API_URL || "http://127.0.0.1:8000";
  const runId = new URL(request.url).searchParams.get("run_id");
  if (!runId) return Response.json({ error: { message: "run_id is required" } }, { status: 422 });
  try {
    const response = await fetch(`${apiBase}/v1/runs/${encodeURIComponent(runId)}/reviews`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: await request.text(),
    });
    return new Response(await response.text(), {
      status: response.status,
      headers: { "content-type": "application/json" },
    });
  } catch {
    return Response.json({ error: { message: "RootSignal API unavailable" } }, { status: 503 });
  }
}
