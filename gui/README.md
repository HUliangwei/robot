# robot GUI — 本地项目仪表盘

零第三方依赖（Python 标准库）的本地网页应用：浏览各小项目进度、可视化运行命令、查看产出视频与图表。

## 启动

```bash
python gui/server.py            # 默认端口 8766，自动避让被占端口
python gui/server.py --port 9000
python gui/server.py --no-browser
```

启动后自动打开浏览器 → `http://127.0.0.1:8766`。

## 功能

| 功能 | 说明 |
|---|---|
| 小项目列表 | 自动扫描 `workspace/*/`（有 commands.json 或 PROGRESS.md 即识别） |
| 进度查看 | 渲染各项目 `PROGRESS.md`（内置轻量 Markdown 渲染） |
| 命令运行 | 读取 `commands.json`，点击「▶ 运行」在本机执行（用项目 conda python + HF_HOME），输出实时流式显示，可停止 |
| 产出浏览 | 各项目 `outputs/` 下的视频/图表自动列成画廊 |
| 推理报告 | 内嵌 `docs/inference_report.html` |

## 关闭服务

三种方式：
1. **界面按钮**：左侧「⏻ 关闭服务」（推荐，优雅关闭）
2. **Ctrl+C**：前台运行时的终端里按 Ctrl+C
3. **结束进程**：任务管理器结束对应的 `python.exe`（若后台启动）

```bash
# 需要时再次启动
python gui/server.py
```

## 端口说明

- **8765 被 Videoto3D 占用**（`gui/control/server/launcher.py` 默认 port=8765）
- 本服务默认 **8766**，且启动时自动探测：若端口被占则 +1 顺延（最多 +19），并打印实际地址

## 给新小项目的接入方法

在 `workspace/<项目名>/` 下创建：
1. `PROGRESS.md` — 进度记录（GUI「进度」页读取）
2. `commands.json` — 命令清单（GUI「命令」页读取；`python` 字段会替换为实际解释器，`hf_home` 会注入环境变量）

模板见 `workspace/embodied_learning/commands.json`。
