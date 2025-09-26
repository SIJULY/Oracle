# OCI VM Management Panel (Web版) 🚀

一个基于 Python Flask 和 OCI SDK 的 Web 面板，用于在一个界面中管理 Oracle Cloud Infrastructure 实例。本项目将一个本地 Tkinter 应用成功转换为一个可远程访问、跨平台的 Web 服务。

## ✨ 特性

* **多账户管理**: 支持从标准的 OCI `config` 文件导入，并通过 Web 界面安全地管理多个账户。
* **实时状态概览**: 集中展示所有虚拟机的状态、IP、配置等关键信息。
* **完整的生命周期操作**: 支持对虚拟机进行创建、启动、停止、重启和终止。
* **后台异步任务**: 所有耗时操作都在后台执行，避免了界面卡顿，并通过轮询将结果反馈到前端。
* **一键部署脚本**: 提供 `install.sh` 脚本，可在全新的服务器上一键完成所有环境配置和部署。

## ⚙️ 第一步：获取 OCI API 凭据

在使用此面板前，您必须拥有一个标准的 OCI `config` 文件。

1.  遵循 OCI 官方文档生成 API 密钥对：[OCI Required Keys and OCIDs](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/apisigningkey.htm)。
2.  您需要准备好您的**用户OCID**、**租户OCID**、**指纹**、**区域**，以及您的**私钥文件** (`.pem`) 的路径。
3.  将这些信息整理到一个标准的 `config` 文件中（通常位于 `~/.oci/config`）。这个文件就是您之后将要导入到 Web 面板中的文件。

## 🚀 第二步：一键部署到新服务器

1.  登录一台全新的 Debian 或 Ubuntu 服务器。
2.  运行下面的一行命令，并确保将 URL 替换为您自己的 GitHub 仓库地址。

    ```bash
    git clone https://github.com/SIJULY/Oracle.git && cd Oracle && chmod +x install.sh && sudo ./install.sh
    ```

## 🖥️ 第三步：使用Web面板

1.  **访问**: 在浏览器中打开 `http://您的服务器IP`。
2.  **登录**: 使用您在 `app.py` 文件中设置的密码。
3.  **导入OCI账号**:
    * 点击“添加账号 (从INI)”并选择您本地的 OCI `config` 文件。
    * 面板会解析文件并列出所有找到的账号档案。
    * 为每个您想导入的档案设置一个易于记忆的**别名**，并填写创建实例所需的**默认子网OCID**和**默认SSH公钥**。
4.  **连接和管理**: 从下拉列表中选择一个账号别名，点击“使用选中账号”。连接成功后，实例列表将自动加载，您就可以开始管理您的VM了。

## 🛠️ 第四步：管理后台服务

* **查看状态**: `sudo systemctl status ociapp`
* **重启服务**: `sudo systemctl restart ociapp`
* **查看日志**: `sudo journalctl -u ociapp.service -f`
