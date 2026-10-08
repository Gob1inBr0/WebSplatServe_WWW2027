# 高斯编码 Web 平台

> English: [README.md](README.md)

## 概述

本目录提供一套独立的 Web 平台，作为多种高斯编码与重建算法的统一可视化入口。

## 用户手册

### 📖 文档导航

**按需从这里开始：**

#### 🚀 环境搭建与配置
- **远程 SSH 环境配置**（远程训练推荐）
  - 快速导航：[`project_md/REMOTE_SETUP_INDEX.md`](project_md/REMOTE_SETUP_INDEX.md)
  - 新算法（Gaussian Splatting Lightning、HAC-plus、FCGS、ContextGS、CompGS、reduced-3dgs、MEGS-2、GaussianPro、AtomGS）：[`project_md/REMOTE_SETUP_GUIDE_NEW.md`](project_md/REMOTE_SETUP_GUIDE_NEW.md)
  - 旧算法（Scaffold-GS）：[`project_md/REMOTE_SETUP_GUIDE_OLD.md`](project_md/REMOTE_SETUP_GUIDE_OLD.md)
  - 校验脚本：[`tools/remote_verify_setup.sh`](tools/remote_verify_setup.sh)

#### 🎯 Web 应用训练
- 中文：[`WEB_TRAINING_MANUAL_ZH.md`](WEB_TRAINING_MANUAL_ZH.md)
- English: [`WEB_TRAINING_MANUAL_EN.md`](WEB_TRAINING_MANUAL_EN.md)

## 基本功能

平台目前提供以下核心功能：

- 场景加载与渲染
  - 单入口页面：`index.html`
  - 场景清单加载
  - 渲染器注册表
  - SH / SG 两条查看器路径
  - 旧版查看器通过 `iframe + postMessage` 与控制面板联动

- 算法管理与任务调度
  - 调研方法注册表
  - 基于配置文件的多仓库适配器注册表
  - 服务端导出接口与算法任务 API
  - 采集流程脚本生成与执行
  - 环境自检与运行就绪校验
  - 按状态展开/折叠的引导式流程
  - 远程优先的流程分区，另设可选的本地调试分组
  - 场景分享链接与任务监控

- 实时输入与结果展示
  - 相机拍摄
  - 图片上传
  - 流式上传
  - 采集会话组装成多帧数据集
  - 自动准备 COLMAP 工作区
  - 双栏实时工作区（采集/结果）
  - 双模式结果展示：结果图片或交互式结构查看器
  - 内置远程训练模式（SSH/SFTP），自动下载输出

- 指标与状态监控
  - 算法任务指标抽取，前端实时展示
  - 查看器侧指标：`FPS`、`Vertices`、`Progress`
  - 算法侧指标：`Algo FPS`、`Loss`、`PSNR`、`Iter`
  - 持久化的任务运行日志（`.log`）与指标历史（`.csv`）
  - 前端日志尾随 + 分页指标表 + 一键下载

## 运行

建议使用内置的 API 与静态文件服务：

安装远程模式依赖：

```bash
python -m pip install paramiko
```

### ⚠️ 远程训练之前

**重要**：使用远程训练功能之前，先配置好远程服务器环境：

1. **选择算法系列**：
   - HAC-plus、FCGS、ContextGS、CompGS、reduced-3dgs、MEGS-2、GaussianPro、AtomGS 或 Gaussian Splatting Lightning？→ 见 [`project_md/REMOTE_SETUP_GUIDE_NEW.md`](project_md/REMOTE_SETUP_GUIDE_NEW.md)
   - 旧版 Scaffold-GS？→ 见 [`project_md/REMOTE_SETUP_GUIDE_OLD.md`](project_md/REMOTE_SETUP_GUIDE_OLD.md)

2. **校验环境配置**：
   ```bash
   bash web/tools/remote_verify_setup.sh
   ```

3. **参考完整清单**：
   - 中文（HAC++）：[`WEB_TRAINING_MANUAL_ZH.md`](WEB_TRAINING_MANUAL_ZH.md)
   - 英文（HAC++）：[`WEB_TRAINING_MANUAL_EN.md`](WEB_TRAINING_MANUAL_EN.md)

### 启动服务

```bash
python3 web/server/api_server.py --host 127.0.0.1 --port 8080
```

然后打开：

```
http://127.0.0.1:8080/web/
```

也可以通过分享链接打开指定的清单：

```
http://127.0.0.1:8080/web/?manifest=/web/generated/scene_a/scene_manifest.json
```

## 端到端流程

Web 界面覆盖以下流程：

1. 在 `Runtime Config` 中检查 API 并校验适配器。
2. 在 `Capture` 中至少采集一帧。
3. 在 `Remote Training Config` 中填写远程凭据和路径。点击提交之前，先按训练手册跑一遍所选算法的预检清单。
4. 在 `Remote Run` 中点击 `One-click Upload and Remote Train`。
5. 后端依次执行：上传帧 -> 组装会话 -> 远程训练 -> 下载输出。
6. 前端轮询任务状态、更新指标，并自动把查看器切换到最新结果。
7. 打开 `System Board -> Job Logs and Metrics` 查看日志尾随、分页指标行，并下载 `.log/.csv`。
8. 可选：用 `Local Debug (Optional)` 做本地后备操作。

### 补充采集流程

- 浏览器采集相机帧或上传图片。
- 服务端把帧存到 `web/generated/streams/<session_id>/input/`。
- `POST /api/materialize-session` 把采集会话组装成数据集，放在 `web/generated/datasets/<session_id>/`。
- 前端可以用这些路径自动填充任务表单，用于 COLMAP / 训练流程。
- `POST /api/prepare-colmap-workspace` 可以准备 COLMAP 工作区及相关文件。

### 实时处理

- 浏览器把帧发送到 `POST /api/stream-frame`。
- 服务端保存帧，并提供 `process_frame` 调度入口。
- 如果适配器定义了 `process_frame` 模板，服务端会触发后端算法处理该帧并返回结果。
- 前端轮询并在结果可用时展示处理后的图片或交互式场景。

### 一键远程训练

- 在 `Remote Training Config` 中填写远程凭据和路径。
- 在 `Remote Run` 中点击 `One-click Upload and Remote Train`。
- 流程为：帧上传 -> 自动组装会话 -> 远程训练 -> 自动下载输出 -> 自动渲染。

### 任务日志与指标下载

- `GET /api/jobs/<job_id>/logs?page=1&page_size=20&tail_lines=120`
  - 返回分页指标行和原始日志尾随。
- `GET /api/jobs/<job_id>/logs/download`
  - 下载持久化的运行日志（`.log`）。
- `GET /api/jobs/<job_id>/metrics.csv`
  - 下载指标历史（`.csv`）。

前端 `Job Logs and Metrics` 面板直接绑定这些接口，并支持分页。

## 运行时检查

页面对以下工具做环境检查：

- `python3`
- `colmap`
- `nvidia-smi`
- `magick`

系统区分两种就绪状态：

- `web_runnable`：Web 服务本身能否启动
- `pipeline_ready`：算法流程是否具备运行所需的环境

远程模式下，网络/鉴权/路径检查在任务提交时进行校验。

## 适配器注册表

适配器配置在：

```
web/config/algorithm_adapters.json
```

每个适配器条目应提供 `family`、`repo_path`、`repo_url`、`representation`、`operations` 和 `default_cwd`。前端读取该配置来展示和切换算法。

## 实时桥接约定

平台使用的实时输入/输出约定：

- 输入帧上传到：`web/generated/streams/<session_id>/input/`
- 处理输出应写到：`web/generated/streams/<session_id>/output/latest.png`
- 如果产出了可交互的高斯结构，放置以下之一：
  - `web/generated/streams/<session_id>/output/point_cloud.ply`
  - `web/generated/streams/<session_id>/output/latest.ply`
  - `web/generated/streams/<session_id>/output/scene.ply`
  - `web/generated/streams/<session_id>/output/scene_manifest.json`
- 结构化指标可写到同一输出目录下的 `metrics.json`。

服务端监视 stdout/stderr、`metrics.json`、`latest.png` 以及 `.ply` / `scene_manifest.json`，并把更新转发给前端。

## 场景清单示例

见 `src/loaders/scene-manifest-loader.js` 中的 `manifestSchemaExample()`。
