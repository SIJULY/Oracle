#!/bin/bash
set -e

# ===================================================
# OCI Web Panel - 最终安全版一键安装脚本
# 作者: @小龙女她爸
# GitHub: https://github.com/SIJULY/Oracle
# ===================================================

# --- 配置参数 ---
APP_DIR="/root/Oracle"
PYTHON_ENV="$APP_DIR/venv"
CADDY_CONF_DIR="/etc/caddy/conf.d"
CADDY_APP_CONF="$CADDY_CONF_DIR/oci-panel.caddy"
CADDY_MAIN_FILE="/etc/caddy/Caddyfile"
DEFAULT_PASSWORD="ChangeMe#12345"
APP_PORT=5003

echo "📦 开始安装 OCI Web Panel..."

# --- 1. 更新系统并安装依赖 ---
echo "➡️ 步骤 1/7: 更新系统并安装依赖..."
apt update && apt upgrade -y > /dev/null 2>&1
# 安装 redis 和 git。caddy 和 python 工具会单独检查安装。
apt install -y redis-server git python3-venv python3-pip > /dev/null 2>&1

# --- 检查并安装 Caddy ---
echo "➡️ 步骤 2/7: 检查并安装 Caddy..."
if ! command -v caddy &> /dev/null
then
    echo "Caddy 未安装，正在为您安装..."
    apt install -y debian-keyring debian-archive-keyring apt-transport-https curl > /dev/null 2>&1
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg > /dev/null 2>&1
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list > /dev/null
    apt update > /dev/null 2>&1
    apt install caddy > /dev/null 2>&1
    echo "Caddy 安装完毕。"
else
    echo "Caddy 已安装，跳过。"
fi

# --- 2. 克隆项目 ---
echo "➡️ 步骤 3/7: 下载项目代码..."
if [ -d "$APP_DIR" ]; then
    echo "检测到旧目录，正在备份并重新下载..."
    mv $APP_DIR "$APP_DIR-bak-$(date +%s)"
fi
git clone https://github.com/SIJULY/Oracle.git $APP_DIR

# --- 3. 设置 Python 虚拟环境 ---
echo "➡️ 步骤 4/7: 配置 Python 环境..."
cd $APP_DIR
python3 -m venv $PYTHON_ENV
source $PYTHON_ENV/bin/activate
pip install --upgrade pip > /dev/null 2>&1
pip install -r $APP_DIR/requirements.txt > /dev/null 2>&1
deactivate

# --- 4. 交互式设置密码 ---
echo "➡️ 步骤 5/7: 设置应用密码..."
read -p "请输入应用登录密码 (直接回车将使用默认密码: $DEFAULT_PASSWORD): " APP_PASSWORD
APP_PASSWORD=${APP_PASSWORD:-$DEFAULT_PASSWORD}

# 直接修改 app.py 文件中的密码
sed -i "s/^PASSWORD = .*/PASSWORD = \"$APP_PASSWORD\"/" $APP_DIR/app.py
echo "✅ 密码已设置。"

# --- 5. 设置 systemd 服务 ---
echo "➡️ 步骤 6/7: 创建并启动后台服务..."

# Gunicorn (Web 服务)
cat > /etc/systemd/system/ociapp.service <<EOF
[Unit]
Description=Gunicorn for OCI Web Panel
After=network.target

[Service]
User=root
Group=root
WorkingDirectory=$APP_DIR
ExecStart=$PYTHON_ENV/bin/gunicorn --workers 3 --bind 127.0.0.1:$APP_PORT app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Celery (后台任务服务)
cat > /etc/systemd/system/celery_worker.service <<EOF
[Unit]
Description=Celery Worker for OCI App
After=network.target redis-server.service

[Service]
User=root
Group=root
WorkingDirectory=$APP_DIR
ExecStart=$PYTHON_ENV/bin/celery -A app.celery worker --loglevel=info
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now redis-server ociapp.service celery_worker.service > /dev/null 2>&1
systemctl restart redis-server ociapp.service celery_worker.service

# --- 6. 配置 Caddy ---
echo "➡️ 步骤 7/7: 配置 Caddy 反向代理..."
read -p "请输入您的域名 (如果留空，将使用服务器IP地址): " DOMAIN

if [ -z "$DOMAIN" ]; then
    SERVER_IP=$(curl -s ifconfig.me)
    DOMAIN=$SERVER_IP
    CADDY_CONFIG="http://$DOMAIN"
else
    CADDY_CONFIG="$DOMAIN"
fi

# 创建独立的配置文件
mkdir -p $CADDY_CONF_DIR
cat > $CADDY_APP_CONF <<EOF
# OCI Web Panel Config
$CADDY_CONFIG {
    reverse_proxy 127.0.0.1:$APP_PORT
}
EOF

# 检查主 Caddyfile 并安全地添加 import 语句
IMPORT_LINE="import $CADDY_CONF_DIR/*.caddy"
if ! grep -qF "$IMPORT_LINE" "$CADDY_MAIN_FILE"; then
    echo "✅ 正在向主 Caddyfile 添加 import 语句..."
    # 使用 tee 和 sudo 权限来追加内容
    echo -e "\n$IMPORT_LINE" | sudo tee -a "$CADDY_MAIN_FILE" > /dev/null
else
    echo "✅ Import 语句已存在，无需添加。"
fi

systemctl reload caddy

# --- 完成 ---
echo ""
echo "🎉 安装完成！"
echo "👉 您的访问地址是: http://$DOMAIN (如果设置了域名，Caddy会自动配置HTTPS，请用 https://$DOMAIN 访问)"
echo "🔑 您的登录密码是: $APP_PASSWORD"
echo "ℹ️ 如果无法访问，请确保您服务器的防火墙已开放 80 和 443 端口。"
