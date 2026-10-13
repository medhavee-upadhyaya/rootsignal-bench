const apiBase = backendApiUrl();

export async function GET() {
  try {
    const response = await fetch(`${apiBase}/v1/knowledge/collections`, { cache: "no-store", headers: backendHeaders(false) });
    return new Response(await response.text(), {
      status: response.status,
      headers: backendHeaders(),
    });
  } catch {
    return Response.json({ detail: "RootSignal API unavailable" }, { status: 503 });
  }
}

export async function POST(request: Request) {
  const body = await request.json();
  try {
    const response = await fetch(`${apiBase}/v1/knowledge/collections`, {
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
import { backendHeaders } from "@/lib/api-auth";
import { backendApiUrl } from "@/lib/backend-url";
