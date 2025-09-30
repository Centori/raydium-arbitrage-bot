#!/bin/bash
# Docker tag and push script for SolAssassin repository
# This script tags local images and pushes them to Docker Hub

echo "===== SolAssassin - Docker Image Push ====="

# Use centori88 as default username if not provided
if [ -z "$1" ]; then
  DOCKER_USERNAME="centori88"
  echo "Using default username: centori88"
else
  DOCKER_USERNAME=$1
fi

# Version tag - use date if not provided
if [ -z "$2" ]; then
  VERSION=$(date +"%Y%m%d")
else
  VERSION=$2
fi

echo "🔹 Using repository: $DOCKER_USERNAME/solassassin"
echo "🔹 Using version tag: $VERSION"

# Tag and push the TypeScript service
echo "📦 Tagging and pushing TypeScript service..."
docker tag raydium-arbitrage-bot_typescript-service:latest $DOCKER_USERNAME/solassassin:typescript-$VERSION
docker push $DOCKER_USERNAME/solassassin:typescript-$VERSION

# Tag and push the Python service
echo "📦 Tagging and pushing Python service..."
docker tag raydium-arbitrage-bot_python-service:latest $DOCKER_USERNAME/solassassin:python-$VERSION
docker push $DOCKER_USERNAME/solassassin:python-$VERSION

# Tag and push the Liquidity Monitor service
echo "📦 Tagging and pushing Liquidity Monitor service..."
docker tag raydium-arbitrage-bot_liquidity-monitor:latest $DOCKER_USERNAME/solassassin:monitor-$VERSION
docker push $DOCKER_USERNAME/solassassin:monitor-$VERSION

# Tag latest versions
echo "📦 Tagging and pushing latest versions..."
docker tag raydium-arbitrage-bot_typescript-service:latest $DOCKER_USERNAME/solassassin:typescript-latest
docker push $DOCKER_USERNAME/solassassin:typescript-latest

docker tag raydium-arbitrage-bot_python-service:latest $DOCKER_USERNAME/solassassin:python-latest
docker push $DOCKER_USERNAME/solassassin:python-latest

docker tag raydium-arbitrage-bot_liquidity-monitor:latest $DOCKER_USERNAME/solassassin:monitor-latest
docker push $DOCKER_USERNAME/solassassin:monitor-latest

echo "✅ All SolAssassin images have been tagged and pushed to Docker Hub!"
echo ""
echo "You can now pull these images using:"
echo "docker pull $DOCKER_USERNAME/solassassin:typescript-$VERSION"
echo "docker pull $DOCKER_USERNAME/solassassin:python-$VERSION"
echo "docker pull $DOCKER_USERNAME/solassassin:monitor-$VERSION"
echo ""
echo "Or use the latest tag:"
echo "docker pull $DOCKER_USERNAME/solassassin:typescript-latest"
echo "docker pull $DOCKER_USERNAME/solassassin:python-latest"
echo "docker pull $DOCKER_USERNAME/solassassin:monitor-latest"