#!/bin/bash

# 设置脚本在任何命令出错时立即退出
set -e

# --- 配置 ---
# 您的GitHub仓库地址
GIT_REPO_URL="https://github.com/SIJULY/Oracle.git"
# 应用安装目录
APP_DIR="/root/oci-web-app"
# systemd服务名称
SERVICE_NAME="ociapp"

# --- 脚本开始 ---
echo "================================================="
echo "  OCI Web Panel Installer (Caddy Version)  "
echo "================================================="

# 1. 更新系统并安装基础依赖
echo ">>> [1/7] Updating system and installing dependencies..."
apt-get update
apt-get install -y python3-pip python3-venv git curl debian-keyring debian-archive-keyring apt-transport-https

# 2. 安装 Caddy Web 服务器
echo ">>> [2/7] Installing Caddy Web Server..."
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
apt-get update
apt-get install -y caddy

# 3. 从GitHub克隆项目代码
echo ">>> [3/7] Cloning project from GitHub..."
if [ -d "$APP_DIR" ]; then
    echo "Warning: Directory $APP_DIR already exists, skipping clone."
else
    git clone "$GIT_REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"

# 4. 设置Python虚拟环境并安装依赖
echo ">>> [4/7] Setting up Python environment..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
deactivate

# 5. 创建 systemd 服务文件，让Gunicorn在后台运行
echo ">>> [5/7] Creating systemd service for the application..."
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

# 6. 配置 Caddy 作为反向代理
echo ">>> [6/7] Configuring Caddy..."
SERVER_IP=$(curl -s -4 ifconfig.me)
cat <<EOF > /etc/caddy/Caddyfile
# Caddyfile for ${SERVICE_NAME}

http://${SERVER_IP} {
    reverse_proxy 127.0.0.1:5003
}
EOF

# 7. 启动并启用服务
echo ">>> [7/7] Starting and enabling services..."
systemctl daemon-reload
systemctl start "${SERVICE_NAME}"
systemctl enable "${SERVICE_NAME}"
# 【重要修正】使用 restart 确保 Caddy 无论如何都会应用新配置并运行
systemctl restart caddy
systemctl enable caddy

# --- 结束语 ---
echo "================================================="
echo "🎉 Deployment complete!"
echo "Your application should now be accessible at:"
echo "http://${SERVER_IP}"
echo "================================================="
