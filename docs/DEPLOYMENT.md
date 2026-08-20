# Deployment

## Local full stack

Run an OpenAI-compatible model server on the host, then start both the API and web application:

```bash
docker compose up --build
```

The application is available at `http://localhost:3000`, the API at `http://localhost:8000`, and metrics at `http://localhost:8000/metrics`. Set `INCIDENTLAB_LLM_URL` and `INCIDENTLAB_MODEL` to override the default host model endpoint. Knowledge data persists in the named `rootsignal-data` volume.

Both containers run as UID 10001 with all Linux capabilities dropped, a read-only root filesystem, `no-new-privileges`, bounded temporary storage, and health checks. Only `/data` is writable for the API.

## Kubernetes

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

No credential belongs in the manifest or image. Supply credentials, if a remote model endpoint requires them, through the platform secret manager at deployment time.
