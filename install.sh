#!/bin/bash
set -e
#
# ============================================
# Oracle 一键安装脚本
# 作者: @小龙女她爸
# GitHub: https://github.com/SIJULY/Oracle
# ============================================

APP_DIR="/opt/oracle-app"
PYTHON_ENV="$APP_DIR/venv"
CADDY_FILE="/etc/caddy/Caddyfile"
DEFAULT_PASSWORD="ChangeMe#12345"

echo "📦 开始安装 Oracle 项目..."

# 1. 安装依赖
echo "➡️ 安装依赖..."
apt update
apt install -y python3 python3-venv python3-pip git curl sudo caddy

# 2. 克隆项目
echo "➡️ 下载项目代码..."
rm -rf $APP_DIR
git clone https://github.com/SIJULY/Oracle.git $APP_DIR

# 3. 设置 Python 虚拟环境
echo "➡️ 配置 Python 环境..."
python3 -m venv $PYTHON_ENV
source $PYTHON_ENV/bin/activate
pip install --upgrade pip
pip install -r $APP_DIR/requirements.txt
deactivate

# 4. 交互式设置密码
echo "➡️ 设置应用密码..."
read -p "请输入应用密码（默认 $DEFAULT_PASSWORD）: " APP_PASSWORD
APP_PASSWORD=${APP_PASSWORD:-$DEFAULT_PASSWORD}

# 写入 .env
cat > $APP_DIR/.env <<EOF
APP_PASSWORD=$APP_PASSWORD
EOF

echo "✅ 密码已写入 $APP_DIR/.env"

# 5. 设置 systemd 服务
echo "➡️ 创建 systemd 服务..."
cat > /etc/systemd/system/oracle-app.service <<EOF
[Unit]
Description=Oracle Flask App
After=network.target

[Service]
User=root
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$PYTHON_ENV/bin/python $APP_DIR/app.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable oracle-app
systemctl restart oracle-app

# 6. 配置 Caddy
echo "➡️ 配置 Caddy 反向代理..."
read -p "请输入域名（留空则使用服务器 IP）: " DOMAIN

if [ -z "$DOMAIN" ]; then
    # 获取公网 IP
    SERVER_IP=$(curl -s ifconfig.me)
    DOMAIN=$SERVER_IP
    echo "⚠️ 未输入域名，将使用 IP: http://$SERVER_IP"
    cat > $CADDY_FILE <<EOF
$DOMAIN:80 {
    reverse_proxy 127.0.0.1:5000
}
EOF
else
    echo "✅ 使用域名 $DOMAIN"
    cat > $CADDY_FILE <<EOF
$DOMAIN {
    reverse_proxy 127.0.0.1:5000
}
EOF
fi

systemctl restart caddy

echo "🎉 安装完成！"
echo "👉 访问地址: http://$DOMAIN"
echo "🔑 登录密码: $APP_PASSWORD"
