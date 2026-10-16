# 电脑版（Windows 原生 / Linux 原生）

需要 Python 3.11 或更新版本。只用 Python 标准库，无须安装 Docker 或额外 Python 包。

## 启动 Web

Windows 双击 `desktop/start.cmd`，或在仓库根目录执行：

```powershell
python desktop/launch.py
```

首次会创建本地 `desktop/.env`，下载与 CPU 架构匹配的官方 CFData-WEB v1.8.3 程序，并核对 SHA256。支持 Windows AMD64 / ARM64；Linux 原生入口也可使用同一 Python 命令。默认 Web 地址为 `http://127.0.0.1:13335`。

**默认只启动 Web，不启用 DNS 更新。** 程序应保持运行；在控制台按 Ctrl+C 可停止。电脑版调度只在程序运行且电脑未休眠时执行，不会自动安装系统服务或开机任务。

配置、Web 生成文件和运行状态默认保存在 `data-desktop/`；下载程序保存在 `bin/`。均已忽略 Git 提交。

## 启用 DNS 自动化

把自己筛选的香港地址库保存为 `data-desktop/source-ipv4.txt`，修改 `desktop/.env`：

```dotenv
DNS_AUTOMATION_ENABLED=true
DNS_NAME=hk.example.com
CF_API_TOKEN=
CF_ZONE_ID=
```

改为自己的域名、Token、Zone ID 后重启。需要 Web 认证时，同时填写 `WEB_USERNAME` 和 `WEB_PASSWORD`。

若已有按期望排序且验证合格的初始列表，将其保存为 `data-desktop/manual-priority.txt`，并设置 `INITIALIZE_FROM_ORDERED_LIST=true`。此项允许首次直接写入第一项；周筛仍只从 `SOURCE_FILE` 读取。

默认 Asia/Shanghai 时区，每小时第 7 分钟巡检、每周日 03:17 周筛。可将 `TZ` 改为 `local` 使用系统时区，或改为 `UTC`；其他 IANA 时区在 Windows 上可能需要系统提供时区数据。

## 查看状态、手动执行

```powershell
python desktop/control.py inspect
python desktop/control.py hourly
python desktop/control.py screen
```

手动 `screen` 会按自己配置的规则筛选并更新 DNS。手动操作也使用任务锁，避免与定时任务重叠。

## 全量发现与延迟筛选

电脑辅助工具位于 [pc-tools/](../pc-tools/README.md)。它们独立于 DNS 调度器，适合先在电脑生成完整 HKG 库和延迟库，再复制到自己的路由器数据目录。全量任务不要开启 TUN/透明代理，避免测到代理出口的机房。

此项目没有预置任何实测 IP 或凭据，需要用自己的网络重新测量。
