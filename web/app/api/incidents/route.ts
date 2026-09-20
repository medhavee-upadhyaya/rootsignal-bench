export async function GET(request: Request) {
  const apiBase = process.env.INCIDENTLAB_API_URL || "http://127.0.0.1:8000";
  const incidentId = new URL(request.url).searchParams.get("incident_id");
  const endpoint = incidentId
    ? `/v1/incidents/${encodeURIComponent(incidentId)}`
    : "/v1/incidents";
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
  try {
    const response = await fetch(`${apiBase}/v1/incidents`, {
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

export async function DELETE(request: Request) {
  const incidentId = new URL(request.url).searchParams.get("incident_id");
  if (!incidentId) return Response.json({ error: { message: "incident_id is required" } }, { status: 422 });
  const apiBase = process.env.INCIDENTLAB_API_URL || "http://127.0.0.1:8000";
  try {
    const response = await fetch(`${apiBase}/v1/incidents/${encodeURIComponent(incidentId)}`, {
      method: "DELETE",
    });
    return new Response(await response.text(), {
      status: response.status,
      headers: { "content-type": "application/json" },
    });
  } catch {
    return Response.json({ error: { message: "RootSignal API unavailable" } }, { status: 503 });
  }
}
