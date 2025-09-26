#!/bin/bash

# 设置脚本在任何命令出错时立即退出
set -e

# --- 配置 ---
# 【重要修正】自动检测脚本所在的目录作为应用目录
APP_DIR=$(pwd)
# systemd服务名称
SERVICE_NAME="ociapp"

# --- 脚本开始 ---
echo "================================================="
echo "  OCI Web Panel Installer (Caddy Coexistence Version)  "
echo "================================================="

# 1. 更新系统并安装基础依赖
echo ">>> [1/7] Updating system and installing dependencies..."
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y python3-pip python3-venv git curl debian-keyring debian-archive-keyring apt-transport-https

# 2. 安装 Caddy Web 服务器 (如果尚未安装)
echo ">>> [2/7] Checking and installing Caddy..."
if ! command -v caddy &> /dev/null
then
    echo "Caddy not found. Installing now..."
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
    apt-get update
    apt-get install -y caddy
else
    echo "Caddy is already installed. Skipping installation."
fi

# 3. 检查项目文件 (因为我们现在在项目目录里运行)
echo ">>> [3/7] Verifying project files in current directory..."
if [ ! -f "${APP_DIR}/app.py" ] || [ ! -f "${APP_DIR}/requirements.txt" ]; then
    echo "错误：无法在当前目录 ${APP_DIR} 中找到 app.py 或 requirements.txt。"
    echo "请确保您在克隆后的项目目录中运行此脚本。"
    exit 1
fi
echo "Project files verified."

# 4. 设置Python虚拟环境并安装依赖
echo ">>> [4/7] Setting up Python environment..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
deactivate

# 5. 清理并创建 systemd 服务文件
echo ">>> [5/7] Creating systemd service for the application..."
systemctl stop "${SERVICE_NAME}.service" 2>/dev/null || true
systemctl disable "${SERVICE_NAME}.service" 2>/dev/null || true

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

# 6. 配置 Caddy 以实现并存
echo ">>> [6/7] Configuring Caddy for coexistence..."
SERVER_IP=$(curl -s -4 ifconfig.me || echo "")
if [ -z "$SERVER_IP" ]; then
    echo "警告：无法自动获取公网IP地址。将使用 'localhost' 作为备用地址。"
    SERVER_IP="localhost"
else
    echo "成功获取到公网IP: ${SERVER_IP}"
fi

# 为我们的应用创建独立的配置文件
mkdir -p /etc/caddy/conf.d
cat <<EOF > /etc/caddy/conf.d/${SERVICE_NAME}.caddy
# Caddyfile for ${SERVICE_NAME}

http://${SERVER_IP} {
    reverse_proxy 127.0.0.1:5003
}
EOF

# 确保主 Caddyfile 导入了我们的配置目录
if ! grep -q "import /etc/caddy/conf.d/*.caddy" /etc/caddy/Caddyfile; then
    echo "Adding 'import' directive to main Caddyfile..."
    echo -e "\nimport /etc/caddy/conf.d/*.caddy" >> /etc/caddy/Caddyfile
fi

# 7. 启动并启用服务
echo ">>> [7/7] Starting and enabling services..."
systemctl daemon-reload
systemctl start "${SERVICE_NAME}"
systemctl enable "${SERVICE_NAME}"
systemctl restart caddy
systemctl enable caddy

# --- 结束语 ---
echo "================================================="
echo "🎉 部署完成！"
echo "您的应用现在应该可以通过以下地址访问："
echo "http://${SERVER_IP}"
echo "您现有的 Caddy 站点应该不受影响。"
echo "================================================="

