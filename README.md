# OCI Web Panel - 一款强大的 Oracle Cloud 实例 Web 管理面板

这是一个基于 **Flask** 和 **Celery** 构建的 Web 应用，旨在提供一个图形化界面，用于管理 **Oracle Cloud Infrastructure (OCI)** 上的计算实例。
它特别适合需要频繁创建、管理或“抢占”稀缺实例资源的用户。


## ✨一键安装脚本：
```bash
bash <(curl -fsSL https://raw.githubusercontent.com/SIJULY/Oracle/main/docker-install.sh)
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

    
3. **具体如何获取上述信息可按照下面教程操作**：
   
<img width="1600" height="1000" alt="image" src="https://github.com/user-attachments/assets/e482977d-b220-4c26-9f1e-5b8d2c84a06f" />

<img width="1600" height="1000" alt="image" src="https://github.com/user-attachments/assets/517f4bad-5382-452b-8e4c-886877c22aac" />

<img width="1600" height="1000" alt="image" src="https://github.com/user-attachments/assets/7d2901e2-be6f-4a58-8e80-b1cdfb204436" />

<img width="1482" height="1022" alt="image" src="https://github.com/user-attachments/assets/2b4df7ca-d221-455e-867a-c33b964c6537" />

<img width="1896" height="1150" alt="image" src="https://github.com/user-attachments/assets/b8e46ba5-f1e2-48d3-8aa4-f244bd893de7" />

  **用文本编辑器打开SSH公钥复制到网页提示的输入框中**：






---

