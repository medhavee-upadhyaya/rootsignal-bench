# Integrations

## Prometheus Alertmanager

RootSignal accepts the standard Alertmanager webhook body at:

```text
POST /v1/integrations/alertmanager
```

The endpoint returns HTTP `202` with a durable job and `status_url`, then runs the investigation after acknowledging the webhook. Configure the receiver to send JSON with the same bearer credential used by the RootSignal API. The adapter converts the alert group into an observation-only incident, derives stable identifiers from the canonical payload, and executes the normal bounded model investigation. Exact Alertmanager retries resolve to the same job and persisted run instead of invoking the model twice. The normalized request is retained with the job, so interrupted work can resume without resending alert data.

The conversion preserves labels, annotations, timestamps, generator URLs, fingerprints, receiver metadata, and any `deployment`, `version`, `revision`, or `release` label. It never creates a private oracle or includes the alert in benchmark scores. When no deployment label is present, the incident explicitly records that deployment context was unavailable.

Poll `GET /v1/integration-jobs/{job_id}` until the job is `completed` or `failed`. Completed jobs include the immutable `run_id`; status reads never execute inference. After an application interruption, use `POST /v1/integration-jobs/{job_id}/resume` for queued or lease-expired work. Retry a failed inference explicitly with `POST /v1/integration-jobs/{job_id}/retry`. Scripts that intentionally want to wait for the full diagnosis may use `POST /v1/integrations/alertmanager/investigate` instead.

Example Alertmanager receiver:

```yaml
receivers:
  - name: rootsignal
    webhook_configs:
      - url: https://rootsignal.example.com/v1/integrations/alertmanager
        http_config:
          authorization:
            type: Bearer
            credentials: ${ROOTSIGNAL_API_KEY}
```

Keep the credential in the Alertmanager secret store and outside the configuration committed to source control.
