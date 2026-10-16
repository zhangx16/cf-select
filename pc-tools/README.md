# Windows 电脑辅助筛选工具

需要 Python 3.11 或更新版本，只用标准库，无须安装第三方库。
这些脚本不会登录路由器、上传文件或修改 DNS。

## 第一步：只筛 HKG

准备 `source-ipv4.txt` 放在本目录，每行一个 IPv4 CIDR（也支持 `/32`）。例如你从 CFData 项目获取的地址库；不要把别人的实测优选结果误作全部地址库。

PowerShell：

```powershell
$env:SCAN_CONCURRENCY="100"
python discover_pc.py
```

程序逐个遍历去重后的全部地址，通过 Cloudflare trace 判断 HKG，不测延迟、丢包或下载。保存 SQLite 断点，进度为 `progress.json`。正常结束生成 `hkg-all.txt`、`hkg-details.csv`；`.partial` 不是完整结果。

## 第二步：筛平均延迟低于 100ms

```powershell
$env:LATENCY_CONCURRENCY="200"
python latency_pc.py
```

输入 `hkg-all.txt`，每个地址进行 10 次 TCP443 连接测试，仅按成功连接的平均延迟严格低于 100ms 保留，不额外要求零失败。输出 `hkg-under100ms.txt` 与全部明细 `hkg-latency-details.csv`；进度 `latency-progress.json`。

完成后把选用的地址库复制到 Docker 部署目录的 `data/source-ipv4.txt`。DNS 周筛还会按 65ms、8 MB/s、10% 的部署参数再次检查。

全量任务应保持电脑运行、同一网络出口，并关闭 TUN/透明代理，避免识别到代理出口机房。并发可以按自己设备及网络调整；提高并发不保证等比例提速，也可能造成超时误判。

请保留 SQLite、原输入文件和脚本目录以便断点恢复。修改输入库后应使用新的工作目录，避免把不同任务的断点混在一起。
