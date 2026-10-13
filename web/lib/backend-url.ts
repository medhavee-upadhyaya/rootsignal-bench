const DEFAULT_BACKEND_URL = "http://127.0.0.1:8000";

export function backendApiUrl(): string {
  const explicitUrl = process.env.INCIDENTLAB_API_URL?.trim();
  if (explicitUrl) return explicitUrl.replace(/\/$/, "");

  const host = process.env.INCIDENTLAB_API_HOST?.trim();
  if (!host) return DEFAULT_BACKEND_URL;

  const port = process.env.INCIDENTLAB_API_PORT?.trim();
  return `http://${host}${port ? `:${port}` : ""}`;
}
