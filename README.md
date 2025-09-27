# OCI Web Panel - 一款强大的 Oracle Cloud 实例 Web 管理面板

这是一个基于 Flask 和 Celery 构建的 Web 应用，旨在提供一个图形化界面，用于管理 Oracle Cloud Infrastructure (OCI) 上的计算实例。它特别适合需要频繁创建、管理或“抢占”稀缺实例资源的用户。

![应用截图](https://i.imgur.com/your-screenshot-url.png)
*(提示：您可以将您的应用截图上传到图床，并替换上面的链接)*

## ✨ 功能特性

* **多账户管理**：支持添加和管理多个 OCI 账户配置。
* **实例看板**：清晰地列出账户下所有实例的核心信息（状态、IPV4、IPV6、配置、创建时间等）。
* **实例生命周期管理**：支持对选中实例进行启动、停止、重启和终止操作。
* **网络管理**：
    * 一键更换公网IP (IPV4)：自动解绑并重新绑定一个新的临时公网IP。
    * 一键分配IPV6：为实例自动分配一个IPV6地址（需子网支持）。
* **智能实例创建**：
    * **标准创建**：在弹窗中选择规格，程序会自动查找或创建网络环境，并尝试创建一次。
    * **自动抢占实例 (抢机)**：针对资源稀缺区域，后台任务会持续循环尝试创建实例，直到成功为止。支持自定义重试间隔。
* **异步任务处理**：所有耗时操作（创建、抢占、实例操作）都在后台通过 Celery 任务执行，不阻塞界面。
* **任务管理与历史**：
    * 提供任务历史弹窗，永久记录所有创建和抢占任务的最终结果。
    * 即使关闭浏览器，也能回来查看任务是否成功，并找回成功实例的 Root 密码。
    * 支持查看正在运行的抢占任务，并可手动停止。
    * 支持删除已完成的任务历史记录。

## 🚀 部署教程

本教程以在一个全新的 **Ubuntu 22.04** VPS 上部署为例。

### 一、准备工作

1.  **一台 VPS**：拥有一台至少 1GB 内存的 VPS，并已配置好 SSH 登录。
2.  **OCI 账户和 API 密钥**：
    * 您需要一个 Oracle Cloud 账户。
    * 您需要为将要管理的用户生成一个 API 密钥，并记下相关的配置信息（`user` OCID, `fingerprint`, `tenancy` OCID, `region`）以及下载的 `.pem` 私钥文件。
    * 确保该用户所属的用户组拥有足够的权限策略 (Policy)。为了使用本应用的所有功能，建议授予以下权限：
        ```
        allow group <您的用户组名> to manage all-resources in tenancy
        ```
    * 如果您想精细化控制，至少需要 `manage instance-family` 和 `manage virtual-network-family` 权限。

### 二、安装步骤

#### 1. 更新系统并安装基础环境

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3-venv python3-pip redis-server nginx -y
```

#### 2、下载项目文件并设置环境

# 创建项目目录
mkdir -p /root/Oracle
cd /root/Oracle
