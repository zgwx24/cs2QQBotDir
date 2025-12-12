# NapCat QQ GPT Bot

一个集成了 GPT API 的 QQ 机器人，可以自动接收群消息和私聊消息，并使用 GPT 进行智能回复。

## 功能

- ✅ 实时监听 QQ 消息（群消息和私聊）
- ✅ 调用 OpenAI GPT API 进行智能回复
- ✅ 支持对话历史，维持多轮对话上下文
- ✅ 自动发送回复消息
- ✅ 独立的用户对话管理

## 配置

在 `run.py` 中修改以下配置：

```python
# WebSocket 接收器配置
WS_URL = "ws://127.0.0.1:3001/ws"
WS_TOKEN = "123456"

# HTTP API 配置（发送消息）
API_URL = "http://127.0.0.1:3000"
API_TOKEN = "your-api-token"

# GPT API 配置
GPT_API_KEY = "your-openai-api-key"
GPT_MODEL = "gpt-3.5-turbo"
```

## 依赖

- websockets>=12.0,<14
- requests>=2.31.0
- openai>=1.0.0

## 使用

```bash
uv run run.py
```

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
