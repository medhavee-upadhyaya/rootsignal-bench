export const MAX_TELEMETRY_FILE_BYTES: number;
export function parseTelemetryBundle(text: string): {
  id: string;
  title: string;
  summary: string;
  metrics: string;
  logs: string;
  deployments: string;
  runbook: string;
  counts: { metrics: number; logs: number; deployments: number };
};
