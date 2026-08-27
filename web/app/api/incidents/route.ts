export async function GET() {
  const apiBase = process.env.INCIDENTLAB_API_URL || "http://127.0.0.1:8000";
  try {
    const response = await fetch(`${apiBase}/v1/incidents`, { cache: "no-store" });
    return new Response(await response.text(), {
      status: response.status,
      headers: { "content-type": "application/json" },
    });
  } catch {
    return Response.json({ error: { message: "RootSignal API unavailable" } }, { status: 503 });
  }
}
