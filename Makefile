CLUSTER ?= pulse
IMAGES  := pulse-ingestor pulse-processor pulse-api pulse-ui

.PHONY: up down logs build k8s-up k8s-down k8s-validate k8s-status

## Local (docker compose)
up: ## Start the whole stack locally
	docker compose up -d --build

down: ## Stop the local stack
	docker compose down

logs:
	docker compose logs -f --tail=100

build: ## Build all service images
	docker compose build $(IMAGES:pulse-%=%)

## Kubernetes (k3d)
k8s-up: ## Create a k3d cluster, build+import images, deploy
	k3d cluster create $(CLUSTER) --agents 1 -p "8081:80@loadbalancer" 2>/dev/null || true
	docker compose build $(IMAGES:pulse-%=%)
	k3d image import -c $(CLUSTER) $(addsuffix :latest,$(IMAGES))
	kubectl apply -k deploy/k8s
	kubectl -n pulse rollout status deploy/api --timeout=180s
	@echo "Dashboard: http://pulse.localhost:8081  (add '127.0.0.1 pulse.localhost' to /etc/hosts)"

k8s-down: ## Delete the k3d cluster
	k3d cluster delete $(CLUSTER)

k8s-status: ## Show pods/services
	kubectl -n pulse get pods,svc

k8s-validate: ## Render + client-validate manifests (no cluster needed)
	kubectl kustomize deploy/k8s > /dev/null && echo "kustomize: ok"
