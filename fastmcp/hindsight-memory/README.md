# Hindsight Project Memory · VPS 接入

主任务为 [Herdr Issue #13](https://github.com/CF-FE/herdr-4-codexcloud/issues/13)。本服务独立维护在 `ghyghoo8/create-network-sh/fastmcp/hindsight-memory/`；Win 源码和项目 Skill 归 [CF-FE/herdr-4-codexcloud](https://github.com/CF-FE/herdr-4-codexcloud/tree/main/mcp/hindsight-memory)。不跨仓导入、不操作其他 FastMCP 服务，也不复制 Win token、模型或数据库。

默认路径为 HTTPS MCP `/hindsight/mcp` → 固定 SSH profile → Win stdio MCP → 原 Hindsight。MCP 协议／会话无法使用时，支持的七项操作可沿相同 SSH 身份使用 Win API relay。Cloud 实际没有 MCP 注册入口时可用 HTTPS `/hindsight/api`；其 JSON 输入为 `{ "tool": "recall", "arguments": {"bank_id": "cf-fe-herdr-4-codexcloud", "query": "本任务需要核对的历史决定"} }`。API 输出保持 MCP content、structuredContent、isError，并用 `_meta.hindsight_gateway` 给出原请求及计时。

## 连接与状态

- 每次尝试创建新的 SSH/MCP 会话，失败后清理本地子进程。第二次尝试不会复用已失效会话。SSH profile 保留已有 `ConnectTimeout=30`、`ServerAliveInterval=15`、`ServerAliveCountMax=3`；Mac LAN 不变。
- 单请求最多 **2 次上游调用**，每次最多90秒，含连接和初始化；总预算180秒，第二次只获得剩余预算，退避2–5秒。Win API relay不重试，Cloud客户端不重试。平台更短上限优先。
- 网络暂时故障只沿原协议恢复；MCP会话／协议故障才切API，API不能绕过EasyTier断线。工具、认证、参数错误不通过换协议重试。
- VPS `retain` 要求调用方预置UUID `operation_id`和稳定 `document_id`。Cloud helper会在发送前补齐UUID并先输出对账标识，前端HTTP回执丢失时仍能查询。一次调用冻结所有输入；回执不明时第二次**只查询原operation**，不追加第三次写入。`SUBMITTED`仅为异步受理，完成状态由原操作查询给出。`not_found`不等于未执行。
- 无持久缓存或后台队列；无法确认时把原ID、来源、内容hash、末状态及待补摘要留在原任务。跨独立调用不能靠本服务证明UUID对应的旧内容；上游去重本身不比对内容。
- `_meta`记录连接到远端程序就绪、含SSH的MCP初始化、工具往返及总耗时。它们不是纯网络握手或模型处理时间。上游尚未提供独立API处理计时，该项为null。不会记录正文、结果或stderr。

## 认证和部署

只监听VPS loopback8767，经既有Caddy/ngrok独立分流。每个已验证主体按配置获得bank白名单和明确变更操作，默认只允许`retain`变更；bank不是授权。`list_banks`过滤掉其他bank。入口仅接受HTTPS授权，未知Origin拒绝，消息上限16MiB，最多两项在途调用。systemd限定256MiB内存，VPS不运行模型。

`deployment/`包含独立用户、systemd credential、配置和路由模板。沿已有SSH配置复制连接参数及已核known_hosts；私钥由systemd `LoadCredential`读取既有受控文件，无需复制到仓库。服务签名key独立生成，OAuth状态只放本服务私有目录。`issue_token.py`为配置中已授权服务主体向私有文件签发30天JWT，不在stdout显示令牌，不覆盖旧令牌。生产凭据、实际配置和宿主回执不得提交。

原云端Dot需要独立GitHub OAuth应用：homepage为本服务base URL，callback为`/hindsight/auth/callback`。在私有env填写新的client ID/secret，再按原客户端完成授权。未配置OAuth时，服务只支持预配JWT客户端，**不代表Dot已接入**。不复用信箱或Gitee的OAuth凭据。`FASTMCP_HOME`与其他服务分离。

部署顺序为：本目录测试和复审 → 固定Git提交/依赖锁 → 独立venv、受控配置及systemd → 验证loopback认证 → Caddy validate、固定配置备份、受支持的配置reload → 公网身份/目录/自然调用 → 各客户端分别验收。回退时移除本次专属路由并reload、停本服务、恢复`current`到前一固定发布；保留原任务证据，其他服务与Win数据不动。

## Codex Cloud

在原saved environment设置 `HINDSIGHT_VPS_API_URL=https://YOUR_ORIGIN/hindsight/api`。将独立客户端JWT作为环境自有HTTP/network secret `HINDSIGHT_VPS_TOKEN`，allowed domain只填该HTTPS域，保存后Republish。程序使用`clients/cloud_request.py`，不自己加重试。该配置不证明实际Cloud执行；下一次自然任务记录真实协议、bank、来源、operation和结果状态。默认MCP及API兜底分别验收，不创建业务测试作业。

## 验证和来源

运行 `python3 -m unittest discover -s tests -v`。单元测试使用假时钟/传输，不进行断网或进程崩溃注入。实际部署结果另在原Issue记录。`catalog.json`是M1实际`tools/list`的固定元数据快照（39工具，MCP2025-03-26），包含原开源工具说明；不含记忆内容。所有非`list_banks`工具必须具有显式bank schema，升级须重新核对目录。

依据：M1合同1.0.0（固定摘要见SOURCE.json，发布跟踪沿原Issue）、[FastMCP token verification](https://gofastmcp.com/servers/auth/token-verification)、[MCP2025-03-26](https://modelcontextprotocol.io/specification/2025-03-26)。固定来源和依赖版本见`SOURCE.json`与`requirements.lock.txt`。
