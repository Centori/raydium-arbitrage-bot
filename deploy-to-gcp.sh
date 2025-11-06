#!/bin/bash
set -e

# Configuration
PROJECT_ID="integra-backend-prod"
INSTANCE_NAME="raydium-bot"
ZONE="us-central1-a"  # Low latency for Solana RPC
MACHINE_TYPE="e2-medium"  # 2 vCPUs, 4GB RAM - sufficient for the bot
BOOT_DISK_SIZE="20GB"
IMAGE_FAMILY="ubuntu-2204-lts"
IMAGE_PROJECT="ubuntu-os-cloud"

echo "=== Raydium Arbitrage Bot Deployment to GCP ==="
echo "Project: $PROJECT_ID"
echo "Instance: $INSTANCE_NAME"
echo "Zone: $ZONE"
echo ""

# Check if gcloud is authenticated
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q .; then
    echo "❌ Not authenticated with gcloud. Run: gcloud auth login"
    exit 1
fi

# Set project
gcloud config set project $PROJECT_ID

# Create application archive (exclude unnecessary files)
echo "📦 Creating application archive..."
tar -czf /tmp/raydium-bot-app.tar.gz \
    --exclude='venv' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.git' \
    --exclude='*.log' \
    --exclude='data/migration_history.json' \
    --exclude='data/pool_cache.json' \
    --exclude='node_modules' \
    --exclude='.pytest_cache' \
    --exclude='deploy-to-gcp.sh' \
    -C "$(pwd)" .

echo "✅ Application archive created: $(du -h /tmp/raydium-bot-app.tar.gz | cut -f1)"

# Note: .env file is excluded for security - will be configured manually on VM
echo "🔐 Application archive ready (secrets excluded)"

# Check if instance already exists
if gcloud compute instances describe $INSTANCE_NAME --zone=$ZONE &>/dev/null; then
    echo "⚠️  Instance '$INSTANCE_NAME' already exists in zone $ZONE"
    read -p "Do you want to delete it and create a new one? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "🗑️  Deleting existing instance..."
        gcloud compute instances delete $INSTANCE_NAME --zone=$ZONE --quiet
    else
        echo "❌ Deployment cancelled"
        exit 0
    fi
fi

# Create the VM instance
echo "🚀 Creating Compute Engine instance..."
gcloud compute instances create $INSTANCE_NAME \
    --project=$PROJECT_ID \
    --zone=$ZONE \
    --machine-type=$MACHINE_TYPE \
    --boot-disk-size=$BOOT_DISK_SIZE \
    --boot-disk-type=pd-standard \
    --image-family=$IMAGE_FAMILY \
    --image-project=$IMAGE_PROJECT \
    --tags=raydium-bot \
    --metadata-from-file=startup-script=startup-script.sh \
    --scopes=cloud-platform \
    --maintenance-policy=MIGRATE \
    --provisioning-model=STANDARD

echo "⏳ Waiting for instance to be ready (this may take 2-3 minutes)..."
sleep 30

# Wait for SSH to be available
echo "🔌 Waiting for SSH access..."
for i in {1..30}; do
    if gcloud compute ssh $INSTANCE_NAME --zone=$ZONE --command="echo 'SSH ready'" &>/dev/null; then
        echo "✅ SSH is ready"
        break
    fi
    echo "  Attempt $i/30..."
    sleep 10
done

# Upload application files (without secrets)
echo "📤 Uploading application files to VM (secrets excluded)..."
gcloud compute scp /tmp/raydium-bot-app.tar.gz \
    $INSTANCE_NAME:/tmp/app.tar.gz \
    --zone=$ZONE

# Extract and setup on VM
echo "⚙️  Setting up application on VM..."
gcloud compute ssh $INSTANCE_NAME --zone=$ZONE --command="
    sudo mkdir -p /home/botuser/raydium-arbitrage-bot
    sudo tar -xzf /tmp/app.tar.gz -C /home/botuser/raydium-arbitrage-bot
    sudo chown -R botuser:botuser /home/botuser/raydium-arbitrage-bot
    rm /tmp/app.tar.gz
"

# Check startup script logs
echo "📋 Checking startup script progress..."
sleep 10
gcloud compute ssh $INSTANCE_NAME --zone=$ZONE --command="
    sudo tail -n 50 /var/log/syslog | grep startup-script || echo 'Startup script still running...'
"

echo ""
echo "=== Deployment Complete ==="
echo "Instance Name: $INSTANCE_NAME"
echo "Zone: $ZONE"
echo "External IP: $(gcloud compute instances describe $INSTANCE_NAME --zone=$ZONE --format='get(networkInterfaces[0].accessConfigs[0].natIP)')"
echo ""
echo "⚠️  IMPORTANT: Configure secrets before starting the bot:"
echo "  1. SSH to VM:     gcloud compute ssh $INSTANCE_NAME --zone=$ZONE"
echo "  2. Run setup:     sudo bash /home/botuser/raydium-arbitrage-bot/setup-secrets-on-vm.sh"
echo "  3. Edit .env:     sudo nano /home/botuser/raydium-arbitrage-bot/.env"
echo "  4. Start bot:     sudo systemctl start raydium-bot"
echo ""
echo "📊 Useful commands:"
echo "  View logs:       gcloud compute ssh $INSTANCE_NAME --zone=$ZONE --command='sudo journalctl -u raydium-bot -f'"
echo "  Check status:    gcloud compute ssh $INSTANCE_NAME --zone=$ZONE --command='sudo systemctl status raydium-bot'"
echo "  Stop bot:        gcloud compute ssh $INSTANCE_NAME --zone=$ZONE --command='sudo systemctl stop raydium-bot'"
echo "  Delete instance: gcloud compute instances delete $INSTANCE_NAME --zone=$ZONE"
echo ""
echo "💡 Bot will NOT start automatically until you configure secrets."

# Cleanup
rm /tmp/raydium-bot-app.tar.gz

echo "✨ Done!"
