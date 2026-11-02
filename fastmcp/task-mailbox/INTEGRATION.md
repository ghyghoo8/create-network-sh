# Task Mailbox 在本仓的接入

本目录按公子要求纳入当前 MCP 服务，包含源码、测试、依赖锁、部署脚本、文档和云端／本地客户端配置模板，可从本目录独立工作，不依赖另一份本地 checkout。

## 固定来源与维护

- 首次来源：[CF-FE/task-mailbox-mcp](https://github.com/CF-FE/task-mailbox-mcp)，固定提交 `7d162860c10ac2d72719522be7fe01478f4747a3`。
- 24 个源文件按原相对路径、字节及 Git mode 复制；[import-manifest.json](import-manifest.json)记录大小、SHA-256 和 Git blob。
- `INTEGRATION.md` 和来源清单是本仓接收记录，不属于源提交的 24 文件。
- 本目录独立维护；首次来源记录保留。后续同步须显式记录版本和增量，不建立软链接、子模块、跨仓运行导入、共享虚拟环境或自动同步。
- 原独立仓库保留初始化来源；本次没有删除仓库或迁移实际运行数据。

```text
ARCHITECTURE TRIAGE
Path: DIRECT
Evidence: fastmcp/gitee/README.md and its import-manifest pattern;
          task-mailbox source at the fixed commit; headscale/rebuild.sh routing.
Boundary impact: independent source directory and documentation only;
                 task/OAuth ownership and runtime contracts remain unchanged.
Next action: copy and verify the closed source set, then index it in this repo.
```

## 服务与既有入口

本服务只持久收发任务与结果，不执行任务、不唤醒 Agent，不替代 Mac Herdr 的机器控制入口。功能和工具见[服务 README](README.md)、[契约](SPEC.md)。

| 位置 | 归属 |
| --- | --- |
| `fastmcp/gitee/` | 原 Gitee 参考资料，保留自己的认证和部署逻辑 |
| `fastmcp/task-mailbox/` | 本信箱服务的可部署源码与模板 |
| 既有 ngrok → Caddy `127.0.0.1:19080` | 可复用公网传输入口，不替代应用认证 |
| 原 Gitee `127.0.0.1:8765` | 保留原路径、OAuth 和运行进程 |
| 信箱候选 `127.0.0.1:8766` | 新服务独立进程、虚拟环境和私密状态 |
| `https://mcp.example.com/mailbox/mcp` | 占位端点；部署时换为获准域名，两端完成各自 OAuth |

[Caddy 路由片段](deployment/caddy-route.example)应放在现有有序 `route` 的默认 Gitee 代理之前，包含 `/mailbox/*` 和两条前缀 OAuth discovery 路径，以及 `4MB` HTTP 包络上限。不是只加入 `/mailbox/mcp`。保留旧 `/auth/callback` 及其他服务路径；先校验再按宿主实际方式加载。

`headscale/rebuild.sh` 会生成并安装原 Headscale／Gitee 的完整 Caddyfile，它不是新信箱的安装入口。不要为加入信箱执行该重建脚本；以后重建共享入口时需显式合并信箱路由，避免覆盖已获准的新路径。`configure-shared-ngrok.py` 管理旧启停脚本的精确补丁，本次不改它或旧 Gitee 脚本。

## 运行预算与部署

默认单份内容 **1 MiB**、SQLite 主数据库 **256 MiB**、最多 **10000 个任务**；均可配置。内存保护为 `MemoryHigh=192M`／`MemoryMax=256M`，CPU 上限单核 `50%`。OAuth 专用状态采用 8 MiB／512 文件的单写者保守拒写预算；应用日志约 1 MiB × 3。主数据库上限不是整个服务的磁盘总额，大文件保留引用和摘要。

按[部署说明](docs/deployment.md)使用[宿主准备脚本](deployment/prepare-host.sh)；它只准备账户、独立依赖与单元，不启动或公开服务。独立 OAuth App 的真实凭据只在宿主 TTY 通过[交互配置辅助](deployment/configure-private.py)填写，不在聊天或仓库传递。云端、Codex、Kimi 的入口见[客户端指引](clients/README.md)。

## 本次接收与验证边界

日期：2026-11-02，Asia/Shanghai。目标工作区接收前为干净状态；本次只新增信箱目录、FastMCP 索引和根导航。没有改写 Gitee 旧来源清单、Headscale 脚本、线上配置或认证。

来源的[验证文档](docs/verification.md)按原字节保留，是来源执行记录，不冒充目标仓或本轮现场验收。来源已有 17 项标准库测试和较小输入的回环／OAuth 存储测试；扩大单份默认值后的 VPS 重跑发生 SSH／观察超时，结果沿原临时引用对账，不能据此认定 Herdr 或 Agent 失败。本次接收不重新派发模型或业务。

目标目录已通过来源 24 文件摘要／权限与资源闭包检查、17 项标准库 Store 测试、3 项既有 Headscale 回归、Python／Shell 语法及公开内容检查。独立只读复核确认 42 个本地文档链接／锚点有效，旧 Gitee 清单和 Headscale 脚本保持原字节。生产 OAuth、常驻进程、公网端点、Dot 与本地客户端真实双向读取及业务验收继续分别为未验。

本轮另已沿既有管理入口，在 VPS 准备目标仓固定提交 `a06dc70e7994df7cb3c92a30cfde4276c26a5759` 的本服务代码；24 个来源摘要核对通过，独立依赖环境、专用账户、私密环境模板和 systemd 单元已准备，单元校验退出 0。没有启动服务或加载新公网路由，原 Gitee 未重启。独立 GitHub OAuth 应用凭据仍需在宿主交互辅助中填写，不能将这些准备记为云端已接通。

从本目录执行：

```bash
python3 -m unittest discover -s tests -v
```

MCP／加密状态测试需另用本服务独立依赖环境，不能因源码复制或离线检查通过宣布云端已经接通。
