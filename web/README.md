# RootSignal Web

The RootSignal investigation workspace is a vinext application backed by the
RootSignal API. It exposes incident investigation, knowledge ingestion, and
benchmark results through one production-oriented interface.

## Development

```bash
npm install
npm run dev
```

The web server runs at `http://localhost:3000` and proxies API requests to
`http://127.0.0.1:8000` by default. Set `INCIDENTLAB_API_URL` to point it at a
different API instance.

## Verification

```bash
npm run lint
npm test
```

`npm test` creates a production build and verifies the product identity and
primary interface copy.

## Deployment

Build the frontend with `npm run build` and deploy the generated application
with the container or platform described in the root deployment documentation.
Application secrets belong in ignored `.env*` files.
