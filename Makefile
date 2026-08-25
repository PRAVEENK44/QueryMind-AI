# QueryMind AI - Kubernetes Development Makefile
# 
# Usage:
#   make kind-create          # Create kind cluster
#   make kind-deploy          # Deploy to kind (dev overlay)
#   make kind-deploy-staging  # Deploy to kind (staging overlay)
#   make kind-deploy-prod     # Deploy to kind (prod overlay)
#   make kind-destroy         # Destroy kind cluster
#   make port-forward         # Port forward services locally
#   make logs-backend         # View backend logs
#   make logs-streamlit       # View streamlit logs
#   make logs-postgres        # View postgres logs
#   make test-api             # Test API endpoint
#   make clean                # Clean up local artifacts

.PHONY: help kind-create kind-destroy kind-deploy kind-deploy-staging kind-deploy-prod \
        port-forward logs-backend logs-streamlit logs-postgres test-api clean

# Default target
help:
	@echo "QueryMind AI - Kubernetes Commands"
	@echo ""
	@echo "Cluster Management:"
	@echo "  make kind-create          Create local kind cluster"
	@echo "  make kind-destroy         Destroy kind cluster"
	@echo ""
	@echo "Deployment:"
	@echo "  make kind-deploy          Deploy dev overlay to kind"
	@echo "  make kind-deploy-staging  Deploy staging overlay to kind"
	@echo "  make kind-deploy-prod     Deploy prod overlay to kind"
	@echo ""
	@echo "Access:"
	@echo "  make port-forward         Port forward all services (run in background)"
	@echo "  make test-api             Test API health endpoint"
	@echo ""
	@echo "Logs:"
	@echo "  make logs-backend         View backend logs"
	@echo "  make logs-streamlit       View streamlit logs"
	@echo "  make logs-postgres        View postgres logs"
	@echo ""
	@echo "Utilities:"
	@echo "  make clean                Clean up local artifacts"

# =============================================================================
# Cluster Management
# =============================================================================

KIND_CLUSTER_NAME := querymind
KIND_CONFIG := k8s/kind-config.yaml

kind-create: $(KIND_CONFIG)
	@echo "Creating kind cluster '$(KIND_CLUSTER_NAME)'..."
	@kind create cluster --name $(KIND_CLUSTER_NAME) --config $(KIND_CONFIG) || true
	@echo "Waiting for cluster to be ready..."
	@kubectl wait --for=condition=Ready nodes --all --timeout=60s
	@echo "Installing NGINX Ingress Controller..."
	@kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml
	@kubectl wait --namespace ingress-nginx --for=condition=Ready pod --selector=app.kubernetes.io/component=controller --timeout=120s
	@echo "Cluster ready!"

$(KIND_CONFIG):
	@echo "Creating kind config..."
	@mkdir -p k8s
	@cat > $(KIND_CONFIG) <<'EOF'
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
name: querymind
nodes:
  - role: control-plane
    kubeadmConfigPatches:
      - |
        kind: InitConfiguration
        nodeRegistration:
          kubeletExtraArgs:
            node-labels: "ingress-ready=true"
    extraPortMappings:
      - containerPort: 80
        hostPort: 80
        protocol: TCP
      - containerPort: 443
        hostPort: 443
        protocol: TCP
      - containerPort: 30080
        hostPort: 30080
        protocol: TCP
      - containerPort: 30443
        hostPort: 30443
        protocol: TCP
EOF

kind-destroy:
	@echo "Destroying kind cluster '$(KIND_CLUSTER_NAME)'..."
	@kind delete cluster --name $(KIND_CLUSTER_NAME)

# =============================================================================
# Deployment
# =============================================================================

kind-deploy:
	@echo "Deploying dev overlay to kind..."
	@kubectl config set-context --current --namespace=querymind-dev
	@kustomize build k8s/overlays/dev | kubectl apply -f -
	@echo "Waiting for deployments to be ready..."
	@kubectl wait --namespace=querymind-dev --for=condition=Available deployment --all --timeout=300s
	@kubectl wait --namespace=querymind-dev --for=condition=Ready pod --selector=app.kubernetes.io/component=postgres --timeout=120s
	@echo "Dev deployment complete!"
	@make test-api

kind-deploy-staging:
	@echo "Deploying staging overlay to kind..."
	@kubectl config set-context --current --namespace=querymind-staging
	@kustomize build k8s/overlays/staging | kubectl apply -f -
	@echo "Waiting for deployments to be ready..."
	@kubectl wait --namespace=querymind-staging --for=condition=Available deployment --all --timeout=300s
	@kubectl wait --namespace=querymind-staging --for=condition=Ready pod --selector=app.kubernetes.io/component=postgres --timeout=120s
	@echo "Staging deployment complete!"
	@make test-api

kind-deploy-prod:
	@echo "Deploying prod overlay to kind..."
	@kubectl config set-context --current --namespace=querymind
	@kustomize build k8s/overlays/prod | kubectl apply -f -
	@echo "Waiting for deployments to be ready..."
	@kubectl wait --namespace=querymind --for=condition=Available deployment --all --timeout=300s
	@kubectl wait --namespace=querymind --for=condition=Ready pod --selector=app.kubernetes.io/component=postgres --timeout=120s
	@echo "Prod deployment complete!"
	@make test-api

# =============================================================================
# Port Forwarding
# =============================================================================

# Port forward all services (run in background)
port-forward:
	@echo "Starting port forwards..."
	@echo "Backend: http://localhost:8000"
	@echo "Streamlit: http://localhost:8501"
	@echo "PostgreSQL: localhost:5432"
	@echo "Redis: localhost:6379"
	@echo ""
	@echo "Press Ctrl+C to stop all port forwards"
	@kubectl port-forward --namespace=querymind-dev svc/querymind-backend 8000:8000 & \
	kubectl port-forward --namespace=querymind-dev svc/querymind-streamlit 8501:8501 & \
	kubectl port-forward --namespace=querymind-dev svc/querymind-postgres 5432:5432 & \
	kubectl port-forward --namespace=querymind-dev svc/querymind-redis 6379:6379 & \
	wait

# Port forward specific services
port-forward-backend:
	@kubectl port-forward --namespace=querymind-dev svc/querymind-backend 8000:8000

port-forward-streamlit:
	@kubectl port-forward --namespace=querymind-dev svc/querymind-streamlit 8501:8501

port-forward-postgres:
	@kubectl port-forward --namespace=querymind-dev svc/querymind-postgres 5432:5432

port-forward-redis:
	@kubectl port-forward --namespace=querymind-dev svc/querymind-redis 6379:6379

# =============================================================================
# Logs
# =============================================================================

logs-backend:
	@kubectl logs --namespace=querymind-dev -l app.kubernetes.io/component=backend -f --tail=100

logs-streamlit:
	@kubectl logs --namespace=querymind-dev -l app.kubernetes.io/component=streamlit -f --tail=100

logs-postgres:
	@kubectl logs --namespace=querymind-dev -l app.kubernetes.io/component=postgres -f --tail=100

logs-redis:
	@kubectl logs --namespace=querymind-dev -l app.kubernetes.io/component=redis -f --tail=100

logs-all:
	@kubectl logs --namespace=querymind-dev -l app.kubernetes.io/name=querymind -f --tail=50

# =============================================================================
# Testing
# =============================================================================

test-api:
	@echo "Testing API health endpoint..."
	@sleep 5
	@curl -f http://localhost:8000/health || (echo "API not ready, waiting..." && sleep 10 && curl -f http://localhost:8000/health)
	@echo "API health check passed!"

test-query:
	@echo "Testing query endpoint..."
	@curl -X POST http://localhost:8000/api/query \
	  -H "Content-Type: application/json" \
	  -d '{"query": "Total budget across all departments"}' | jq .

# =============================================================================
# Utilities
# =============================================================================

# Get pod status
status:
	@kubectl get pods --namespace=querymind-dev -o wide
	@kubectl get svc --namespace=querymind-dev
	@kubectl get ingress --namespace=querymind-dev

# Describe resources for debugging
describe-backend:
	@kubectl describe deployment --namespace=querymind-dev querymind-backend

describe-postgres:
	@kubectl describe statefulset --namespace=querymind-dev querymind-postgres

# Execute commands in pods
exec-backend:
	@kubectl exec --namespace=querymind-dev -it deployment/querymind-backend -- /bin/sh

exec-postgres:
	@kubectl exec --namespace=querymind-dev -it statefulset/querymind-postgres -- psql -U $$POSTGRES_USER -d querymind

# Clean up local artifacts
clean:
	@rm -rf k8s/kind-config.yaml
	@docker system prune -f

# Build and load images into kind
build-and-load:
	@echo "Building Docker images..."
	@docker build -t querymind-ai:latest .
	@docker build -t querymind-postgres:latest -f Dockerfile.postgres .
	@echo "Loading images into kind..."
	@kind load docker-image querymind-ai:latest --name $(KIND_CLUSTER_NAME)
	@kind load docker-image querymind-postgres:latest --name $(KIND_CLUSTER_NAME)
	@echo "Images loaded!"

# Full deploy from scratch
full-deploy: kind-create build-and-load kind-deploy
	@echo "Full deployment complete!"

# Quick redeploy (rebuild images and redeploy)
redeploy: build-and-load
	@kustomize build k8s/overlays/dev | kubectl apply -f -
	@kubectl rollout restart deployment/querymind-backend --namespace=querymind-dev
	@kubectl rollout restart deployment/querymind-streamlit --namespace=querymind-dev
	@echo "Redeploy complete!"

# Validate kustomize builds
validate:
	@echo "Validating dev overlay..."
	@kustomize build k8s/overlays/dev > /dev/null && echo "✓ dev valid"
	@echo "Validating staging overlay..."
	@kustomize build k8s/overlays/staging > /dev/null && echo "✓ staging valid"
	@echo "Validating prod overlay..."
	@kustomize build k8s/overlays/prod > /dev/null && echo "✓ prod valid"

# Show diff before apply
diff:
	@kustomize build k8s/overlays/dev | kubectl diff -f -