OCI Web Panel - 一款强大的 Oracle Cloud 实例 Web 管理面板
这是一个基于 Flask 和 Celery 构建的 Web 应用，旨在提供一个图形化界面，用于管理 Oracle Cloud Infrastructure (OCI) 上的计算实例。它特别适合需要频繁创建、管理或“抢占”稀缺实例资源的用户。

(提示：您可以将您的应用截图上传到图床，并替换上面的链接)

✨ 功能特性
多账户管理：支持添加和管理多个 OCI 账户配置。

实例看板：清晰地列出账户下所有实例的核心信息（状态、IPV4、IPV6、配置、创建时间等）。

实例生命周期管理：支持对选中实例进行启动、停止、重启和终止操作。

网络管理：

一键更换公网IP (IPV4)：自动解绑并重新绑定一个新的临时公网IP。

一键分配IPV6：为实例自动分配一个IPV6地址（需子网支持）。

智能实例创建：

标准创建：在弹窗中选择规格，程序会自动查找或创建网络环境，并尝试创建一次。

自动抢占实例 (抢机)：针对资源稀缺区域，后台任务会持续循环尝试创建实例，直到成功为止。支持自定义重试间隔。

异步任务处理：所有耗时操作（创建、抢占、实例操作）都在后台通过 Celery 任务执行，不阻塞界面。

任务管理与历史：

提供任务历史弹窗，永久记录所有创建和抢占任务的最终结果。

即使关闭浏览器，也能回来查看任务是否成功，并找回成功实例的 Root 密码。

支持查看正在运行的抢占任务，并可手动停止。

支持删除已完成的任务历史记录。

🚀 部署教程
本教程以在一个全新的 Ubuntu 22.04 VPS 上部署为例。

一、准备工作
一台 VPS：拥有一台至少 1GB 内存的 VPS，并已配置好 SSH 登录。

OCI 账户和 API 密钥：

您需要一个 Oracle Cloud 账户。

您需要为将要管理的用户生成一个 API 密钥，并记下相关的配置信息（user OCID, fingerprint, tenancy OCID, region）以及下载的 .pem 私钥文件。

确保该用户所属的用户组拥有足够的权限策略 (Policy)。为了使用本应用的所有功能，建议授予以下权限：

allow group <您的用户组名> to manage all-resources in tenancy
如果您想精细化控制，至少需要 manage instance-family 和 manage virtual-network-family 权限。

二、安装步骤
1. 更新系统并安装基础环境
Bash

sudo apt update && sudo apt upgrade -y
sudo apt install python3-venv python3-pip redis-server nginx -y
2. 下载项目文件并设置环境
Bash

# 创建项目目录
mkdir -p /root/Oracle
cd /root/Oracle

# 在这里，您需要将下面提供的三个核心文件 app.py, index.html, script.js 上传到这个目录
# 目录结构应如下所示：
# /root/Oracle/
# |-- app.py
# |-- templates/
# |   `-- index.html
# `-- static/
#     `-- script.js

# 创建 Python 虚拟环境
python3 -m venv venv

# 激活虚拟环境
source venv/bin/activate
3. 创建 requirements.txt 并安装依赖
Bash

# 创建依赖文件
nano requirements.txt
将以下内容粘贴到 requirements.txt 文件中并保存：

Plaintext

Flask
gunicorn
celery
redis
oci
然后执行安装命令：

Bash

# 确保您仍处于虚拟环境中 (命令行前有 (venv) 标志)
pip install -r requirements.txt
4. 配置应用
用 nano 或其他编辑器打开 app.py 文件：

Bash

nano app.py
找到这一行，并将密码修改为您自己的强密码：

Python

PASSWORD = "You22kme#12345" # 【重要】请修改为您自己的登录密码
5. 配置 Systemd 服务 (实现开机自启和后台运行)
a. Gunicorn (Web 服务)
创建服务文件：

Bash

nano /etc/systemd/system/ociapp.service
粘贴以下内容：

Ini, TOML

[Unit]
Description=Gunicorn for OCI Web Panel
After=network.target

[Service]
User=root
Group=root
WorkingDirectory=/root/Oracle
ExecStart=/root/Oracle/venv/bin/gunicorn --workers 3 --bind 127.0.0.1:5003 app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
b. Celery (后台任务服务)
创建服务文件：

Bash

nano /etc/systemd/system/celery_worker.service
粘贴以下内容：

Ini, TOML

[Unit]
Description=Celery Worker for OCI App
After=network.target redis-server.service

[Service]
User=root
Group=root
WorkingDirectory=/root/Oracle
ExecStart=/root/Oracle/venv/bin/celery -A app.celery worker --loglevel=info
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
6. 启动服务
Bash

sudo systemctl daemon-reload
sudo systemctl start ociapp.service
sudo systemctl start celery_worker.service

# 设置开机自启
sudo systemctl enable ociapp.service
sudo systemctl enable celery_worker.service
7. 配置 Nginx 反向代理
创建一个新的 Nginx 配置文件：

Bash

nano /etc/nginx/sites-available/ociapp
粘贴以下内容 (如果您有域名，可以将 _ 替换为您的域名)：

Nginx

server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:5003;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
启用这个配置并重启 Nginx：

Bash

sudo ln -s /etc/nginx/sites-available/ociapp /etc/nginx/sites-enabled/
sudo nginx -t  # 测试配置是否正确
sudo systemctl restart nginx
三、使用方法
访问和登录：在浏览器中输入您的 VPS 的公网 IP 地址（或域名），您会看到登录页面。输入您在 app.py 中设置的密码进行登录。

添加账户：在左上角的“添加 OCI 账户”卡片中，填入您的 OCI 账户信息和之前下载的 .pem 私钥文件。SSH公钥是使用创建/抢占功能的必需项。

连接账户：在右上角的“账户列表”中，点击“连接”按钮。连接成功后，页面会自动刷新并加载该账户下的实例列表。

执行操作：

选中实例列表中的任意实例，下方的操作按钮（启动、更换IP等）会被激活。

点击“创建实例”或“自动抢占实例”，在弹出的窗口中填写规格并开始任务。

点击“任务历史”可以随时查看所有创建和抢占任务的结果，找回丢失的密码。

