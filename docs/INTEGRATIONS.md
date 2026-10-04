# Integrations

## Prometheus Alertmanager

RootSignal accepts the standard Alertmanager webhook body at:

```text
POST /v1/integrations/alertmanager/investigate
```

Configure the receiver to send JSON with the same bearer credential used by the RootSignal API. The adapter converts the alert group into an observation-only incident, derives stable identifiers from the canonical payload, and executes the normal bounded model investigation. Exact Alertmanager retries return the original persisted run instead of invoking the model twice.

The conversion preserves labels, annotations, timestamps, generator URLs, fingerprints, receiver metadata, and any `deployment`, `version`, `revision`, or `release` label. It never creates a private oracle or includes the alert in benchmark scores. When no deployment label is present, the incident explicitly records that deployment context was unavailable.

Successful responses include the incident, diagnosis, immutable run record, and `workflow.status_url`. HTTP `503` means the alert was stored but inference was unavailable; retry the identical webhook body. HTTP `409` means the same workflow is already being processed.

Example Alertmanager receiver:

```yaml
receivers:
  - name: rootsignal
    webhook_configs:
      - url: https://rootsignal.example.com/v1/integrations/alertmanager/investigate
        http_config:
          authorization:
            type: Bearer
            credentials: ${ROOTSIGNAL_API_KEY}
```

Keep the credential in the Alertmanager secret store and outside the configuration committed to source control.
