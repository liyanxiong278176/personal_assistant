#!/bin/bash
# Travel Assistant - Cloud Deployment Script
# Usage: ./deployment/deploy.sh [environment]
# Environment: production (default), staging

set -e  # Exit on error

# ============================================
# Configuration
# ============================================
ENVIRONMENT="${1:-production}"

# Load environment variables
if [ -f ".env.${ENVIRONMENT}" ]; then
    set -a
    source ".env.${ENVIRONMENT}"
    set +a
else
    echo "Error: .env.${ENVIRONMENT} not found"
    echo "Create .env.${ENVIRONMENT} from .env.production.example"
    exit 1
fi

# Validate required variables
required_vars=("SERVER_HOST" "SSH_USER" "SSH_KEY_PATH")
for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        echo "Error: Required variable $var is not set"
        exit 1
    fi
done

# ============================================
# Colors for output
# ============================================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# ============================================
# Functions
# ============================================

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# ============================================
# Pre-flight Checks
# ============================================
log_info "Running pre-flight checks..."

# Check SSH key exists
if [ ! -f "$SSH_KEY_PATH" ]; then
    log_error "SSH key not found at $SSH_KEY_PATH"
    exit 1
fi

# Check SSH connectivity
log_info "Testing SSH connection to $SSH_USER@$SERVER_HOST..."
if ! ssh -i "$SSH_KEY_PATH" -o ConnectTimeout=10 -o StrictHostKeyChecking=no "$SSH_USER@$SERVER_HOST" "echo 'SSH connection successful'" > /dev/null 2>&1; then
    log_error "Cannot connect to server. Check:"
    echo "  - Server IP is correct: $SERVER_HOST"
    echo "  - SSH user is correct: $SSH_USER"
    echo "  - SSH key path is correct: $SSH_KEY_PATH"
    echo "  - Port 22 is open in security group"
    exit 1
fi

# Check Docker on remote server
log_info "Checking Docker installation on remote server..."
if ! ssh -i "$SSH_KEY_PATH" "$SSH_USER@$SERVER_HOST" "docker --version" > /dev/null 2>&1; then
    log_warn "Docker not installed. Installing Docker..."
    ssh -i "$SSH_KEY_PATH" "$SSH_USER@$SERVER_HOST" "curl -fsSL https://get.docker.com | sh"
    ssh -i "$SSH_KEY_PATH" "$SSH_USER@$SERVER_HOST" "sudo usermod -aG docker \$USER"
    log_warn "Docker installed. You may need to log out and back in for group changes to take effect."
fi

# Check Docker Compose on remote server
log_info "Checking Docker Compose installation..."
if ! ssh -i "$SSH_KEY_PATH" "$SSH_USER@$SERVER_HOST" "docker compose version" > /dev/null 2>&1; then
    log_warn "Docker Compose not installed. Installing..."
    ssh -i "$SSH_KEY_PATH" "$SSH_USER@$SERVER_HOST" "sudo apt-get update && sudo apt-get install -y docker-compose-plugin"
fi

# ============================================
# Deployment
# ============================================
log_info "Starting deployment to $ENVIRONMENT..."

# Create deployment directory
REMOTE_DIR="/opt/travel-assistant"
ssh -i "$SSH_KEY_PATH" "$SSH_USER@$SERVER_HOST" "mkdir -p $REMOTE_DIR"

# Copy files to server
log_info "Copying files to server..."
scp -i "$SSH_KEY_PATH" -r \
    docker-compose.yml \
    frontend/Dockerfile \
    frontend/package.json \
    frontend/next.config.ts \
    frontend/app \
    frontend/components \
    frontend/lib \
    frontend/fonts \
    backend/Dockerfile \
    backend/requirements.txt \
    backend/app \
    backend/gunicorn_conf.py \
    nginx/nginx.conf \
    "$SSH_USER@$SERVER_HOST:$REMOTE_DIR/"

# Copy environment file
log_info "Copying environment file..."
scp -i "$SSH_KEY_PATH" ".env.${ENVIRONMENT}" "$SSH_USER@$SERVER_HOST:$REMOTE_DIR/.env"

# Deploy
log_info "Deploying containers..."
ssh -i "$SSH_KEY_PATH" "$SSH_USER@$SERVER_HOST" << EOF
    cd $REMOTE_DIR

    # Stop existing containers
    docker compose down

    # Pull latest images (if any)
    docker compose pull

    # Build and start containers
    docker compose up -d --build

    # Wait for health checks
    sleep 10

    # Show status
    docker compose ps
EOF

# ============================================
# Post-deployment Checks
# ============================================
log_info "Running post-deployment checks..."

# Check if containers are running
CONTAINER_STATUS=$(ssh -i "$SSH_KEY_PATH" "$SSH_USER@$SERVER_HOST" "cd $REMOTE_DIR && docker compose ps --format json" 2>/dev/null || echo "[]")
RUNNING_CONTAINERS=$(echo "$CONTAINER_STATUS" | grep -o '"Health": "healthy"' | wc -l)

if [ "$RUNNING_CONTAINERS" -ge 3 ]; then
    log_info "Deployment successful! $RUNNING_CONTAINERS containers are healthy."
else
    log_warn "Some containers may not be healthy. Check status on server."
fi

# Test HTTP endpoint
log_info "Testing HTTP endpoint..."
if curl -f -s "http://$SERVER_HOST/health" > /dev/null; then
    log_info "Health check passed! Application is accessible at http://$SERVER_HOST"
else
    log_warn "Health check failed. Check logs: ssh -i $SSH_KEY_PATH $SSH_USER@$SERVER_HOST 'cd $REMOTE_DIR && docker compose logs'"
fi

log_info "Deployment complete!"
log_info "Application URL: http://$SERVER_HOST"
log_info "View logs: ssh -i $SSH_KEY_PATH $SSH_USER@$SERVER_HOST 'cd $REMOTE_DIR && docker compose logs -f'"
