# 部署指南（WebGS P1）

> English: [DEPLOYMENT.md](DEPLOYMENT.md)

如何把 Web_Scan 跑成一个公网可访问的服务演示，并采集 WWW Industry Track 投稿所需的线上运行遥测作为部署证据。以下所有步骤都不需要改代码；遥测管线是内置的（`web/server/telemetry.py`）。

## 1. 以真实使用方式运行服务

```bash
./start_webserver.sh                       # 本机，端口 8080
python3 web/server/api_server.py \
  --host 0.0.0.0 --port 8080 \
  --allowed-host your.domain.example       # 接受公网的 Host 头
```

- API 访问 token 首次生成后写入 `web/config/server.token`，并自动注入到被服务的页面里。凡是能从公网访问的部署都要保持 token 鉴权开启（`--no-auth` 仅用于本地测试）。
- 公开演示请在前面架一个带 HTTPS 的反向代理，例如 Caddy：

```
your.domain.example {
    reverse_proxy 127.0.0.1:8080
}
```

- `./stop_webserver.sh`（或控制台的停止按钮）停止服务。
- 要拿到连续数周的运行证据，请把服务挂到服务管理器下运行，例如用一个 launchd plist / systemd unit 执行 `start_webserver.sh` 并在退出时自动重启。遥测汇总里会报告每个进程的 `uptime_seconds`。

## 2. 采集哪些遥测（以及不采集哪些）

匿名记录到 `web/generated/telemetry/` 下的每日 JSONL 文件：

| 事件 | 时机 | 关键字段 |
|---|---|---|
| `server_start` | 进程启动 | 主机、端口、鉴权模式 |
| `page_view` | 控制台/工作台被打开 | 粗粒度设备类别（浏览器/操作系统/移动或桌面） |
| `http_request` | 每个响应 | 方法、路径**分桶**（绝不记录原始路径）、状态码、延迟毫秒、输出字节数 |
| `serving_load` | 渐进式查看器：首次渲染、全部数据块就绪或失败 | 策略、TTFR、字节数、行数、数据块失败数、失败阶段、设备类别 |
| `export_web` | `POST /api/export-web` | 成功/失败、错误类别、行数、数据块数、耗时 |

不记录：IP 地址、原始 User-Agent 字符串、场景/文件名、用户内容，以及服务所访问的其他机器上的任何数据。

用 `WEBSGS_TELEMETRY=0` 或 `web/config/security.json` 中的 `{"telemetry_enabled": false}` 可关闭遥测（需重启生效）。保留期默认 30 天（`WEBSGS_TELEMETRY_RETENTION_DAYS` 可改）。客户端上报不需要 token，但受白名单和取值范围校验，并同样通过同源检查；汇总接口和所有 `/api` 路由一样需要 token，原始 JSONL 文件不对外静态服务。

## 3. 导出部署证据

```bash
TOKEN=$(cat web/config/server.token)
curl -H "X-Auth-Token: $TOKEN" http://127.0.0.1:8080/api/telemetry/summary | python3 -m json.tool
```

这份汇总直接回答 Industry Track 关心的问题：

- 会话与受众 — `events_by_day`、`clients.*`（设备/浏览器/操作系统构成）
- 服务了什么 — `http.requests`、`http.bytes_served`、`events_by_type`
- 响应速度 — `http.latency_ms`（p50/p95）、`serving.ttfr_ms`（p50/p95）、`serving.p95_frame_ms`
- 可靠性 — `http.status`（4xx/5xx 计数）、`serving.failures_by_stage`、`exports.failures_by_error`、`http.recent_failures`、`uptime_seconds`

写论文时：定期快照这份 JSON（用 cron 定时追加到文件），这样能画出数周的运行曲线。失败案例分析（P1）使用 `serving.failures_by_stage` + `exports.failures_by_error` + 查看器自身的遥测导出（浏览器控制台里的 `window.__webgsTelemetry()`）来获得逐次加载的轨迹。

## 4. 新部署的冒烟检查清单

1. 打开控制台，在一台已连接的 GPU 主机上提交一个训练/压缩任务。
2. 导出一个场景（`POST /api/export-web` 或控制台按钮），打开渐进式查看器链接；确认首帧渲染出现在全部数据块完成之前。
3. `curl -H "X-Auth-Token: $TOKEN" .../api/telemetry/summary` 能看到你刚产生的 `serving_load` 事件，TTFR 数值合理。
4. 确认 `https://.../web/generated/telemetry/...` 返回 404（这些文件只在服务端，不对外提供）。
