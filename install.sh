#!/bin/bash
set -e
# 【重要】请将下面的URL替换为您自己的GitHub仓库地址！
GIT_REPO_URL="https://github.com/SIJULY/Oracle.git"
APP_DIR="/root/oci-web-app"
SERVICE_NAME="ociapp"
echo "================================================="; echo "  OCI Web Panel Installer (Caddy Version)  "; echo "================================================="
echo ">>> [1/7] Updating system and installing dependencies..."
apt-get update
apt-get install -y python3-pip python3-venv git curl debian-keyring debian-archive-keyring apt-transport-https
echo ">>> [2/7] Installing Caddy Web Server..."
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
apt-get update
apt-get install -y caddy
echo ">>> [3/7] Cloning project from GitHub..."
if [ -d "$APP_DIR" ]; then echo "Directory exists, skipping clone."; else git clone "$GIT_REPO_URL" "$APP_DIR"; fi
cd "$APP_DIR"
echo ">>> [4/7] Setting up Python environment..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
deactivate
echo ">>> [5/7] Creating systemd service..."
cat <<EOF > /etc/systemd/system/${SERVICE_NAME}.service
[Unit]
Description=Gunicorn for OCI Web Panel
After=network.target
[Service]
User=root
Group=root
WorkingDirectory=${APP_DIR}
ExecStart=${APP_DIR}/venv/bin/gunicorn --workers 3 --bind 127.0.0.1:5003 --log-level=info app:app
Restart=always
[Install]
WantedBy=multi-user.target
EOF
echo ">>> [6/7] Configuring Caddy..."
SERVER_IP=$(curl -s -4 ifconfig.me)
cat <<EOF > /etc/caddy/Caddyfile
http://${SERVER_IP} {
    reverse_proxy 127.0.0.1:5003
}
EOF
echo ">>> [7/7] Starting services..."
systemctl daemon-reload
systemctl start "${SERVICE_NAME}"
systemctl enable "${SERVICE_NAME}"
systemctl reload caddy
echo "================================================="; echo "🎉 Deployment complete!"; echo "Access your OCI Web Panel at: http://${SERVER_IP}"; echo "================================================="
