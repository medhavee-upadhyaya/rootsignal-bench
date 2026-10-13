import { backendApiUrl } from "@/lib/backend-url";

export async function GET() {
  const apiBase = backendApiUrl();
  try {
    const response = await fetch(`${apiBase}/v1/system`, { cache: "no-store" });
    return new Response(await response.text(), {
      status: response.status,
      headers: { "content-type": "application/json" },
    });
  } catch {
    return Response.json({ error: { message: "RootSignal API unavailable" } }, { status: 503 });
  }
}
