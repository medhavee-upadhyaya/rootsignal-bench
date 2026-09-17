const MAX_TELEMETRY_FILE_BYTES = 1_000_000;

function object(value, label) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} must be a JSON object`);
  }
  return value;
}

function rows(value, label, minimum) {
  if (!Array.isArray(value) || value.length < minimum) {
    throw new Error(`${label} must contain at least ${minimum} item${minimum === 1 ? "" : "s"}`);
  }
  return value.map((item) => typeof item === "string" ? item : JSON.stringify(item));
}

export function parseTelemetryBundle(text) {
  if (new TextEncoder().encode(text).length > MAX_TELEMETRY_FILE_BYTES) {
    throw new Error("Telemetry bundle must not exceed 1 MB");
  }
  let payload;
  try {
    payload = object(JSON.parse(text), "Telemetry bundle");
  } catch (error) {
    if (error instanceof SyntaxError) throw new Error("Telemetry bundle must be valid JSON");
    throw error;
  }
  const telemetry = object(payload.telemetry ?? payload, "Telemetry");
  const metrics = object(telemetry.metrics, "Metrics");
  if (!Object.keys(metrics).length) throw new Error("Metrics must contain at least one signal");
  const logs = rows(telemetry.logs, "Logs", 2);
  const deployments = rows(telemetry.deployments, "Deployments", 1);
  const metricLines = Object.entries(metrics).map(([name, value]) =>
    `${name}=${typeof value === "string" ? value : JSON.stringify(value)}`
  );
  const runbooks = Array.isArray(payload.runbooks) ? payload.runbooks : [];
  const firstRunbook = runbooks.find((item) => item && typeof item === "object");
  return {
    id: typeof payload.id === "string" ? payload.id : "",
    title: typeof payload.title === "string" ? payload.title : "",
    summary: typeof payload.summary === "string" ? payload.summary : "",
    metrics: metricLines.join("\n"),
    logs: logs.join("\n"),
    deployments: deployments.join("\n"),
    runbook: firstRunbook && typeof firstRunbook.content === "string" ? firstRunbook.content : "",
    counts: { metrics: metricLines.length, logs: logs.length, deployments: deployments.length },
  };
}

export { MAX_TELEMETRY_FILE_BYTES };
