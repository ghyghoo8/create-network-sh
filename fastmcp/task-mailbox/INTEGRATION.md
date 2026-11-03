# Task Mailbox 在本仓的接入

本目录仅保留截至 `create-network-sh@9d36feb436264f2c0a065be7e644043a930a98dd` 的历史部署副本与接收记录。**唯一维护仓为 [CF-FE/task-mailbox-mcp](https://github.com/CF-FE/task-mailbox-mcp)**；后续功能、修复、发布与安装指引沿该仓，当前真实状态只查[主维护仓验证记录](https://github.com/CF-FE/task-mailbox-mcp/blob/main/docs/verification.md)。下文“本次／当前验证”等措辞保留当时历史语境，不在本副本维护第二份当前状态。

## 固定来源与维护

- 首次来源：[CF-FE/task-mailbox-mcp](https://github.com/CF-FE/task-mailbox-mcp)，固定提交 `7d162860c10ac2d72719522be7fe01478f4747a3`。
- 24 个源文件按原相对路径、字节及 Git mode 复制；[import-manifest.json](import-manifest.json)记录大小、SHA-256 和 Git blob。
- `INTEGRATION.md` 和来源清单是本仓接收记录，不属于源提交的 24 文件。
- 本目录不再作为后续功能或修复的维护落点；首次来源、导入 hash 和下方历史增量保留，不同步服务源码，不建立软链接、子模块、跨仓运行导入或共享虚拟环境。
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
| `fastmcp/task-mailbox/` | 旧部署代码、模板与固定来源；当前维护归 `CF-FE/task-mailbox-mcp` |
| 既有 ngrok → Caddy `127.0.0.1:19080` | 可复用公网传输入口，不替代应用认证 |
| 原 Gitee `127.0.0.1:8765` | 保留原路径、OAuth 和运行进程 |
| 信箱 `127.0.0.1:8766` | 新服务独立进程、虚拟环境和私密状态 |
| `https://mcp.example.com/mailbox/mcp` | 占位端点；部署时换为获准域名，两端完成各自 OAuth |

[Caddy 路由片段](deployment/caddy-route.example)应放在现有有序 `route` 的默认 Gitee 代理之前，包含 `/mailbox/*` 和两条前缀 OAuth discovery 路径，以及 `4MB` HTTP 包络上限。不是只加入 `/mailbox/mcp`。保留旧 `/auth/callback` 及其他服务路径；先校验再按宿主实际方式加载。

`headscale/rebuild.sh` 会生成并安装原 Headscale／Gitee 的完整 Caddyfile，它不是新信箱的安装入口。不要为加入信箱执行该重建脚本；以后重建共享入口时需显式合并信箱路由，避免覆盖已获准的新路径。`configure-shared-ngrok.py` 管理旧启停脚本的精确补丁，本次不改它或旧 Gitee 脚本。

## 运行预算与部署

默认单份内容 **1 MiB**、SQLite 主数据库 **256 MiB**、最多 **10000 个任务**；均可配置。内存保护为 `MemoryHigh=192M`／`MemoryMax=256M`，CPU 上限单核 `50%`。OAuth 专用状态采用 8 MiB／512 文件的单写者保守拒写预算；应用日志约 1 MiB × 3。主数据库上限不是整个服务的磁盘总额，大文件保留引用和摘要。

按[部署说明](docs/deployment.md)使用[宿主准备脚本](deployment/prepare-host.sh)；它只准备账户、独立依赖与单元，不启动或公开服务。独立 OAuth App 的真实凭据只在宿主 TTY 通过[交互配置辅助](deployment/configure-private.py)填写，不在聊天或仓库传递。云端、Codex、Kimi 的入口见[客户端指引](clients/README.md)。

## 本次接收与验证边界

日期：2026-11-02，Asia/Shanghai。目标工作区接收前为干净状态；本次只新增信箱目录、FastMCP 索引和根导航。没有改写 Gitee 旧来源清单、Headscale 脚本、线上配置或认证。

首次接收时，来源的[验证文档](docs/verification.md)按原字节复制；本轮已按目标仓新证据更新为唯一当前验证记录，初始字节基线仍保留在来源清单与 Git 历史。来源已有 17 项标准库测试和较小输入的回环／OAuth 存储测试；扩大单份默认值后的 VPS 重跑发生 SSH／观察超时，结果沿原临时引用对账，不能据此认定 Herdr 或 Agent 失败。本次接收不重新派发模型或业务。

目标目录已通过来源 24 文件摘要／权限与资源闭包检查、17 项标准库 Store 测试、3 项既有 Headscale 回归、Python／Shell 语法及公开内容检查。独立只读复核确认 42 个本地文档链接／锚点有效，旧 Gitee 清单和 Headscale 脚本保持原字节。上述为首次接收时的离线检查；后续进程、路由及客户端证据以[当前验证记录](docs/verification.md)为准。

首次部署准备沿既有管理入口，在 VPS 准备目标仓固定提交 `a06dc70e7994df7cb3c92a30cfde4276c26a5759` 的本服务代码；24 个来源摘要核对通过，独立依赖环境、专用账户、私密环境模板和 systemd 单元已准备，单元校验退出 0。没有启动服务或加载新公网路由，原 Gitee 未重启。独立 GitHub OAuth 应用凭据仍需在宿主交互辅助中填写，不能将这些准备记为云端已接通。

从本目录执行：

```bash
python3 -m unittest discover -s tests -v
```

MCP／加密状态测试需另用本服务独立依赖环境，不能因源码复制或离线检查通过宣布云端已经接通。

## 2026-11-02 增量：服务启动、客户端与钩子设计

运行代码仍来自本仓 `a06dc70e7994df7cb3c92a30cfde4276c26a5759`，与初次来源的运行文件一致；本次没有修改运行代码或依赖。公子完成独立 OAuth 配置后，主执行侧启动本服务，并校验、加载共享 Caddy 的新增前缀路由；Caddy 主进程保持，原 Gitee 未重启。服务、OAuth、云端与本地客户端证据汇总至 [verification.md](docs/verification.md)，实际域名、插件标识及私密配置不入仓库。

本次文档增量为 `README.md`、`SPEC.md`、`clients/README.md`、`docs/deployment.md`、`docs/verification.md` 和本接收记录，并新增 [docs/hooks.md](docs/hooks.md)作为事件与 Codex App 钩子方案。修正 README 的旧 `64 KiB` 为实际 `1 MiB`，以及 SPEC 的旧测试数；不改写 `import-manifest.json` 的初始 24 文件基线。此后的摘要差异是显式目标仓维护，不能再把当前文档字节称作初次来源原样。

钩子设计评审与当前 OAuth 排障分开：新增常驻监听、受控执行处理器、自动派发或故障注入尚未实现／部署。方案文档不扩张执行权限。

## 2026-11-02 增量：Mac 协调适配实施

实现固定提交 `10c2030d6be54c617b53d6ae86a38335975f1b3a` 新增 `mac/`、四份对应行为测试与 Mac 操作指引；VPS 运行代码／依赖和初始来源清单不变。67 项测试包含原 Store 17、Mac 台账 20、collector 17、hook 10、CLI／安装 3。Mac 依赖按实际平台另行解析和锁定，不能套用 Linux 依赖清单作为可用保证。

本轮同步维护 README、SPEC、客户端、钩子与当前验证入口。首次 portable 插件的“仅限桌面端”事实已纠正，采用公子原生注册的私有 Task Mailbox App 连接；旧包卸载归公子操作回报，新 App 元数据及当前会话受保护工具回读归主执行侧。当前状态以 [verification.md](docs/verification.md)为准，不凭任一客户端通过推导 Dot 原生读确认。
