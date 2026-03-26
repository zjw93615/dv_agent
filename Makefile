# DV-Agent Makefile
# Convenient commands for development and deployment

.PHONY: help install dev-setup dev-up dev-down dev-logs \
        build run stop logs clean test lint \
        prod-up prod-down prod-logs prod-build

# Default target
help:
	@echo "DV-Agent Development & Deployment Commands"
	@echo ""
	@echo "Development:"
	@echo "  make install      - Install dependencies"
	@echo "  make dev-setup    - Setup development environment"
	@echo "  make dev-up       - Start development infrastructure (Redis)"
	@echo "  make dev-up-full  - Start with Ollama and Redis Commander"
	@echo "  make dev-down     - Stop development infrastructure"
	@echo "  make dev-logs     - View development logs"
	@echo "  make run          - Run the application locally"
	@echo "  make test         - Run tests"
	@echo "  make lint         - Run linter"
	@echo ""
	@echo "Production:"
	@echo "  make prod-build   - Build production Docker image"
	@echo "  make prod-up      - Start production stack"
	@echo "  make prod-up-full - Start with monitoring"
	@echo "  make prod-down    - Stop production stack"
	@echo "  make prod-logs    - View production logs"
	@echo ""
	@echo "Utilities:"
	@echo "  make clean        - Clean up Docker resources"
	@echo "  make ollama-pull  - Pull Ollama model"

# ==================== Development ====================

# Install dependencies
install:
	pip install -r requirements.txt
	pip install -e .

# Full development setup
dev-setup: install
	@echo "Copying environment template..."
	@if not exist .env copy .env.example .env
	@echo "Development setup complete!"
	@echo "Edit .env to configure your API keys"

# Start development infrastructure (Redis only)
dev-up:
	docker compose -f docker-compose.dev.yml up -d
	@echo "Redis is running on localhost:6379"

# Start with debug tools
dev-up-debug:
	docker compose -f docker-compose.dev.yml --profile debug up -d
	@echo "Redis Commander: http://localhost:8081"

# Start with Ollama
dev-up-ollama:
	docker compose -f docker-compose.dev.yml --profile ollama up -d
	@echo "Ollama: http://localhost:11434"

# Start everything
dev-up-full:
	docker compose -f docker-compose.dev.yml --profile debug --profile ollama up -d
	@echo "All development services started"

# Stop development infrastructure
dev-down:
	docker compose -f docker-compose.dev.yml --profile debug --profile ollama down

# View development logs
dev-logs:
	docker compose -f docker-compose.dev.yml logs -f

# Run the application locally
run:
	python -m dv_agent.cli serve

# Run in debug mode
run-debug:
	python -m dv_agent.cli --debug serve

# Start interactive chat
chat:
	python -m dv_agent.cli chat

# ==================== Testing ====================

# Run all tests
test:
	pytest tests/ -v

# Run tests with coverage
test-cov:
	pytest tests/ -v --cov=dv_agent --cov-report=html --cov-report=term

# Run linter
lint:
	ruff check src/ tests/

# Fix lint issues
lint-fix:
	ruff check src/ tests/ --fix

# Type checking
typecheck:
	mypy src/

# ==================== Production ====================

# Build production Docker image
prod-build:
	docker build -t dv-agent:latest .

# Start production stack (basic)
prod-up:
	@if not exist .env.production copy .env.production.example .env.production
	docker compose up -d --build
	@echo "DV-Agent is running on http://localhost:8080"

# Start with Nginx
prod-up-nginx:
	docker compose --profile nginx up -d --build

# Start with monitoring
prod-up-monitor:
	docker compose --profile monitoring up -d --build
	@echo "Grafana: http://localhost:3000"
	@echo "Prometheus: http://localhost:9090"

# Start with Ollama
prod-up-ollama:
	docker compose --profile ollama up -d --build

# Start full production stack
prod-up-full:
	docker compose --profile nginx --profile monitoring --profile ollama up -d --build

# Stop production stack
prod-down:
	docker compose --profile nginx --profile monitoring --profile ollama down

# View production logs
prod-logs:
	docker compose logs -f

# View specific service logs
prod-logs-app:
	docker compose logs -f dv-agent

prod-logs-redis:
	docker compose logs -f redis

# ==================== Utilities ====================

# Pull Ollama model
ollama-pull:
	docker exec -it dv-agent-ollama ollama pull llama3.2

# Clean up Docker resources
clean:
	docker compose -f docker-compose.dev.yml down -v --remove-orphans
	docker compose down -v --remove-orphans
	docker system prune -f

# Remove all volumes (WARNING: deletes data)
clean-all: clean
	docker volume rm dv-agent_redis_data dv-agent_ollama_data 2>nul || true

# Health check
health:
	curl -s http://localhost:8080/health || echo "Service not running"

# Generate SSL certificates (self-signed for testing)
ssl-gen:
	@mkdir -p deploy/ssl
	openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
		-keyout deploy/ssl/key.pem \
		-out deploy/ssl/cert.pem \
		-subj "/CN=localhost"
	@echo "Self-signed certificates generated in deploy/ssl/"
