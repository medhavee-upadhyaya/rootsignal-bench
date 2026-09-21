export async function POST(request: Request) {
  const body = await request.json();
  const apiBase = process.env.INCIDENTLAB_API_URL || "http://127.0.0.1:8000";
  try {
    const latest = body.selection === "latest_model_run_per_incident";
    const response = await fetch(`${apiBase}/v1/evaluation-suites${latest ? "/latest" : ""}`, {
      method: latest ? "GET" : "POST",
      headers: { "content-type": "application/json" },
      body: latest ? undefined : JSON.stringify(body),
    });
    return new Response(await response.text(), {
      status: response.status,
      headers: { "content-type": "application/json" },
    });
  } catch {
    return Response.json({ error: { message: "RootSignal API unavailable" } }, { status: 503 });
  }
}
