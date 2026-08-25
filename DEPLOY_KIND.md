# QueryMind AI — Kind Deployment Guide

This guide deploys QueryMind AI to a local `kind` cluster for portfolio demonstration.

## Prerequisites

- Docker Desktop (Windows/Mac) or Docker Engine (Linux)
- `kind` — `go install sigs.k8s.io/kind@latest` or `brew install kind` / `choco install kind`
- `kubectl` — `winget install Kubernetes.kubectl` / `brew install kubectl` / `apt install kubectl`
- `kustomize` — built into `kubectl` (`kubectl kustomize`)

## Quick Start

```bash
# 1. Create kind cluster with port mappings
kind create cluster --config kind-config.yaml

# 2. Build and load Docker images into kind
docker build -t querymind-ai:latest .
docker build -t querymind-postgres:latest -f Dockerfile.postgres .
kind load docker-image querymind-ai:latest --name querymind
kind load docker-image querymind-postgres:latest --name querymind

# 3. Apply Kustomize manifests (dev overlay)
kubectl kustomize k8s/overlays/dev | kubectl apply -f -

# 4. Wait for pods to be ready
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=querymind -n querymind --timeout=300s

# 5. Port-forward services for local access
kubectl port-forward -n querymind svc/querymind-backend 8000:8000 &
kubectl port-forward -n querymind svc/querymind-streamlit 8501:8501 &
kubectl port-forward -n querymind svc/querymind-prometheus 9090:9090 &
kubectl port-forward -n querymind svc/querymind-grafana 3000:3000 &
```

## Access URLs

| Service | Local URL |
|---------|-----------|
| Backend API | http://localhost:8000 |
| API Health | http://localhost:8000/health |
| API Metrics | http://localhost:8000/metrics |
| Streamlit UI | http://localhost:8501 |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3000 (admin / `grafana_admin_password.txt`) |
| Alertmanager | http://localhost:9093 |
| Pushgateway | http://localhost:9091 |

## Verify Deployment

```bash
# Check API health
curl http://localhost:8000/health

# Run a test query
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Total budget across all departments"}'

# Check Prometheus targets
curl http://localhost:9090/api/v1/targets

# Check Grafana dashboards
open http://localhost:3000
```

## Run Eval Harness in Cluster

```bash
# Create a job to run eval harness
kubectl create job --from=cronjob/querymind-eval eval-run-$(date +%s) -n querymind
# Or run manually in a pod:
kubectl run eval-runner --rm -it --image=querymind-ai:latest -n querymind -- \
  python -m evals.harness --baseline compare
```

## Secrets Setup

Before deploying, update secrets in `k8s/overlays/dev/secret-patch.yaml` or create manually:

```bash
kubectl create secret generic querymind-secrets -n querymind \
  --from-literal=POSTGRES_USER=querymind_ro_user \
  --from-literal=POSTGRES_PASSWORD=your_readonly_password \
  --from-literal=POSTGRES_RW_USER=querymind_rw_user \
  --from-literal=POSTGRES_RW_PASSWORD=your_readwrite_password \
  --from-literal=OPENAI_API_KEY=your_openai_key \
  --from-literal=GEMINI_API_KEY=your_gemini_key \
  --from-literal=REDIS_PASSWORD=your_redis_password \
  --dry-run=client -o yaml | kubectl apply -f -
```

## Grafana Password

The default Grafana admin password is in `secrets/grafana_admin_password.txt`. Change it:

```bash
# Generate new password
openssl rand -base64 16 > secrets/grafana_admin_password.txt

# Update secret
kubectl create secret generic grafana-admin-password \
  --from-file=secrets/grafana_admin_password.txt \
  -n querymind --dry-run=client -o yaml | kubectl apply -f -
```

## Troubleshooting

### Pods stuck in Pending
```bash
kubectl describe pod -n querymind -l app.kubernetes.io/name=querymind
# Check events for PVC binding issues, resource constraints
```

### Database connection failed
```bash
kubectl logs -n querymind -l app.kubernetes.io/component=postgres
# Verify postgres-init-script ConfigMap applied
```

### Images not found
```bash
# Rebuild and reload
docker build -t querymind-ai:latest .
kind load docker-image querymind-ai:latest --name querymind
```

### Port conflicts
If host ports are in use, edit `kind-config.yaml` to use different hostPort values.

## Cleanup

```bash
kind delete cluster --name querymind
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      kind Cluster                           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │  Backend    │  │  Streamlit  │  │  PostgreSQL         │  │
│  │  (x2)       │  │  (x1)       │  │  (StatefulSet)      │  │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘  │
│         │              │                      │             │
│         └──────────────┼──────────────────────┘             │
│                        ▼                                    │
│              ┌─────────────────┐                            │
│              │   Prometheus    │                            │
│              │   (metrics)     │                            │
│              └────────┬────────┘                            │
│                       ▼                                     │
│              ┌─────────────────┐                            │
│              │    Grafana      │                            │
│              │  (dashboards)   │                            │
│              └─────────────────┘                            │
└─────────────────────────────────────────────────────────────┘
```

All services exposed via hostPort mappings for direct localhost access.