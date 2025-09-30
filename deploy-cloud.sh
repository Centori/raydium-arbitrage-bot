#!/bin/bash

# Cloud deployment script for Raydium Arbitrage Bot
# This script can be used to deploy to any Docker-based cloud service

echo "===== Raydium Arbitrage Bot - Cloud Deployment ====="

# Set up environment variables
if [ ! -f .env ]; then
    echo "Error: .env file not found. Create one based on the example."
    exit 1
fi

# Ensure required directories exist
mkdir -p logs data/liquidity data/metrics

# Login to Docker registry (replace with your registry)
echo "Logging in to Docker registry..."
# For Docker Hub
# docker login -u YOUR_USERNAME -p YOUR_PASSWORD

# For Google Container Registry
# gcloud auth configure-docker

# For Azure Container Registry
# az acr login --name YOUR_REGISTRY

# Build the Docker images
echo "Building Docker images..."
docker-compose build

# Tag the images for the registry
echo "Tagging images for registry..."
# Replace these with your actual registry and image names
REGISTRY="your-registry.io"
PROJECT="raydium-arbitrage-bot"
TAG=$(date +%Y%m%d%H%M%S)

docker tag raydium-arbitrage-bot-typescript-service $REGISTRY/$PROJECT-typescript:$TAG
docker tag raydium-arbitrage-bot-python-service $REGISTRY/$PROJECT-python:$TAG

# Push the images to the registry
echo "Pushing images to registry..."
docker push $REGISTRY/$PROJECT-typescript:$TAG
docker push $REGISTRY/$PROJECT-python:$TAG

# Create docker-compose.cloud.yml with registry images
cat > docker-compose.cloud.yml << EOF
version: '3.8'

services:
  typescript-service:
    image: $REGISTRY/$PROJECT-typescript:$TAG
    ports:
      - "\${API_PORT:-3000}:3000"
    environment:
      - NODE_ENV=production
      - RPC_ENDPOINT=\${RPC_ENDPOINT}
      - ALCHEMY_API_KEY=\${ALCHEMY_API_KEY}
      - HELIUS_API_KEY=\${HELIUS_API_KEY}
      - JITO_ENDPOINT=\${JITO_ENDPOINT}
      - JITO_AUTH_KEYPAIR_BASE64=\${JITO_AUTH_KEYPAIR_BASE64}
      - API_PORT=\${API_PORT:-3000}
      - API_HOST=0.0.0.0
      - TELEGRAM_BOT_TOKEN=\${TELEGRAM_BOT_TOKEN}
      - TELEGRAM_CHAT_ID=\${TELEGRAM_CHAT_ID}
    restart: always
    volumes:
      - logs:/app/logs

  python-service:
    image: $REGISTRY/$PROJECT-python:$TAG
    environment:
      - PYTHONUNBUFFERED=1
      - API_HOST=typescript-service
      - API_PORT=\${API_PORT:-3000}
      - ALCHEMY_API_KEY=\${ALCHEMY_API_KEY}
      - HELIUS_API_KEY=\${HELIUS_API_KEY}
      - RPC_ENDPOINT=\${RPC_ENDPOINT}
    depends_on:
      - typescript-service
    restart: always
    volumes:
      - logs:/app/logs

volumes:
  logs:
EOF

echo "Docker Compose file for cloud deployment created: docker-compose.cloud.yml"
echo "Deploy to your cloud provider using: docker-compose -f docker-compose.cloud.yml up -d"

# Deploy commands for specific cloud platforms (uncomment as needed)

# DigitalOcean App Platform
# doctl apps create --spec digitalocean.yml

# Google Cloud Run
# gcloud run deploy raydium-arbitrage-bot --image $REGISTRY/$PROJECT:$TAG --platform managed

# Azure Container Instances
# az container create --resource-group myResourceGroup --name raydium-arbitrage-bot --image $REGISTRY/$PROJECT:$TAG --dns-name-label raydium-bot --ports 3000 --environment-variables 'API_PORT'='3000'

echo "Deployment completed successfully!"