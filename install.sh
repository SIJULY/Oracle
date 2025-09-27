#!/bin/bash
set -e

# ==============================
# 配置参数（可修改）
# ==============================
APP_DIR="/root/Oracle"
PASSWORD="ChangeMe#12345"   # 【重要】修改为你自己的登录密码
APP_PORT=5003

# ==============================
# 1. 更新系统并安装依赖
# ==============================
echo "📦 更新系统并安装依赖..."
apt update && apt upgrade -y
apt install -y python3-venv python3-pip redis-server nginx git

# ==============================
# 2. 下载项目文件
# ==============================
echo "⬇️ 下载项目文件..."
if [ ! -d "$APP_DIR" ]; then
    mkdir -p $APP_DIR
fi

cd $APP_DIR
# 克隆或更新仓库
if [ ! -d ".git" ]; then
    git clone https://github.com/SIJULY/Oracle.git $APP_DIR
else
    git pull
fi

# ==============================
# 3. 设置 Python 虚拟环境
# ==============================
echo "🐍 创建虚拟环境并安装依赖..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# ==============================
# 4. 修改应用密码
# ==============================
echo "🔑 设置应用密码..."
sed -i "s|PASSWORD = .*|PASSWORD = \"$PASSWORD\"|" app.py

# ==============================
# 5. 配置 systemd 服务
# ==============================

echo "⚙️ 配置 systemd..."

# Gunicorn
cat >/etc/systemd/system/ociapp.service <<EOF
[Unit]
Description=Gunicorn for OCI Web Panel
After=network.target

[Service]
User=root
Group=root
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/venv/bin/gunicorn --workers 3 --bind 127.0.0.1:$APP_PORT app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Celery
cat >/etc/systemd/system/celery_worker.service <<EOF
[Unit]
Description=Celery Worker for OCI App
After=network.target redis-server.service

[Service]
User=root
Group=root
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/venv/bin/celery -A app.celery worker --loglevel=info
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now ociapp.service
systemctl enable --now celery_worker.service

# ==============================
# 6. 配置 Nginx
# ==============================
echo "🌐 配置 Nginx..."
cat >/etc/nginx/sites-available/ociapp <<EOF
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:$APP_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    }
}
EOF

ln -sf /etc/nginx/sites-available/ociapp /etc/nginx/sites-enabled/
nginx -t && systemctl restart nginx

# ==============================
# 完成
# ==============================
echo "✅ 安装完成！"
echo "👉 请在浏览器访问 http://<你的服务器IP> 登录"
echo "👉 登录密码：$PASSWORD"
