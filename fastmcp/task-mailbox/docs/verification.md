# 当前验证记录

本页是本仓当前验证状态的唯一入口。状态按 `PASS`、`PARTIAL`、`FAIL`、`UNKNOWN`、`NOT_RUN` 记录，始终限定证据所属层次与调用者。保存、发送、持久接收、结果报告、实际读取及业务验收分别取证。

## 当前状态

更新：2026-11-02，Asia/Shanghai。目标仓运行代码固定为 `a06dc70e7994df7cb3c92a30cfde4276c26a5759`，初始独立来源为 `7d162860c10ac2d72719522be7fe01478f4747a3`；本轮后续改动仅为文档。除特别标明，以下现场证据由主执行侧直接取得。

| 层次 | 状态 | 已有证据与范围 |
| --- | --- | --- |
| 标准库 Store | PASS | 17 项临时 SQLite 测试；持久行为、事件去重、配额、满库回滚及旧数据保全 |
| 回环 MCP，小内容／两个模拟客户端 | PASS | VPS 临时回环实测 9 工具、收发、重复投递、摘要确认、账号拒绝及带前缀 OAuth 元数据；不代表 Dot／Mac 原生客户端 |
| 当前约 240 KiB UTF-8 样本 | UNKNOWN | 扩大上限后的重跑观察／SSH 超时，没有取得本次完整结束回执；不补造 PASS，也不派发模型 |
| OAuth 加密存储原型 | PASS | VPS 独立环境、临时目录验证加密持久化、稳定密钥重开及拒写预算；不是生产 OAuth |
| VPS 独立环境与源码 | PASS | 24 个初始来源摘要核对；独立 venv 125212 KiB，锁定依赖与专用单元已安装 |
| VPS 常驻新信箱进程 | PASS | 单元 active/running，NRestarts=0，回环受保护端点返回 401；只证明进程层 |
| 共享 HTTPS 路由与发现 | PASS | 两类 OAuth discovery 为 200 且 issuer/resource 精确匹配，MCP 未认证 POST 为 401；Caddy 校验成功、原主进程保持，旧 Gitee 路径仍为受保护 401 |
| 生产 OAuth 完整流程 | PARTIAL | 独立 App 配置存在，Mac 首次原生流程收到回调；令牌交换失败，尚无允许主体的受保护工具回读 |
| 云端私有插件登记 | PASS | 原生创建一次版本 0.1.0，回读同一插件／release 元数据；不是 Dot 发现或调用证据 |
| 云端连接 | PARTIAL | 公子回报“已连接成功”；当前执行会话未暴露信箱工具，尚无 Dot 原生 whoami／读写回执 |
| Mac Codex 配置 | PASS | 原生命令登记，回读 enabled=true、Streamable HTTP 及正确端点；不推定当前 App 会话已加载 |
| Mac Codex OAuth | FAIL | CLI 0.166.0-alpha.5.1 本地 callback 后 token exchange 报 Request failed；原因仍未定位，未自动重登或改变认证方式 |
| Mac Kimi 配置 | PASS | 委托执行侧原子写入 Kimi Code 2.4.1 用户级 MCP 文件、保留既有条目；主执行侧另行直接回读端点匹配与权限 0600 |
| Mac Kimi OAuth／工具发现 | NOT_RUN | 未启动 Kimi 新会话、登录或发现 |
| 双向 nonce 数据闭环 | NOT_RUN | 待 Dot 与指定 Mac 客户端分别实际调用、读全及核对摘要 |
| Codex App 钩子／Mac 收件桥 | NOT_RUN | 仅完成[设计评审](hooks.md)，没有启用钩子、常驻监听或自动执行 |
| Herdr／模型／业务执行 | NOT_RUN | 信箱没有执行能力；进程、HTTP 或数据闭环均不代替业务验收 |

当前运行时为 Python 3.14.4、FastMCP 4.0.11、MCP 2.3.0、uvicorn 0.54.0。真实端点、账号、插件 ID、原始输出及认证状态留在私密落点，公开文档只用别名。

## 现场资源与排障边界

部署前单次快照：总 RAM 950.5 MiB、available 658.1 MiB，根盘空闲 13031.3 MiB，1 分钟负载约 0.13。既有 Gitee venv 120.3 MiB，本服务独立 venv 122.3 MiB。早期模拟测试进程峰值 RSS 121444 KiB（约 118.6 MiB），不代表当前大样本或生产负载。

当前常驻单元回读 `MemoryPeak=125485056` 字节（约 119.7 MiB），同次 `MemoryCurrent=34807808` 字节（约 33.2 MiB），NRestarts=0。这是一个时点／启动以来峰值，不是持续余量或 24 小时稳定性验收。

Mac 登录使用客户端原生 CIMD、PKCE S256 和 read:user；临时 loopback 接收端经回读确认属于该次 Codex 登录进程。回调已返回，随后令牌交换失败。仅凭 Request failed 不能归因为回调、GitHub 配置或服务端 OAuth 拒绝。应用错误日志为空也不能证明该请求未到达（应用未启用 access log）。

不带真实 code／token 的 Mac token POST 探针返回标准 JSON 401；HTTP/1.1 与 HTTP/2 两种 curl 请求均完成。它们只证明相应探针经过入口，不代表 Codex 的 Rust HTTP 栈、实际授权码交换或云端连接。当前未读取客户端令牌缓存、未重放授权码、未开启可能记录 code／token 的认证 DEBUG 日志。

委托只读诊断在同一 Mac 使用 Codex 0.166.0-alpha.5.1 的 exec-server stdio 发送一次无凭据 dummy POST，2.767 秒返回 HTTP 发送错误，未取得状态码；OAuth／模型调用和配置变化均为 0，主执行侧回读了受限诊断产物。它复现了独立于 OAuth 业务的原生发送失败；该探针与 MCP 登录的 TLS fallback 标记不同，不能当作完整等价流程。具体 TLS／代理／路由原因仍 UNKNOWN，未据此切换配置。

## 本地 Store 验证

在仓库根执行：

```bash
python3 -m unittest discover -s tests -v
```

测试使用临时数据库与标准库，不导入 FastMCP、不调用网络、Herdr 或模型。测试数据不会成为业务任务。17 项通过仅证明已覆盖的本地行为，不能推导 VPS 磁盘恢复、OAuth 生命周期或长期在线能力。配额测试使用至多 64 KiB 预算的临时满库样本，证明新增结果失败时任务／结果／事件事务回滚且旧记录保留，并非现场故障注入。

MCP 集成验证单独在服务的独立依赖环境执行：

```bash
.venv/bin/python tests/smoke_mcp.py
.venv/bin/python tests/smoke_oauth_storage.py
```

`smoke_mcp.py` 无参数，使用临时回环端口和 StaticTokenVerifier 测试身份；通过时只证明此测试范围内的 MCP 协议与工具收发，不证明生产 OAuth、VPS 部署或 Dot 调用。不得将集成测试加入标准库测试的隐式导入路径。报告须分别保留 Store 测试、回环 MCP 测试和生产端点实际调用结果。

OAuth 存储脚本使用临时目录验证 Fernet 加密持久化、稳定密钥重开及保守拒写预算。初测由委托侧使用既有依赖完成；主执行侧随后在 VPS 新独立环境直接执行同一脚本，验证通过。两者均不构成生产授权通过。

## 资源保护的验证边界

默认配额为单份任务／结果 1 MiB、SQLite 主数据库 256 MiB、最多 10000 个 job，可配置。`mailbox_usage` 只读报告计数、数据库页使用量及上限；它不报告整个服务目录、主机磁盘或 OAuth／日志总量。任务条数满额拒绝新任务，主数据库满额拒绝无法持久化的写入，不自动删除、清理或扩大上限。

OAuth 专用存储默认采用 8 MiB／512 文件的保守拒写预算，要求单进程唯一写者，不是宿主硬配额。主进程日志为 1 MiB × 3 文件、约 3 MiB；bootstrap 错误仍进 journald。Caddy 模板限制请求体 `4MB`；本轮已安装并回读相应保护配置；尚未执行生产容量／满额故障测试。

systemd 模板的 `MemoryHigh=192M`、`MemoryMax=256M`、`CPUQuota=50%`、`TasksMax=32`、`LimitNOFILE=256` 均为保护上限，尚非实测资源保证。配置错误退出 78 不自动重启，应用不启用 HTTP access log。rollback journal、OAuth 状态、journald 和依赖不包含在主数据库 256 MiB 内；这些项目的独立容量与长期观察仍未完成。

## 端点与认证验证

依次验证：回环服务及真实 MCP 协议、外部 HTTPS 前缀、认证挑战／发现、独立 OAuth 回调、允许主体、各客户端工具发现与 `whoami`。每层保留服务版本、调用者、时间、脱敏请求引用及结果。

明确区分 systemd `active`、HTTP 返回、MCP 初始化、工具清单和工具调用；其中一项通过不能填补其他项。用户完成 OAuth 登录前，受保护工具调用保留 `NOT_RUN`；明确认证拒绝记对应分支 `FAIL`，不静默降为无认证。

独立 GitHub OAuth App 的私密配置已由公子完成，不再作为缺失项。本地 Codex 沿首次回调／交换失败定位，云端沿已登记的同一私有插件回读；不因某端失败而重建插件、绕过认证、换供应商或自动重发模型任务。下一验证是各端原生工具清单与 whoami，再做数据 nonce。

## 双向 nonce 验证

本节只验证任务和结果数据的传输，不向 Herdr、shell 或模型派发测试任务。

1. Dot 生成全新 `job_id` 与随机 nonce，按约定规范化 JSON 计算 SHA-256 后提交；保留服务返回的持久任务记录。
2. 指定 Mac 客户端主动读取事件并调用 `get_job`，核对同一 ID、payload 和摘要，记录真实读取时间。
3. Mac 使用全新稳定事件 ID 上传包含 nonce 关联和接收证据的小结果；同一事件重传只查原版本，不新增结果版本。
4. Dot 实际读取该结果，核对 ID、版本、结果摘要，再按精确版本／摘要调用 `ack_result_read`。
5. 反向使用另一个新任务：Mac 提交，Dot 主动读取并回传，Mac 实际读取并确认。两方向分别记录，不以一方调用代理另一方。

不得把 `sender` 字段、自报读取时间或中间转述当作指定客户端实际读取证据；认证主体与原生客户端回执分别保存。若当前会话只能在本地模拟两侧，结果只记录本地协议测试，Dot 端仍为 `NOT_RUN`。

发生超时或结果不明时，沿原 job／event／cursor 查询，不重建替代任务。取消工具只登记请求，不停止任何执行；读确认不代表业务采用、正式验收或写权交还。

## 后续证据写法

每次更新注明日期／时区、执行侧、版本、测试范围、原任务与事件引用、精确结果版本／摘要，以及尚未覆盖项。公开文档使用稳定别名，实际地址、账号、令牌、配置和原始输出留受限落点。

短时数据闭环不能推导 24 小时可用性。故障注入、主机重启、真实 Herdr／模型回合、业务任务或控制入口切换按各自有效授权另验，不由本页测试结果自动开启。
