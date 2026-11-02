# 当前验证记录

本页是本仓当前验证状态的唯一入口。状态按 `PASS`、`PARTIAL`、`FAIL`、`UNKNOWN`、`NOT_RUN` 记录，始终限定证据所属层次与调用者。保存、发送、持久接收、结果报告、实际读取及业务验收分别取证。

## 当前状态

更新：2026-11-02，Asia/Shanghai。目标仓运行代码固定为 `a06dc70e7994df7cb3c92a30cfde4276c26a5759`，初始独立来源为 `7d162860c10ac2d72719522be7fe01478f4747a3`；Mac 初始实现为 `10c2030d6be54c617b53d6ae86a38335975f1b3a`，当前安装固定为 `6ab86765eedad995c83703aac18898b3972c77d6`，10 个源码／依赖清单文件摘要回读一致；VPS 运行代码未因本地适配改动。除特别标明，以下现场证据由主执行侧直接取得。

| 层次 | 状态 | 已有证据与范围 |
| --- | --- | --- |
| 标准库 Store | PASS | 17 项临时 SQLite 测试；持久行为、事件去重、配额、满库回滚及旧数据保全 |
| 回环 MCP，小内容／两个模拟客户端 | PASS | VPS 临时回环实测 9 工具、收发、重复投递、摘要确认、账号拒绝及带前缀 OAuth 元数据；不代表 Dot／Mac 原生客户端 |
| 当前约 240 KiB UTF-8 样本 | UNKNOWN | 扩大上限后的重跑观察／SSH 超时，没有取得本次完整结束回执；不补造 PASS，也不派发模型 |
| OAuth 加密存储原型 | PASS | VPS 独立环境、临时目录验证加密持久化、稳定密钥重开及拒写预算；不是生产 OAuth |
| VPS 独立环境与源码 | PASS | 24 个初始来源摘要核对；独立 venv 125212 KiB，锁定依赖与专用单元已安装 |
| VPS 常驻新信箱进程 | PASS | 单元 active/running，NRestarts=0，回环受保护端点返回 401；只证明进程层 |
| 共享 HTTPS 路由与发现 | PASS | 两类 OAuth discovery 为 200 且 issuer/resource 精确匹配，MCP 未认证 POST 为 401；Caddy 校验成功、原主进程保持，旧 Gitee 路径仍为受保护 401 |
| 生产 OAuth 跨客户端覆盖 | PARTIAL | 云端 App 与 Mac 桥均取得允许主体的实际工具回执；本地 Codex 原分支交换失败、Kimi 未登录，分别保留状态 |
| 旧 portable 插件 | PARTIAL | 初次包元数据上传通过，但界面显示“仅限桌面端”；公子已卸载，不再作为当前入口；未由主执行侧验证后台永久删除 |
| 新 Task Mailbox App 连接 | PASS | 公子通过原生自定义 MCP 流程创建；主执行侧回读 USER／PRIVATE、1.0.0 及原生 App 绑定，未重造服务器或复制凭据 |
| 当前桌面会话经云端 App 调用 | PASS | 9 工具已实际出现，原生 whoami／mailbox_usage 调用均成功，执行开关为 false；调用者为当前桌面会话，不冒称指定 Dot 已读 |
| 指定 Dot 只读回读（用户回报） | PASS | 公子明确转述指定云端 Dot 的 whoami／mailbox_usage 均成功；这是用户回报的 Dot 实测，不是主执行侧直接以 Dot 身份调用，也不代表原 nonce 已读取 |
| Mac Codex 配置 | PASS | 原生命令登记，回读 enabled=true、Streamable HTTP 及正确端点；不推定当前 App 会话已加载 |
| Mac Codex OAuth | FAIL | CLI 0.166.0-alpha.5.1 本地 callback 后 token exchange 报 Request failed；原因仍未定位，未自动重登或改变认证方式 |
| Mac Kimi 配置 | PASS | 委托执行侧原子写入 Kimi Code 2.4.1 用户级 MCP 文件、保留既有条目；主执行侧另行直接回读端点匹配与权限 0600 |
| Mac Kimi OAuth／工具发现 | NOT_RUN | 未启动 Kimi 新会话、登录或发现 |
| 原 nonce 结果交付与 Dot 读取 | PASS | Mac 桥收件／原事件上传 v1，当前桌面会话经云端 App 读全核摘要／nonce 并 ACK；公子另报告指定 Dot 已读取并确认，主执行侧实际回读该精确 job／版本／hash 的独立稳定 ACK 事件。Dot 行为归用户回报，事件持久记录为主执行侧直接取证；Mac 随后实际收取该 ACK，原游标推进且待处理／回传均为 0 |
| 双向 nonce 全覆盖 | PARTIAL | 上述原任务链路已通过；原任务由桌面会话经云端 App 提交，不能冒称 Dot 发起。Mac 新建任务、Dot 回报的反方向尚未执行 |
| Mac 本地实现与测试 | PASS | 完整 71 项测试：原 Store 17、台账 20、collector 17、hook 10、CLI／安装 3、浏览器交接／日志 4；主执行侧在独立 Mac 环境再次执行通过 |
| Mac 桥独立安装 | PASS | 独立源码副本、摘要回读、0700 运行目录、0600 配置／钩子定义、实际 SQLite 状态回读及 plist lint；没有启动模型／Herdr／业务 handler |
| Mac 桥依赖与加密客户端初始化 | PASS | Python 3.13.1 x86_64，FastMCP 4.0.11、MCP 2.3.0、cryptography 48.0.1，共 66 依赖；临时目录中实际构造客户端、私密权限与缺缓存拒绝测试通过，无外部请求 |
| Codex App 原生钩子触发（已观察四类） | PASS | 公子已审阅并信任已安装定义；主执行侧直接回读本地 live 台账，session 与本对话对应，观察到 SessionStart／PreToolUse／PostToolUse／UserPromptSubmit。只覆盖实际观察的四类，不推定其余三类或 CLI 模型回合已触发 |
| Mac 桥专用 OAuth | PASS | 公子再次明确要求重新授权后，同一专用客户端完成 token POST 200、后续 MCP 请求 200 及 whoami 成功；保留自有加密缓存，未改代理／TLS／端点。此前尝试的交换状态仍为历史 UNKNOWN |
| Mac 桥真实网络收件／回传 | PASS | collector 实际接收原 JOB_PERSISTED，get_job 核原 ID／payload 摘要；小结果先本地安全保存并入 outbox，再以原 event_id 上传，回执精确匹配 v1／hash。当前桌面会话经云端 App 实际读全并核对原结果后 ACK；无模型／业务派发 |
| Mac 人工收件窗口 | PASS | 手动运行 120 秒，启动 3 轮；结束时 collector=OK、待处理事件／报告均为 0，进程已自然退出。只证明此短窗口，不提升为长期在线 |
| Mac 持续收件进程 | NOT_RUN | launchd 单元已准备，RunAtLoad=false／KeepAlive=false，未 bootstrap／kickstart；授权与短窗口通过后仍未启用常驻 |
| Herdr／模型／业务执行 | NOT_RUN | 信箱没有执行能力；进程、HTTP 或数据闭环均不代替业务验收 |

VPS 当前运行时为 Python 3.14.4、FastMCP 4.0.11、MCP 2.3.0、uvicorn 0.54.0。真实端点、账号、插件 ID、原始输出及认证状态留在私密落点，公开文档只用别名。

本机 CLI 回读 `hooks stable true`，未自定义 `CODEX_HOME`，有效用户 hook 文件为 `~/.codex/hooks.json`。同一 Codex host 的 App／CLI 使用这套配置；本次真实事件来自当前 App 会话，没有运行 CLI 模型 turn，因此配置共享不能代替 CLI 原生触发验收。台账保存的是最近观察与时点，不证明原生进程持续在线或业务完成。

## 现场资源与排障边界

部署前单次快照：总 RAM 950.5 MiB、available 658.1 MiB，根盘空闲 13031.3 MiB，1 分钟负载约 0.13。既有 Gitee venv 120.3 MiB，本服务独立 venv 122.3 MiB。早期模拟测试进程峰值 RSS 121444 KiB（约 118.6 MiB），不代表当前大样本或生产负载。

本轮已回读的常驻单元快照 `MemoryPeak=125485056` 字节（约 119.7 MiB），同次 `MemoryCurrent=34807808` 字节（约 33.2 MiB），NRestarts=0。这是一个时点／启动以来峰值，不是持续余量或 24 小时稳定性验收。

Mac 登录使用客户端原生 CIMD、PKCE S256 和 read:user；临时 loopback 接收端经回读确认属于该次 Codex 登录进程。回调已返回，随后令牌交换失败。仅凭 Request failed 不能归因为回调、GitHub 配置或服务端 OAuth 拒绝。应用错误日志为空也不能证明该请求未到达（应用未启用 access log）。

不带真实 code／token 的 Mac token POST 探针返回标准 JSON 401；HTTP/1.1 与 HTTP/2 两种 curl 请求均完成。它们只证明相应探针经过入口，不代表 Codex 的 Rust HTTP 栈、实际授权码交换或云端连接。当前未读取客户端令牌缓存、未重放授权码、未开启可能记录 code／token 的认证 DEBUG 日志。

委托只读诊断在同一 Mac 使用 Codex 0.166.0-alpha.5.1 的 exec-server stdio 发送一次无凭据 dummy POST，2.767 秒返回 HTTP 发送错误，未取得状态码；OAuth／模型调用和配置变化均为 0，主执行侧回读了受限诊断产物。它复现了独立于 OAuth 业务的原生发送失败；该探针与 MCP 登录的 TLS fallback 标记不同，不能当作完整等价流程。具体 TLS／代理／路由原因仍 UNKNOWN，未据此切换配置。

Mac 桥的第二次受控登录只记录异常类型链，不记录可能含凭据的异常 str／args。另用 httpx2 做无凭据诊断：一次 issuer GET 在 2.233 秒、响应头到达前出现 RemoteProtocolError，同次 MCP POST 得到 401；随后以同一默认参数和同一发现 URL 再做一次 GET，5.043 秒得到 200，issuer 与 token endpoint 前缀正确。这些结果支持偶发传输故障的判断，未构成 OAuth 拒绝证据，也没有确定具体 TLS／代理／路由根因。没有改变代理、TLS 或端点，不能将诊断样本当作登录成功。

针对上述已复现的响应头前中断，新增仅同源两类 well-known 元数据 GET 的一次窄重试，固定 httpx2 2.16.0；两次请求共用 10 秒，不替换底层代理／TLS、不跟随重定向，也不在 HTTP 层重发任何 POST。主执行侧运行 71 项标准库回归及 9 项专用依赖假传输测试均通过，后者含实际 OAuth／MCP 共用工厂的离线接合；这些本地测试不提升授权状态；后续真实登录结果按下一段单独记录。

此前安装窄重试后的受控登录已越过元数据发现，但在 SDK 额外的授权页预检 GET 中再次出现响应头前断开，尚未打开新浏览器。已改用 SDK 支持的原生浏览器回调：只向同源 HTTPS 精确 `/authorize` 地址交接原 URL，不重复 headless 预检，保留 PKCE／state／服务端校验；worker 仍拒绝新交互。实际接合测试确认零额外 HTTP、一次原 URL 浏览器交接。为避免 SDK 异常日志包含认证响应，只记录客户端日志级别／异常类型；随后一次已打开浏览器但在传输中断后仍无 token／发现缓存；公子再次要求重新授权，同一客户端正常完成 token POST 200、后续 MCP 200 与 whoami。最后这次成功证明当前通路恢复，不反推旧授权码是否消费或旧 token 是否签发，也不构成长期稳定性证据。

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

独立 GitHub OAuth App 的私密配置和本地 hook trust 已由公子完成，不再作为缺失项。旧 portable 包已由公子卸载；新原生 App 的工具清单、whoami／usage 已由当前会话直接取得，指定 Dot 的两项只读成功另按用户回报记录。Mac 桥使用专用加密 OAuth 状态，不读取旧 Codex／Kimi 缓存或绕过认证；本桥已取得完整授权回执并沿原 nonce 完成 Mac 收件／补传及当前会话经 App 的读取确认，未重建替代任务；指定 Dot 原结果读取已有用户回报及直接事件回读，Mac 发起反方向另验。

云端只读工具成功与云端 hook 能力分开。[官方企业边界](https://learn.chatgpt.com/docs/enterprise/agent-security#hooks-in-local-computer-access-with-work-cloud)规定：相关 enterprise managed policy 和 remote hooks 启用时，Work Cloud with local access／Dot 可使用 Global `requirements.toml` 中的管理员远程 `mcp_tool` hooks；personal accounts 和无 local access 的 Work Cloud 不适用这些企业 hooks。本地 command／插件 hook 不支持云编排；当前 Dot 的企业 hook 条件未验，不承诺自动唤醒。

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

## 2026-11-02 Mac 安装与当前续测引用

实现运行目录、配置和加密状态均留本机受限位置；只观察公子选定的 Herdr／信箱项目。`SessionStart`、`UserPromptSubmit`、必要工具前后、`Stop`、`Interrupt`、`SessionEnd` 只保存关联与最近观察。结果须显式绑定 session/turn/job，Stop 成功入 outbox 后归档原件；失败保原件，不从回复或 transcript 自动生成业务结果。

依赖安装曾遇旧内网额外索引超时、PyPI 下载超时及 Linux cryptography 清单不适用于本机 Intel 二进制的问题。最终保留主框架固定版本，按 Mac 平台二进制解析并单独锁定；未更改全局源、既有客户端或系统 Rust。66 包清单见 [Mac 锁定文件](../mac/requirements.lock.macos-py313.txt)。

原 nonce 为当前桌面会话经新 App 提交的“仅数据验证”任务。Mac 桥授权成功后，collector 从原日志持久接收并实际 get_job；仅从远端取回的内容计算 nonce 摘要与反序结果，先保存本地结果和原事件 outbox，再上传 v1。主执行侧经同一云端 App 实际读取该版本，与 Mac 原件逐字段及规范化 SHA-256 核对一致，nonce 变换一致，随后登记精确版本／摘要的读 ACK。私密续测记录保留原 job、payload hash、稳定事件、结果及回执；未重建／重发任务。该链路是桌面会话经云端 App 与 Mac 桥的真实闭环；指定 Dot 自身读取已有公子明确回报，主执行侧从服务实际回读独立稳定读 ACK，原 job／v1／hash 一致；这区分用户报告的 Dot 行为与主执行侧直接取得的持久事件证据。Mac 发起反向任务仍未执行。没有 Herdr／Agent 或模型执行。

上线／清理状态：旧包卸载及指定 Dot 两项只读成功归公子回报；新 App 原生元数据／当前会话调用、四类 App hook 台账回读及 Mac 桥 OAuth／原 nonce 收件回传归主执行侧。Mac 模拟子进程／fake transport 仍只作本地测试；其余原生事件、CLI 模型触发、常驻在线、反方向及业务验收逐项未决。没有执行现场断网／崩溃注入、业务清理或任意自动派发。
