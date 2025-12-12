import asyncio
import websockets
import json
import requests
from openai import OpenAI
import os
from dotenv import load_dotenv

# ==================== 配置 ====================
load_dotenv()

WS_URL = os.getenv("WS_URL")
WS_TOKEN = os.getenv("WS_TOKEN")    
API_URL = os.getenv("API_URL")
API_TOKEN = os.getenv("API_TOKEN")
GPT_API_KEY = os.getenv("GPT_API_KEY")
GPT_MODEL = os.getenv("GPT_MODEL", "gpt-3.5-turbo")


# ==================== 群白名单配置 ====================
# 只有在这个列表中的群号才会启用 Bot 功能
GROUP_WHITELIST = [
    694590185,  # 群号 1
    1032758463
    # 添加更多群号...
]
# 设置为 None 或 [] 表示全部群都启用
# GROUP_WHITELIST = None  # 或者 GROUP_WHITELIST = []

# ==================== 全局变量 ====================
client = None
conversation_history = {}  # 存储对话历史


def init_gpt_client():
    """初始化 GPT 客户端"""
    global client
    client = OpenAI(api_key=GPT_API_KEY)
    print("✓ GPT 客户端初始化成功")


def get_gpt_response(user_id, message):
    """调用 GPT API 获取回复"""
    try:
        # 初始化用户对话历史
        if user_id not in conversation_history:
            conversation_history[user_id] = []
        
        # 添加用户消息到历史
        conversation_history[user_id].append({
            "role": "user",
            "content": message
        })
        
        # 调用 GPT API
        response = client.chat.completions.create(
            model=GPT_MODEL,
            messages=conversation_history[user_id],
            max_tokens=500,
            temperature=0.7
        )
        
        # 获取回复
        reply = response.choices[0].message.content
        
        # 保存助手回复到历史
        conversation_history[user_id].append({
            "role": "assistant",
            "content": reply
        })
        
        # 只保留最近 10 条消息，防止历史过长
        if len(conversation_history[user_id]) > 20:
            conversation_history[user_id] = conversation_history[user_id][-20:]
        
        return reply
    
    except Exception as e:
        return f"GPT 调用失败: {str(e)}"


def send_group_message(group_id, message):
    """发送群组消息"""
    try:
        url = f"{API_URL}/send_group_msg"
        headers = {
            "Authorization": f"Bearer {API_TOKEN}",
            "Content-Type": "application/json"
        }
        data = {
            "group_id": group_id,
            "message": message
        }
        response = requests.post(url, json=data, headers=headers)
        print(f"✓ 群消息已发送: {message[:50]}...")
        return response.json()
    except Exception as e:
        print(f"✗ 发送群消息失败: {str(e)}")
        return None


def send_private_message(user_id, message):
    """发送私聊消息"""
    try:
        url = f"{API_URL}/send_private_msg"
        headers = {
            "Authorization": f"Bearer {API_TOKEN}",
            "Content-Type": "application/json"
        }
        data = {
            "user_id": user_id,
            "message": message
        }
        response = requests.post(url, json=data, headers=headers)
        print(f"✓ 私信已发送: {message[:50]}...")
        return response.json()
    except Exception as e:
        print(f"✗ 发送私信失败: {str(e)}")
        return None


def is_mentioned(data):
    """检查机器人是否被@了"""
    self_id = data.get("self_id")
    raw_message = data.get("raw_message", "")
    
    # 方法 1: 检查 CQCode 格式的 @ ([CQ:at,qq=xxxxx])
    if f"[CQ:at,qq={self_id}]" in raw_message:
        return True
    
    # 方法 2: 检查 message 数组格式（如果支持的话）
    message = data.get("message", [])
    if isinstance(message, list):
        for item in message:
            if item.get("type") == "at" and item.get("data", {}).get("qq") == self_id:
                return True
    
    return False


def extract_text_from_message(raw_message):
    """从消息中提取纯文本内容（去掉 CQCode）"""
    import re
    # 移除所有 CQCode，如 [CQ:at,qq=xxxxx]、[CQ:image,file=xxx] 等
    text = re.sub(r'\[CQ:[^\]]+\]', '', raw_message)
    return text.strip()


def is_group_whitelisted(group_id):
    """检查群号是否在白名单中"""
    # 如果白名单为空或 None，允许所有群
    if not GROUP_WHITELIST:
        return True
    
    # 检查群号是否在白名单中
    return group_id in GROUP_WHITELIST


async def listen_and_respond():
    """监听消息并使用 GPT 回复"""
    extra_headers = [("Authorization", f"Bearer {WS_TOKEN}")]
    
    try:
        async with websockets.connect(WS_URL, extra_headers=extra_headers) as ws:
            print("✓ WebSocket 连接成功，等待消息...")
            while True:
                message = await ws.recv()
                data = json.loads(message)
                
                # 只处理消息事件
                if data.get("post_type") == "message":
                    msg_type = data.get("message_type")
                    
                    if msg_type == "group":
                        # 群消息处理
                        group_id = data.get("group_id")
                        user_id = data.get("user_id")
                        self_id = data.get("self_id")
                        raw_message = data.get("raw_message", "")
                        message_data = data.get("message", [])
                        
                        # 🔍 调试：打印完整消息结构
                        print(f"\n📨 群消息 [{group_id}] 来自用户 {user_id}:")
                        print(f"   Raw: {raw_message}")
                        print(f"   Message 结构: {message_data}")
                        print(f"   Self ID: {self_id}")
                        
                        # ✅ 检查群号是否在白名单中
                        if not is_group_whitelisted(group_id):
                            print(f"   ❌ 群号不在白名单中，跳过处理")
                            continue
                        
                        # ✅ 检查是否被@了（改进版）
                        mentioned = is_mentioned(data)
                        print(f"   @检测结果: {mentioned}")
                        
                        if mentioned:
                            # 提取纯文本内容（去掉@标签）
                            text_content = extract_text_from_message(raw_message)
                            
                            print(f"   ✅ 被@了，调用 GPT...")
                            print(f"   提取内容: {text_content}")
                            
                            # 调用 GPT 获取回复
                            gpt_reply = get_gpt_response(f"group_{group_id}_{user_id}", text_content)
                            print(f"   GPT 回复: {gpt_reply}")
                            
                            # 发送回复
                            send_group_message(group_id, gpt_reply)
                        else:
                            print(f"   ⏭️  未被@，跳过处理")
                    
                    elif msg_type == "private":
                        # 私聊消息处理（私聊总是回复，不需要@）
                        user_id = data.get("user_id")
                        raw_message = data.get("raw_message", "")
                        
                        print(f"\n💬 私信 来自用户 {user_id}:")
                        print(f"   内容: {raw_message}")
                        print(f"   调用 GPT...")
                        
                        # 调用 GPT 获取回复
                        gpt_reply = get_gpt_response(f"private_{user_id}", raw_message)
                        print(f"   GPT 回复: {gpt_reply}")
                        
                        # 发送回复
                        send_private_message(user_id, gpt_reply)
    
    except websockets.exceptions.ConnectionClosed:
        print("✗ WebSocket 连接已关闭")
    except Exception as e:
        print(f"✗ 错误: {str(e)}")


async def main():
    """主函数"""
    print("=" * 50)
    print("   CS2 QQBOT导 启动")
    print("=" * 50)
    
    init_gpt_client()
    await listen_and_respond()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n[已停止] Bot 已关闭")
