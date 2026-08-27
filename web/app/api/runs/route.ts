export async function GET(request: Request) {
  const apiBase = process.env.INCIDENTLAB_API_URL || "http://127.0.0.1:8000";
  const runId = new URL(request.url).searchParams.get("run_id");
  const endpoint = runId ? `/v1/runs/${encodeURIComponent(runId)}` : "/v1/runs?limit=20";
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
