import type { NextConfig } from "next";

const configuredPath = process.env.ROOTSIGNAL_BASE_PATH?.trim() || "";
const basePath = configuredPath && configuredPath !== "/"
  ? `/${configuredPath.replace(/^\/+|\/+$/g, "")}`
  : "";

const nextConfig: NextConfig = {
  basePath,
  env: {
    NEXT_PUBLIC_ROOTSIGNAL_BASE_PATH: basePath,
  },
};

export default nextConfig;
