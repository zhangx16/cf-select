# 来源与许可证

本项目的 DNS 自动化、跨平台调度和辅助筛选脚本以 GPL-3.0 分发，见 LICENSE。

Web 和 CLI 使用 [PoemMisty/CFData-WEB](https://github.com/PoemMisty/CFData-WEB) 的官方发行程序，固定版本 [v1.8.3](https://github.com/PoemMisty/CFData-WEB/releases/tag/v1.8.3)，不修改该 Go 程序。

本仓库不存储或再发布其编译产物。启动/构建时直接从官方 Release 下载，校验码取自该发布的 `.sha256` 文件并固定在 `tools/fetch_upstream.py` 中。这是完整性校验，不是数字签名。

- 对应项目源码：https://github.com/PoemMisty/CFData-WEB/tree/v1.8.3
- 上游 GPL-3.0 许可证：https://github.com/PoemMisty/CFData-WEB/blob/v1.8.3/LICENSE
- 上游构建依赖：https://github.com/PoemMisty/CFData-WEB/blob/v1.8.3/combined_refactor/go.mod

上游依赖 gorilla/websocket、maxminddb-golang、golang.org/x/sys 等，版权和许可归其作者。若另行再发布上游二进制，应保留相应许可并履行对应源码分发义务。

CF Select 是第三方整合，不是 CFData-WEB 原作者的官方发布，也不是 Cloudflare 官方产品。
