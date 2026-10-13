export async function POST(request: Request) {
  const body = await request.json();
  const apiBase = backendApiUrl();
  try {
    const response = await fetch(`${apiBase}/v1/knowledge`, {
      method: "POST",
      headers: backendHeaders(),
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
