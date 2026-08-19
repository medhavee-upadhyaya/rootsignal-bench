export async function POST(request: Request) {
  const body = await request.json();
  const apiBase = process.env.INCIDENTLAB_API_URL || "http://127.0.0.1:8000";
  try {
    const response = await fetch(`${apiBase}/v1/knowledge`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    return new Response(await response.text(), {
      status: response.status,
      headers: { "content-type": "application/json" },
    });
  } catch {
    return Response.json({ detail: "RootSignal API unavailable" }, { status: 503 });
  }
}
