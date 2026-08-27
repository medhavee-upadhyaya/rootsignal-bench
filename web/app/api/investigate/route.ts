export async function POST(request: Request) {
  const body = await request.json();
  if (body.mode !== "baseline" && body.mode !== "model") {
    return Response.json({ error: { message: "Execution mode must be baseline or model" } }, { status: 422 });
  }
  const apiBase = process.env.INCIDENTLAB_API_URL || "http://127.0.0.1:8000";
  try {
    const endpoint = body.mode === "model" ? "/v1/investigations" : "/v1/baselines/deterministic";
    const response = await fetch(`${apiBase}${endpoint}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ incident_id: body.incident_id, query: body.query }),
    });
    return new Response(await response.text(), {
      status: response.status,
      headers: { "content-type": "application/json" },
    });
  } catch {
    return Response.json({ detail: "RootSignal API unavailable" }, { status: 503 });
  }
}
