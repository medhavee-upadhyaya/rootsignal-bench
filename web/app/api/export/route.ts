export async function GET(request: Request) {
  const search = new URL(request.url).searchParams;
  const runId = search.get("run_id");
  const compareTo = search.get("compare_to");
  if (!runId || !/^[a-f0-9]{32}$/.test(runId)) {
    return Response.json({ error: { message: "A valid run id is required" } }, { status: 422 });
  }
  if (compareTo && !/^[a-f0-9]{32}$/.test(compareTo)) {
    return Response.json({ error: { message: "A valid comparison run id is required" } }, { status: 422 });
  }
  const apiBase = process.env.INCIDENTLAB_API_URL || "http://127.0.0.1:8000";
  const comparison = compareTo ? `?compare_to=${encodeURIComponent(compareTo)}` : "";
  try {
    const response = await fetch(
      `${apiBase}/v1/runs/${encodeURIComponent(runId)}/export${comparison}`,
      { cache: "no-store" },
    );
    return new Response(await response.arrayBuffer(), {
      status: response.status,
      headers: {
        "content-type": response.headers.get("content-type") || "application/json",
        "content-disposition": response.headers.get("content-disposition") || "attachment",
      },
    });
  } catch {
    return Response.json({ error: { message: "RootSignal API unavailable" } }, { status: 503 });
  }
}
