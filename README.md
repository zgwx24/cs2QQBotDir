# NapCat QQ GPT Bot

一个集成了 GPT API 的 QQ 机器人，可以自动接收群消息和私聊消息，并使用 GPT 进行智能回复。

## 功能

- ✅ 实时监听 QQ 消息（群消息和私聊）
- ✅ 调用 OpenAI GPT API 进行智能回复
- ✅ 支持对话历史，维持多轮对话上下文
- ✅ 自动发送回复消息
- ✅ 独立的用户对话管理
- ✅ 基于数字账号的群聊白名单机制
- ✅ 管理员动态添加白名单用户

## 配置

在 `qqbot.py` 中修改以下配置：

```python
# WebSocket 接收器配置
WS_URL = "ws://127.0.0.1:3001/ws"
WS_TOKEN = "your websocket token created and copied from napcat webui"

# HTTP API 配置（发送消息）
API_URL = "http://127.0.0.1:3000"
API_TOKEN = "your-api-token "

# GPT API 配置
GPT_API_KEY = "your-openai-api-key"
GPT_MODEL = "gpt-3.5-turbo"
```

### 群聊白名单配置

```python
# 群号白名单（只有这些群启用 Bot 功能）
GROUP_WHITELIST = [
    152103400,  # 群号1
    615988021,  # 群号2
]

# 用户白名单（基于群号的数字账号白名单）
USER_WHITELIST = {
    152103400: [123456789, 987654321],  # 群号: [QQ号列表]
    615988021: [111111111],
}

# 管理员账号（用于动态添加白名单）
ADMIN_ACCOUNT = 0  # 请填写你的QQ号

# 触发添加白名单的关键词
ADD_WHITELIST_KEYWORDS = ["攻击他", "给我上", "加入白名单"]
```

### 白名单使用说明

1. **手动配置**：在 `USER_WHITELIST` 中直接添加群号和用户 QQ 号
2. **动态添加**：管理员（`ADMIN_ACCOUNT`）在群里发送消息，格式为：
   - 先 @mention 想要添加的用户
   - 然后说出触发词，如"攻击他"、"给我上"或"加入白名单"
   - 例如：`@用户 攻击他` 或 `@用户 给我上`

示例：
```
管理员: @小明 攻击他
Bot: ✓ 已添加用户小明的QQ到白名单
```

## 依赖

- websockets>=12.0,<14
- requests>=2.31.0
- openai>=1.0.0

## 使用

```bash
uv run run.py
```

## MCP Integration

Two helper modules provide MCP connectivity so `qqbot.py` can call tools:

- `mcp_comm.py`: Lightweight async wrapper with `MCPClient.call_tool()` and `list_tools()`.
- `mcp_registry.py`: Registry and `build_http_transport()` to register servers.

### Quick Start (File-based config)

1. Define MCP servers in [cs2QQBotDirector/mcp_servers.json](cs2QQBotDirector/mcp_servers.json):

```
{
	"servers": [
		{ "id": "weather", "type": "http", "base_url": "http://localhost:8080" }
	]
}
```

2. Use in `qqbot.py`:

```python
from mcp_registry import default_registry
from mcp_comm import MCPClient

reg = default_registry("mcp_servers.json")
client = MCPClient(reg.get_transport("weather"))
result = await client.call_tool("weather", "get_forecast", {"city": "Tokyo"})
```

You can add more servers via `MCPRegistry.register()`.
## 工作流程

1. Bot 启动并连接到 NapCat WebSocket 服务
2. 监听 QQ 群消息和私聊消息
3. 接收消息后，调用 OpenAI GPT API 获取回复
4. 通过 NapCat HTTP API 将回复发送回 QQ
5. 维持对话历史以支持多轮交互

## 注意事项

- 需要配置有效的 OpenAI API Key
- 需要 NapCat 服务在 `127.0.0.1:3001` 和 `127.0.0.1:3000` 运行
- API 调用会产生费用，注意 API 额度
