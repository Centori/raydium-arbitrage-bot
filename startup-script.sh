#!/bin/bash
set -e

# Logging function
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*" | tee -a /var/log/bot-startup.log
}

log "=== Starting Raydium Arbitrage Bot Setup ==="

# Update system
log "Updating system packages..."
apt-get update -y
apt-get upgrade -y

# Install Python 3.11 and required packages
log "Installing Python 3.11 and dependencies..."
apt-get install -y python3.11 python3.11-venv python3-pip git curl

# Create bot user if it doesn't exist
if ! id -u botuser > /dev/null 2>&1; then
    log "Creating bot user..."
    useradd -m -s /bin/bash botuser
fi

# Set up application directory
APP_DIR="/home/botuser/raydium-arbitrage-bot"
log "Setting up application directory at $APP_DIR..."

# Clone or update repository if it exists
if [ ! -d "$APP_DIR" ]; then
    log "Creating application directory..."
    mkdir -p "$APP_DIR"
    chown -R botuser:botuser "$APP_DIR"
fi

# Create necessary subdirectories
su - botuser -c "mkdir -p $APP_DIR/data $APP_DIR/logs $APP_DIR/keys"

# Copy application files from metadata server
log "Retrieving application files from instance metadata..."
curl -H "Metadata-Flavor: Google" \
  "http://metadata.google.internal/computeMetadata/v1/instance/attributes/app-archive" \
  -o /tmp/app.tar.gz 2>/dev/null || log "No app archive in metadata, will need manual upload"

if [ -f /tmp/app.tar.gz ]; then
    log "Extracting application files..."
    su - botuser -c "cd $APP_DIR && tar -xzf /tmp/app.tar.gz"
    rm /tmp/app.tar.gz
fi

# Create virtual environment
log "Creating Python virtual environment..."
su - botuser -c "cd $APP_DIR && python3.11 -m venv venv"

# Install Python dependencies
if [ -f "$APP_DIR/requirements.txt" ]; then
    log "Installing Python dependencies..."
    su - botuser -c "cd $APP_DIR && source venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt"
else
    log "WARNING: requirements.txt not found, installing minimal dependencies..."
    su - botuser -c "cd $APP_DIR && source venv/bin/activate && pip install --upgrade pip && \
        pip install requests python-dotenv pytest pytest-asyncio httpx numpy pandas python-dateutil \
        aiohttp asyncio solders solana websockets pylint matplotlib python-telegram-bot"
fi

# Create .env file from metadata if not exists
if [ ! -f "$APP_DIR/.env" ]; then
    log "Creating .env file from metadata..."
    curl -H "Metadata-Flavor: Google" \
      "http://metadata.google.internal/computeMetadata/v1/instance/attributes/env-file" \
      -o "$APP_DIR/.env" 2>/dev/null || log "No .env in metadata"
    chown botuser:botuser "$APP_DIR/.env"
    chmod 600 "$APP_DIR/.env"
fi

# Create systemd service
log "Creating systemd service..."
cat > /etc/systemd/system/raydium-bot.service <<EOF
[Unit]
Description=Raydium Arbitrage Bot
After=network.target

[Service]
Type=simple
User=botuser
WorkingDirectory=$APP_DIR
Environment="PATH=$APP_DIR/venv/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=$APP_DIR/venv/bin/python3 run_migration_sniper.py
Restart=always
RestartSec=10
StandardOutput=append:$APP_DIR/logs/bot.log
StandardError=append:$APP_DIR/logs/bot-error.log

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$APP_DIR/data $APP_DIR/logs

[Install]
WantedBy=multi-user.target
EOF

# Set up log rotation
log "Setting up log rotation..."
cat > /etc/logrotate.d/raydium-bot <<EOF
$APP_DIR/logs/*.log {
    daily
    rotate 7
    compress
    delaycompress
    notifempty
    create 0640 botuser botuser
    sharedscripts
    postrotate
        systemctl reload raydium-bot > /dev/null 2>&1 || true
    endscript
}
EOF

# Enable and start the service
log "Enabling and starting raydium-bot service..."
systemctl daemon-reload
systemctl enable raydium-bot
systemctl start raydium-bot

# Wait a few seconds and check status
sleep 5
if systemctl is-active --quiet raydium-bot; then
    log "✅ Bot service started successfully!"
    systemctl status raydium-bot --no-pager
else
    log "❌ Bot service failed to start. Check logs:"
    journalctl -u raydium-bot -n 50 --no-pager
fi

log "=== Setup Complete ==="
log "Bot logs: $APP_DIR/logs/bot.log"
log "Service status: systemctl status raydium-bot"
log "View logs: journalctl -u raydium-bot -f"
