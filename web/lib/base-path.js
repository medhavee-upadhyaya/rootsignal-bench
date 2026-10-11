function normalizeBasePath(value = "") {
  const trimmed = value.trim();
  if (!trimmed || trimmed === "/") return "";
  return `/${trimmed.replace(/^\/+|\/+$/g, "")}`;
}

export const ROOTSIGNAL_BASE_PATH = normalizeBasePath(
  process.env.NEXT_PUBLIC_ROOTSIGNAL_BASE_PATH || "",
);

export function appPath(path) {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${ROOTSIGNAL_BASE_PATH}${normalizedPath}`;
}

export { normalizeBasePath };
