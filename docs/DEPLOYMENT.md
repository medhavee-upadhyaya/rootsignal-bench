# Deployment

## Local full stack

Run an OpenAI-compatible model server on the host, then start both the API and web application:

```bash
docker compose up --build
```

The application is available at `http://localhost:3000`, the API at `http://localhost:8000`, and metrics at `http://localhost:8000/metrics`. Set `INCIDENTLAB_LLM_URL` and `INCIDENTLAB_MODEL` to override the default host model endpoint. Knowledge data persists in the named `rootsignal-data` volume.

The built-in and custom incidents, experiment history, and scoped knowledge collections share the persistent SQLite volume. Back up the volume before destructive infrastructure changes. The deterministic control remains usable when the model endpoint is offline; independent model runs require the configured endpoint.

### Deploy below an existing domain path

Set `ROOTSIGNAL_BASE_PATH` at web-image build time when a reverse proxy exposes the application below a prefix:

```bash
ROOTSIGNAL_BASE_PATH=/project/rootsignalbench docker compose build web
ROOTSIGNAL_BASE_PATH=/project/rootsignalbench docker compose up
```

The build prefixes browser API calls, evidence downloads, metadata images, framework assets, and the web health check while leaving backend `/v1` routes unchanged. The value is compiled into the browser bundle, so changing only the running container environment is insufficient; rebuild the web image whenever the prefix changes. Leave it empty for root and localhost deployments.

Before exposing RootSignal beyond localhost, set `ROOTSIGNAL_API_KEYS` on the API to one or more comma-separated, secret-manager-supplied values of at least 16 characters. All mutations and sensitive reads then require `Authorization: Bearer <key>`, including incident data, run history, evidence exports, knowledge metadata, and metrics. Only health, readiness, system capability, and the published benchmark summary remain public. Set `ROOTSIGNAL_API_KEY` on the web service to one of those values so the server-side web proxy can authenticate without exposing the key to browser JavaScript. Leave both variables empty only for trusted local development.

For a hosted OpenAI-compatible model endpoint, store its bearer credential as `INCIDENTLAB_LLM_API_KEY` on the API service. It is sent only to the configured model origin for `GET /v1/models` and `POST /v1/chat/completions`. Do not set it on the web container or expose it through a public-prefixed environment variable.

Both containers run as UID 10001 with all Linux capabilities dropped, a read-only root filesystem, `no-new-privileges`, bounded temporary storage, and health checks. Only `/data` is writable for the API.

## Single-host production topology

`deploy/production.compose.yaml` is the production boundary for a container host or a platform that accepts Compose services. It publishes only the web container on loopback, keeps the API on an internal network, persists `/data`, bounds CPU, memory, processes, temporary storage, and logs, and fails configuration when the application key or model identity is missing.

Prepare the ignored environment file and validate interpolation before starting anything:

```bash
cp .env.example .env.production
openssl rand -hex 32
# Put the generated value and model settings into .env.production.
docker compose --env-file .env.production -f deploy/production.compose.yaml config --quiet
docker compose --env-file .env.production -f deploy/production.compose.yaml up -d --build
```

Do not publish port `8000`. Terminate TLS at the hosting ingress or reverse proxy and forward the public RootSignal path only to the loopback web port. The web container is the credential-holding backend-for-frontend; browsers should never call the Python API or model provider directly.

The named `rootsignal-data` volume contains custom incidents, knowledge collections, job state, reviews, and run history. Configure host-level encrypted volume backups before accepting user data. A container restart is safe; deleting or recreating the volume is destructive.

## Render Blueprint

`render.yaml` defines a deployable two-service topology: `rootsignal-web` is the only public service, while `rootsignal-api` is reachable only through Render's private network. The web service discovers the API from platform-provided host and port properties. Render generates the RootSignal application credential and copies it to the web service without committing it to Git. Model endpoint values are entered in the Render dashboard during Blueprint creation.

Both services use the smallest paid 512 MB compute plan. The API also uses a 1 GB persistent disk mounted at `/data`; Render requires paid compute for persistent disks and bills storage separately. Review the estimate shown by Render before approving Blueprint creation. Creating the Blueprint is the cost-bearing action; committing this file is not.

To deploy:

1. In Render, create a new Blueprint from this repository and keep the Blueprint path as `render.yaml`.
2. Enter `INCIDENTLAB_LLM_URL`, `INCIDENTLAB_MODEL`, and, when required, `INCIDENTLAB_LLM_API_KEY`. Never put those values in Git.
3. Review the displayed monthly estimate, then approve creation only if the cost is acceptable.
4. Wait for both service health checks to pass. The public Render URL ends with `/project/rootsignalbench/`.
5. Run one control investigation, one model investigation, reload the saved run, and export its evidence before configuring portfolio routing.

The Blueprint deploys only after GitHub checks pass. The API disk is encrypted and receives daily platform snapshots, but it restricts the API to one instance and causes brief downtime during API deploys. Export important experiment evidence independently; a platform snapshot is not a substitute for an application-level backup.

Do not attach `medhaveeupadhyaya.com` directly to the RootSignal service while the portfolio already owns that domain. After the Render URL is verified, configure the portfolio host to proxy `/project/rootsignalbench` and all nested paths to the Render web service. That routing change is a separate deployment step.

## Kubernetes

Create the required application secret before applying the manifest. Add `llm-api-key` only when the configured model endpoint requires authentication:

```bash
kubectl create secret generic rootsignal-secrets \
  --from-literal=api-key='<generate-a-random-value>' \
  --from-literal=llm-api-key='<provider-value>'
```

Edit the model endpoint and immutable image versions in `deploy/kubernetes.yaml`, then apply it:

```bash
kubectl apply -f deploy/kubernetes.yaml
kubectl rollout status deployment/rootsignal-api
kubectl rollout status deployment/rootsignal-web
```

The manifest includes startup, readiness, and liveness probes; zero-unavailable rolling updates; resource requests and limits; a disruption budget; horizontal autoscaling; persistent knowledge storage; Prometheus discovery annotations; and restricted pod security contexts. The model server is deliberately external because GPU topology and serving configuration are environment-specific.

For multiple API replicas, replace the default `ReadWriteOnce` SQLite volume with an appropriate shared retrieval service or a storage class whose consistency guarantees match the workload. Do not scale writers across an unsafe shared filesystem.

## Release images

Pushing a version tag such as `v0.2.0` builds multi-architecture API and web images in GitHub Actions. Images receive semantic-version and Git-SHA tags plus SBOM and build-provenance attestations. Kubernetes uses immutable version tags instead of `latest`; production operators should pin the resulting image digest for strict reproducibility.

No credential belongs in the manifest or image. Supply RootSignal API keys and any remote-model credentials through the platform secret manager at deployment time.

## Release verification

After the tag workflow succeeds, verify both GHCR packages contain the semantic-version and Git-SHA tags, SBOM attestation, and provenance attestation. Deploy an immutable digest rather than a mutable tag. A successful image build alone does not prove the model endpoint, persistent volume, or ingress configuration works in the target cluster; run health, readiness, one control investigation, one model investigation, and an evidence export after deployment.
