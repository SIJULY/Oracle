# OCI Web Panel - 一款强大的 Oracle Cloud 实例 Web 管理面板

这是一个基于 **Flask** 和 **Celery** 构建的 Web 应用，旨在提供一个图形化界面，用于管理 **Oracle Cloud Infrastructure (OCI)** 上的计算实例。
它特别适合需要频繁创建、管理或“抢占”稀缺实例资源的用户。


## ✨一键安装脚本：
```bash
wget https://raw.githubusercontent.com/SIJULY/Oracle/main/install.sh && chmod +x install.sh && ./install.sh
```

---

## ✨ 功能特性

* **多账户管理**：支持添加和管理多个 OCI 账户配置。
* **实例看板**：清晰地列出账户下所有实例的核心信息（状态、IPv4、IPv6、配置、创建时间等）。
* **实例生命周期管理**：支持对选中实例进行启动、停止、重启和终止操作。
* **网络管理**：

  * 一键更换公网 IP（IPv4）：自动解绑并重新绑定一个新的临时公网 IP。
  * 一键分配 IPv6：为实例自动分配一个 IPv6 地址（需子网支持）。
* **智能实例创建**：

  * **标准创建**：在弹窗中选择规格，程序会自动查找或创建网络环境，并尝试创建一次。
  * **自动抢占实例（抢机）**：针对资源稀缺区域，后台任务会持续循环尝试创建实例，直到成功为止。支持自定义重试间隔。
* **异步任务处理**：所有耗时操作（创建、抢占、实例操作）都在后台通过 Celery 任务执行，不阻塞界面。
* **任务管理与历史**：

  * 提供任务历史弹窗，永久记录所有创建和抢占任务的最终结果。
  * 即使关闭浏览器，也能回来查看任务是否成功，并找回成功实例的 Root 密码。
  * 支持查看正在运行的抢占任务，并可手动停止。
  * 支持删除已完成的任务历史记录。

---

<img width="1443" height="1434" alt="f1c590dd-1097-4cf8-b175-79ec599c8ac2" src="https://github.com/user-attachments/assets/64a1455b-22a9-484a-8f32-947383cbfaa7" />

<img width="1816" height="1478" alt="34bb473d-c4d8-40c2-94e8-96824a70fd68" src="https://github.com/user-attachments/assets/8d604b44-8d73-4ec6-b85d-422b934ada92" />

<img width="1529" height="1406" alt="92eb4491-1291-402b-8a31-ee36b85647f5" src="https://github.com/user-attachments/assets/d00ba123-7c31-4b5f-80d2-ddb7a1215a00" />





## 🚀 部署教程

> 本教程以在一个全新的 **Ubuntu 22.04 VPS** 上部署为例。

### 一、准备工作

1. **一台 VPS**：至少 1GB 内存，并可 SSH 登录。
2. **OCI 账户和 API 密钥**：

   * 您需要一个 Oracle Cloud 账户。
   * 为用户生成一个 API 密钥，记下以下信息：

     * `user` OCID
     * `fingerprint`
     * `tenancy` OCID
     * `region`
     * `.pem` 私钥文件
   * 具体如何获取上述信息可按照下面大佬教程操作：

<img width="1600" height="1000" alt="image" src="https://github.com/user-attachments/assets/e482977d-b220-4c26-9f1e-5b8d2c84a06f" />

<img width="1600" height="1000" alt="image" src="https://github.com/user-attachments/assets/517f4bad-5382-452b-8e4c-886877c22aac" />

<img width="1600" height="1000" alt="image" src="https://github.com/user-attachments/assets/7d2901e2-be6f-4a58-8e80-b1cdfb204436" />

<img width="1482" height="1022" alt="image" src="https://github.com/user-attachments/assets/2b4df7ca-d221-455e-867a-c33b964c6537" />

<img width="1896" height="1150" alt="image" src="https://github.com/user-attachments/assets/b8e46ba5-f1e2-48d3-8aa4-f244bd893de7" />

  **用文本编辑器打开SSH公钥复制到网页提示的输入框中**：






---

### 二、安装步骤

#### 1. 更新系统并安装基础环境

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3-venv python3-pip redis-server nginx -y
```

#### 2. 下载项目文件并设置环境

```bash
# 创建项目目录
mkdir -p /root/Oracle
cd /root/Oracle
```

请将项目中的核心文件上传到 `/root/Oracle` 目录，建议至少包含以下三个文件/目录：

```
/root/Oracle/
├── app.py
├── static/
│   └── script.js
└── templates/
    └── index.html
```

然后创建并激活 Python 虚拟环境：

```bash
python3 -m venv venv
source venv/bin/activate
```

> **提示**：执行 `source venv/bin/activate` 后，命令行前会出现 `(venv)` 提示，表示虚拟环境已激活。

#### 3. 创建 `requirements.txt` 并安装依赖

在项目目录创建 `requirements.txt`：

```bash
nano requirements.txt
```

将以下内容粘贴并保存：

```
Flask
gunicorn
celery
redis
oci
```

然后安装依赖：

```bash
pip install -r requirements.txt
```

#### 4. 配置应用

用编辑器打开 `app.py`，找到登录密码相关配置并修改为安全密码：

```bash
nano app.py
```

```python
# 在 app.py 中找到并修改为您自己的强密码
PASSWORD = "You22kme#12345"  # 【重要】请修改为您自己的登录密码
```

#### 5. 配置 Systemd 服务（实现开机自启和后台运行）

##### a. Gunicorn（Web 服务）

创建 systemd 服务文件：

```bash
nano /etc/systemd/system/ociapp.service
```

将以下内容粘贴进去：

```ini
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
```

> **注意**：如果您不想以 `root` 运行，请创建一个专用用户并修改 `User` 与 `Group` 字段。

##### b. Celery（后台任务服务）

创建 Celery 的 systemd 服务文件：

```bash
nano /etc/systemd/system/celery_worker.service
```

粘贴以下内容：

```ini
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
```

#### 6. 启动并启用服务

```bash
sudo systemctl daemon-reload
sudo systemctl start ociapp.service
sudo systemctl start celery_worker.service

# 设置开机自启
sudo systemctl enable ociapp.service
sudo systemctl enable celery_worker.service
```

#### 7. 配置 Nginx 反向代理

创建 Nginx site 配置：

```bash
nano /etc/nginx/sites-available/ociapp
```

将以下内容粘贴进去（如有域名可替换 `_` 为您的域名）：

```nginx
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
```

启用配置并重启 Nginx：

```bash
sudo ln -s /etc/nginx/sites-available/ociapp /etc/nginx/sites-enabled/
sudo nginx -t  # 测试配置是否正确
sudo systemctl restart nginx
```

---

## ✅ 完成！

现在您可以通过浏览器访问服务器的 **IP 或域名**，输入在 `app.py` 中设置的密码，登录并开始使用 **OCI Web Panel** 🎉

---
