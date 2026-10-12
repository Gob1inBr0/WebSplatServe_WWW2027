# WebSplatServe 运行脚本

> English: [README.md](README.md)

从项目根目录运行脚本：

```powershell
cd WebSplatServe_WWW2027
```

推荐执行顺序：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/01_preflight.ps1
powershell -ExecutionPolicy Bypass -File scripts/02_start_server.ps1
powershell -ExecutionPolicy Bypass -File scripts/03_print_training_console.ps1
powershell -ExecutionPolicy Bypass -File scripts/04_export_scene.ps1 -PlyPath "C:\path\to\scene.ply" -SceneId scene_a
powershell -ExecutionPolicy Bypass -File scripts/05_run_scheduler_simulation.ps1 -SceneId scene_a
powershell -ExecutionPolicy Bypass -File scripts/06_run_policy_benchmark.ps1 -SceneId scene_a
powershell -ExecutionPolicy Bypass -File scripts/07_print_browser_benchmark_urls.ps1 -SceneId scene_a
powershell -ExecutionPolicy Bypass -File scripts/08_export_deployment_evidence.ps1
```

可选的一体化本地校验：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/09_run_all_local_checks.ps1
powershell -ExecutionPolicy Bypass -File scripts/10_smoke_local_pipeline.ps1
```

## macOS / Linux (bash)

每个脚本都有行为一致的 `.sh` 版本。解释器默认使用 `python3`，可通过环境变量 `PYTHON` 或 `--python` 参数覆盖。

```bash
cd WebSplatServe_WWW2027
bash scripts/01_preflight.sh
bash scripts/02_start_server.sh
bash scripts/03_print_training_console.sh
bash scripts/04_export_scene.sh --ply /path/to/scene.ply --scene-id scene_a
bash scripts/05_run_scheduler_simulation.sh --scene-id scene_a
bash scripts/06_run_policy_benchmark.sh --scene-id scene_a
bash scripts/07_print_browser_benchmark_urls.sh --scene-id scene_a
bash scripts/08_export_deployment_evidence.sh
bash scripts/09_run_all_local_checks.sh
bash scripts/10_smoke_local_pipeline.sh
```

说明：

- PowerShell 脚本使用 `-Named` 形式参数；bash 脚本使用 `--flag value` 形式参数。
- `02_start_server.sh` 用 `nohup` 在后台启动服务并把日志写到 `web/generated/server.log`；端口检测默认用 `lsof`（macOS 自带），并回退到 `ss`/`netstat`；健康检查用 `curl`。

说明：

- `02_start_server.ps1` 启动本地 API/静态文件服务。
- `03_print_training_console.ps1` 打印远程训练控制台地址。真正的训练仍需要在 Web 界面里填 GPU 凭据并选择算法。
- 如果已经有标准的 SH PLY，直接从 `04_export_scene.ps1` 开始。
- 浏览器 QoE 基准测试不做图像质量评估。
- `10_smoke_local_pipeline.ps1` 会在临时目录（`%TEMP%`）下生成一个合成的 SH PLY，在那里导出资源，并运行调度器/基准脚本，不需要真实场景，也不需要 `web/generated` 的写权限。
- 训练矩阵战役执行器（`campaign_runner.py`，本目录为源码副本——线上运行副本在 GPU 服务器 `/home/T0ng/campaign_runner.py`）：8 槽位队列、按空闲显存选卡（含在途预留）、tmux 启动、退出码收割、metrics 出分、`campaign_results.csv` 结果表、依赖链（LightGaussian 在 vanilla 检查点之后）。服务器上用 `/home/T0ng/start_runner.sh` 启动；状态在 `/home/T0ng/campaign/state.json`，结果在 `/home/T0ng/campaign/campaign_results.csv`。

- 开发者实例（部署数据页和遥测证据接口只在这里开放，其他实例返回 404）：单独用另一个端口启动，建议只绑本机回环：

  ```bash
  python web/server/api_server.py --host 127.0.0.1 --port 8092 --admin   # PowerShell 版支持相同参数
  ```
