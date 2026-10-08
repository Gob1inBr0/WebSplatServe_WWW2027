# WebScan 控制台（Console）

> English: [README.md](README.md)

Web_Scan 的新前端——为远程 3DGS 训练流程重建的精简界面。与旧版界面由同一个服务提供：

- **Console（本目录，推荐）：** `http://127.0.0.1:8080/web/console/`
- **旧版工作台（保留备用）：** `http://127.0.0.1:8080/web/`

## 功能覆盖

- **向导式训练** — 数据 → 算法 → 提交。远程环境检查和命令预览在单个确认弹窗里自动完成。
- **连接配置** — 可保存多台服务器；直接粘贴一条 SSH 命令（`ssh -p 10526 root@host`）即可自动填好各字段。密码只保存在浏览器会话里。
- **训练任务（Runs）** — 任务可命名，支持实时日志尾随、指标图表、下载进度、取消/重命名/删除，训练结束时发桌面通知。
- **数据集** — 每个任务按其数据集分组，并提供并排对比视图（渲染图 + 与最优结果的指标差值）。
- **3D 查看器** — 内置演示场景，也可快速加载本地 PLY。
- **English / 中文** — 顶栏切换，选择会被记住。

## 渐进式分发（WebGS，WWW Industry Track 规划）

控制台还承载了 WebGS 优化方案中描述的 Web 分发管线的第一个端到端片段：

- **导出** — `web/tools/export_web_assets.py`（或 `POST /api/export-web`）把训练好的 SH PLY 转换成 `manifest.json + base.bin + refinement / region chunks`（32 字节 splat 行 + 对齐的 48 浮点数 SH 行，严格只增不减）。
- **串流** — `3D Viewer → Progressive streaming` 在浏览器里播放清单：基础层先渲染出来（TTFR），精细化数据块自适应到达，并逐步追加进 WebGPU 渲染管线。
- **自适应** — 内置论文基线用的六种策略：`joint | bandwidth | viewport | gpu | naive | full`（URL 参数 `&policy=` 切换）。HUD 显示 TTFR、已下载字节、带宽估计、FPS 和 P95 帧时间。
- **遥测** — 渐进式查看器里的 `window.__webgsTelemetry()` 返回完整轨迹（TTFR、逐块到达时间、随时间变化的字节/行数、帧时间），供评估工具使用。

v1 限制：数据块格式目前只覆盖 SH（标准 3DGS 训练）的 PLY；非 SH 表示是已记录的 P2 事项。

## 内部实现

无需构建步骤。Vue 3 以源码形式放在 `assets/vue.global.prod.js`，其余都是普通 ES 模块：

```
js/app.js          入口：侧栏、顶栏、hash 路由
js/store.js        响应式状态：连接配置、轮询、通知、语言
js/api.js          后端 /api 接口的类型化封装
js/i18n.js         英/中词典（t() 从 store 读取，切换即时生效）
js/ssh-parse.js    解析粘贴的 SSH 命令
js/components/     UI 组件库 + SVG 折线图
js/pages/          仪表盘、向导、任务、数据集、查看器、设置
```

服务端会自动把 API 访问 token 注入本页面；命令行调用仍需要 `X-Auth-Token` 请求头（见主 README）。

## 范围说明

以下功能目前仍排在旧版路线图上（P2）：带自动流式上传的相机拍摄、批量任务清理、跨任务 CSV 导出、中断任务重新接入界面、流程重置/阶段性数据管理、命令覆盖编辑。在这些功能落地之前，`/web/` 的旧版界面仍是它们的备用入口。
