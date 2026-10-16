# CF Select

Cloudflare 香港 IP 筛选、健康检查和 DNS 自动切换工具，基于 [CFData-WEB v1.8.3](https://github.com/PoemMisty/CFData-WEB)。

提供两个运行入口，共用同一套 DNS 策略：

| 版本 | 适用环境 | 启动说明 |
|---|---|---|
| 路由器版 | ARM64 / AMD64 的 OpenWrt、Linux、NAS，安装 Docker | [路由器版说明](router/README.md) |
| 电脑版 | Windows 原生运行，Python 3.11+；也支持 Linux 原生入口 | [电脑版说明](desktop/README.md) |

另提供 [电脑端全量筛选工具](pc-tools/README.md)：逐个识别 HKG 地址，再按需要做延迟筛选。**不按每个 /24 随机抽样。**

本仓库不包含私人域名、Cloudflare Token、Zone ID、账号密码、实测 IP 库或运行记录。上游程序在首次启动/构建时从官方 Release 下载并进行 SHA256 校验，不直接存入 Git。

## 默认 DNS 策略

1. **每周日 03:17**，基于自己提供的 `SOURCE_FILE` 地址库重新筛选；默认时区为 `Asia/Shanghai`。
2. **每小时第 7 分钟**，检查当前 DNS 地址的 TCP 延迟、下载速度和连接失败率。
3. 三项必须同时满足：**平均成功 TCP 延迟 <65ms，下载速度 >8 MB/s，连接失败率 <10%**。
4. 新队列按 **延迟升序 → 速度降序 → 失败率升序** 排序，最多保留 100 个合格地址。
5. 当前 IP 不合格时，依次检查队列中的后续地址，验证合格后切换。
6. 自上次成功筛选后，**当前 IP 第 5 次失效立即重筛**；新队列成功发布后清零。失败候选本身不额外增加计数。
7. 队列耗尽也触发重筛；没有合格结果时保留旧队列和 DNS。

周筛只读取你配置的源库，不会拿初始 100 个备用地址充当重筛源，也不会自动遍历公网。全量发现是独立、手动启动的电脑工具。

固定使用项目“移动专属”源 `speed.okl.abrdns.com` 测速；可通过配置更换。TCP 检查默认 10 次、单次超时 1 秒；“丢包率”指 TCP 连接失败比例，并非 ICMP 丢包测量。10 次样本下，一次失败就是 10%，会被默认规则排除。

DNS 使用一条 IPv4 A 记录、仅 DNS（灰云）、TTL 300 秒。代理节点只替换连接地址，原有 SNI、Host、TLS 参数仍需正确配置。

## 使用流程

1. 选择路由器版或电脑版，先以默认设置运行 Web 页面。
2. 用自己的网络筛选 HKG 地址，将源库保存到相应数据目录的 `source-ipv4.txt`。
3. 在自己的 Cloudflare 区域创建仅具 DNS 编辑权限的 Token，填写自己的域名和 Zone ID。
4. 将 `DNS_AUTOMATION_ENABLED` 改为 `true`，重新启动。

默认 **DNS 自动化关闭**。首次开启时，程序从源库筛选后建立队列；如果已有自己验证、排序好的初始列表，可按版本说明启用 `INITIALIZE_FROM_ORDERED_LIST`，直接把第一项写入 DNS。

地址格式支持公共 IPv4，端口限定为 443：

```text
104.16.0.1/32
104.16.0.2:443#HKG
```

以上仅演示格式，不是实测推荐地址。不同网络的优选结果通常不能直接复用。

## 目录

```text
app/          共用 DNS 策略、Cloudflare API、调度器和文件锁
router/       路由器部署说明及无 Compose 部署脚本
desktop/      电脑原生启动器及配置模板
pc-tools/     全量 HKG 识别与延迟筛选工具
tools/        固定版本上游程序下载和校验
tests/        不访问 Cloudflare 的离线测试、可选本地启动测试
examples/     仅作格式演示的地址列表
```

配置文件和数据目录已加入 `.gitignore`。Linux 凭据文件权限设为 600；Windows 使用本地用户目录权限。不要把自己的 `.env` 和数据目录提交到仓库。

## 测试

```sh
python tests/test_policy.py
```

可选的原生启动测试会下载官方程序、在临时目录启动 Web，并强制关闭 DNS 自动化：

```sh
python tests/smoke_desktop.py
```

离线测试覆盖严格阈值、排序、顺序切换、第 5 次失效重筛、配置域名、文件锁和 IPv4 枚举边界。

## 来源与许可

上游：[PoemMisty/CFData-WEB](https://github.com/PoemMisty/CFData-WEB)，固定版本 `v1.8.3`。本项目增加自动化及跨平台运行入口，不修改上游 Go 程序，也不是上游官方发布。

采用 [GPL-3.0](LICENSE)。来源、对应源码及二进制校验方式见 [NOTICE.md](NOTICE.md)。
