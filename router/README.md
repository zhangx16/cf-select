# 路由器版 / Docker 版

适用于有 Docker 的 ARM64、AMD64 OpenWrt / Linux / NAS。默认使用 256MB 容器内存上限；上游 Go Web 程序的软内存目标为 96MiB，不要求 CPU CFS 配额支持。

## 启动 Web

在仓库根目录：

```sh
cp .env.example .env
mkdir -p data
docker compose up -d --build
```

访问 `http://127.0.0.1:13335`。要从局域网访问路由器，将 `.env` 中 `LAN_BIND_IP` 改为设备自己的局域网地址，并按需同时填写 `WEB_USERNAME`、`WEB_PASSWORD`。

Docker 构建会自动选择 ARM64 或 AMD64 程序，从上游固定版本 Release 下载并校验。如果构建环境访问 GitHub 不稳定，可先在电脑运行：

```sh
python tools/fetch_upstream.py --system linux --arch arm64
# x86 软路由把 arm64 改为 amd64
```

然后把完整源码目录（包括刚下载的 `bin/` 缓存）传到路由器构建。Alpine 软件源不可达时，可在 `.env` 配置 `APK_MIRROR=https://mirrors.ustc.edu.cn/alpine`。

## 没有 Docker Compose 的 OpenWrt

```sh
cp .env.example .env
mkdir -p data
sh router/deploy.sh
```

脚本只管理标签匹配的 `cf-select` 容器，数据保存在当前仓库的 `data/`，不依赖其他应用镜像。修改 `.env` 后重新运行该脚本即可重新创建容器。

## 启用 DNS

先把自己筛选出的香港库保存为 `data/source-ipv4.txt`。在 `.env` 填写：

```dotenv
DNS_AUTOMATION_ENABLED=true
DNS_NAME=hk.example.com
CF_API_TOKEN=
CF_ZONE_ID=
```

其中域名必须改为自己的完整子域名，Token 和 Zone ID 填自己的值。Token 限定到相应区域的 DNS 编辑权限即可。保留文件权限：`chmod 600 .env`。

```sh
docker compose up -d --force-recreate
```

如果已有验证合格的有序初始队列，将它保存为 `data/manual-priority.txt` 并设置 `INITIALIZE_FROM_ORDERED_LIST=true`；这表示允许首次启动直接把列表第一项写入 DNS。周筛仍只使用 `SOURCE_FILE`。

## 日志、状态与手动检查

```sh
docker compose logs --tail 50
docker compose exec cfdata python3 /opt/cfdata/app/dns_policy.py inspect
docker compose exec cfdata python3 /opt/cfdata/app/dns_policy.py hourly
docker compose exec cfdata python3 /opt/cfdata/app/dns_policy.py screen manual
```

无 Compose 时用 `docker exec cf-select ...`。手动 `screen` 会在有合格结果时更新自己的 DNS。

状态和凭据保存在 `data/auto-dns/`，包括 `queue.json`、`policy-state.json`、`last-health.json`、`screen-status.json`、`credentials.json` 和执行日志。保留整个 `data/` 可恢复队列和计数。

默认周日 03:17 周筛、每小时第 7 分钟巡检。时间由容器内置调度器执行，无须修改宿主机 crontab。筛选失败保留旧队列；任务有锁防重叠，巡检有带宽优先权。
