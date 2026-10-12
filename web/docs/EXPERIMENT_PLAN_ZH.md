# WebSplatServe WWW 2027 Industry Track 实验计划

> English: [EXPERIMENT_PLAN.md](EXPERIMENT_PLAN.md)

## 目标

WebSplatServe 评估的是 Web 原生的 3D 高斯分发服务，而不只是离线压缩质量。核心问题是：在异构的网络、视口和 GPU 约束下，浏览器能否更早呈现可用场景并保持可交互。

## 必需的基线策略

- `full`：立即请求所有数据块。近似完整场景一次性下载的压力。
- `naive`：按清单固定顺序，不做自适应。
- `bandwidth`：按每字节的收益排序。
- `viewport`：优先当前视口内可见的空间数据块。
- `gpu`：当帧时间或行数预算吃紧时放缓精细化。
- `joint`：综合使用带宽、视口、帧时间和内存信号。

## 指标

- TTFR：渲染出第一批高斯行的时间。
- 加载时间：仿真或实测的所有选中数据块到齐时间。
- 下载字节数：到每个数据块/精细化节点为止的累计传输量。
- 数据块到达曲线：随真实时间驻留在浏览器中的行数和字节数。
- FPS / P95 帧时间：来自渐进式查看器的遥测。
- 内存：驻留高斯行预算与设备类别。
- 失败率与失败阶段：部署遥测按固定枚举（`manifest | webgl | worker | chunks | internal`）聚合。
- 上限自适应：运行中控制器上调/下调点数上限的次数（每次加载的 `adapt_up` / `adapt_down` / `cap_initial` / `cap_final`）——证明客户端确实在自适应调整预算。
- 失败：数据块失败、不支持的浏览器/GPU、内存溢出或渲染失败。

## 最小实验矩阵

每种策略至少要在以下条件下运行：

- 三类客户端：桌面独立显卡、笔记本集成显卡、移动/中端设备。
- 四种网络设置：2 Mbps / 120 ms、10 Mbps / 60 ms、30 Mbps / 30 ms、100 Mbps / 10 ms。
- 三种场景规模：小、中、大高斯点数。

仓库内置 `web/config/websplatserve_profiles.json`，保证该矩阵明确且可复现。

真实浏览器实验时，客户端类别通过查看器 URL 强制指定（`profile=android_mid_range`、`profile=laptop_integrated_gpu`、`profile=desktop_discrete_gpu`），行数预算用 `maxRows=<n>` 钉死，`adapt=0` 关闭运行中的上限控制器（固定预算组）。自适应组使用默认参数（`profile=auto&adapt=1`）。

## 命令

```bash
python web/tools/export_websplatserve_assets.py /path/to/scene.ply web/generated/websplatserve/scene_a
python web/serving/adaptive_scheduler.py web/generated/websplatserve/scene_a/websplatserve_manifest.json --policy joint --bandwidth-mbps 10 --rtt-ms 60 --out-csv web/generated/experiments/joint_trace.csv
python web/tools/run_serving_benchmark.py web/generated/websplatserve/scene_a/websplatserve_manifest.json --out web/generated/experiments/serving_benchmark.csv
```

真实浏览器 QoE 轨迹（不做图像质量评估）：

```text
http://127.0.0.1:8080/web/viewers/benchmark.html?url=/web/generated/websplatserve/scene_a/manifest.json&seconds=12
```

该页面在同源 iframe 中运行所选策略，导出 TTFR、下载字节数、驻留行数、数据块到达、FPS、P95 帧时间、客户端情况和设备能力数据。

## 完整评测战役

服务评测的具体测试设计——导出校验、4320 行模拟矩阵、抽样浏览器真跑、验收
标准与限制——见 `docs/服务评测-测试设计方案.md`（v2）。战役由
`scripts/campaign_runner.py` 在 GPU 服务器上执行，仅浏览器真跑层需要本机参与。

## 部署证据

公开或内部部署期间，保持匿名遥测开启。汇总与证据接口只在 `--admin` 开发者实例上存在（单独端口、建议只绑本机回环），普通实例一律返回 404。从开发者实例拉取 `/api/telemetry/summary` 存为 JSON 后生成论文备注，或直接在控制台"部署数据"页点下载按钮：

```bash
python web/server/api_server.py --host 127.0.0.1 --port 8092 --admin
python web/tools/collect_deployment_evidence.py telemetry_summary.json --out deployment_evidence.md
```

论文产物中不要保存 IP 地址、原始 User-Agent 字符串、原始显卡型号字符串、原始场景名或用户内容。
