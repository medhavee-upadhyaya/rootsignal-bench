export function backendHeaders(contentType = true): Record<string, string> {
  const headers: Record<string, string> = {};
  if (contentType) headers["content-type"] = "application/json";
  const key = process.env.ROOTSIGNAL_API_KEY;
  if (key) headers.authorization = `Bearer ${key}`;
  return headers;
}
