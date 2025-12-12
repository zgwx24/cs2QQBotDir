import argparse
import asyncio
import websockets
import json
import requests
from openai import OpenAI
import os
from dotenv import load_dotenv
from pathlib import Path


# ==================== 配置 ====================
load_dotenv()

WS_URL = os.getenv("WS_URL")
WS_TOKEN = os.getenv("WS_TOKEN")    
API_URL = os.getenv("API_URL")
API_TOKEN = os.getenv("API_TOKEN")
GPT_API_KEY = os.getenv("GPT_API_KEY")
GPT_MODEL = os.getenv("GPT_MODEL", "gpt-3.5-turbo")
LLM_API_KEY = os.getenv("LLM_API_KEY")


def _safe_read_prompt(filename: str) -> str:
    """读取同目录提示词文件，缺失则返回空串避免崩溃。"""
    try:
        prompt_file = Path(__file__).with_name(filename)
        if prompt_file.exists():
            return prompt_file.read_text(encoding="utf-8").strip()
    except Exception:
        pass
    return ""


SYSTEM_PROMPT = _safe_read_prompt("prompt.txt")
SYSTEM_PROMPT_02 = _safe_read_prompt("prompt_02.txt")
#print(SYSTEM_PROMPT_02  )
#print (SYSTEM_PROMPT  )
# ==================== 群白名单配置 ====================
# 只有在这个列表中的群号才会启用 Bot 功能
GROUP_WHITELIST = [
    694590185,  # 自己的群
    1032758463, # 悠游
    152103400, #csqaq 网站交流群
    # 添加更多群号...
]
# 设置为 None 或 [] 表示全部群都启用
# GROUP_WHITELIST = None  # 或者 GROUP_WHITELIST = []

# ==================== 全局变量 ====================
gpt_client = None
llm_client = None
conversation_history = {}  # 存储对话历史
REPLY_ALL = False
IGNORE_WHITELIST = False


def init_gpt_client():
    """初始化 LLM 客户端"""
    global gpt_client
    if not GPT_API_KEY:
        print("✗ 未提供 GPT_API_KEY，跳过 GPT 客户端初始化")
        return
    gpt_client = OpenAI(api_key=GPT_API_KEY)
    print("✓ GPT 客户端初始化成功")


def get_gpt_response(user_id, message):
    """调用 GPT API 获取回复"""
    try:
        if not gpt_client:
            return "GPT 调用失败: GPT 客户端未初始化"
        # 初始化用户对话历史
        if user_id not in conversation_history:
            conversation_history[user_id] = [
                {"role": "system", "content": SYSTEM_PROMPT_02}
            ]
            print(f"✓ 已为用户 {user_id} 初始化对话历史")
        
        # 添加用户消息到历史
        conversation_history[user_id].append({
            "role": "user",
            "content": message
        })
        
        # 调用 GPT API
        response = gpt_client.chat.completions.create(
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


#get llm response
def init_llm_client():
    """初始化 LLM 客户端"""
    global llm_client
    if not LLM_API_KEY:
        print("✗ 未提供 LLM_API_KEY，跳过 OpenRouter 客户端初始化")
        return
    llm_client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=LLM_API_KEY
        )
    print("✓ OpenRouter 客户端初始化成功")

def get_llm_response(user_id, message):
    """调用 openrouter API 获取回复"""
    try:
        if not llm_client:
            return "openrouter 调用失败: OpenRouter 客户端未初始化"
        # 初始化用户对话历史
        if user_id not in conversation_history:
            conversation_history[user_id] = [
                {"role": "system", "content": SYSTEM_PROMPT_02}
            ]
            print(f"✓ 已为用户 {user_id} 初始化对话历史")
        
        # 添加用户消息到历史
        conversation_history[user_id].append({
            "role": "user",
            "content": message
        })
        
        # 调用 openrouter API
        response = llm_client.chat.completions.create(
            #model="tngtech/deepseek-r1t2-chimera:free",
            model="kwaipilot/kat-coder-pro:free",
            # model="nvidia/nemotron-nano-12b-v2-vl:free",
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
        return f"openrouter 调用失败: {str(e)}"
#get llm rresponse end




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


async def listen_and_respond(responder):
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
                        
                        # ✅ 检查群号是否在白名单中（可选关闭）
                        if not IGNORE_WHITELIST and not is_group_whitelisted(group_id):
                            print(f"   ❌ 群号不在白名单中，跳过处理")
                            continue
                        
                        # ✅ 检查是否被@了（改进版）
                        mentioned = is_mentioned(data)
                        print(f"   @检测结果: {mentioned}")

                        # 若启用暴力模式（回复所有消息），则无需 @
                        should_reply = mentioned or REPLY_ALL

                        if should_reply:
                            # 提取纯文本内容（去掉@标签）
                            text_content = extract_text_from_message(raw_message)
                            
                            print(f"   ✅ 被@了，调用 LLM...")
                            print(f"   提取内容: {text_content}")
                            
                            reply = responder(f"group_{group_id}_{user_id}", text_content)
                            print(f"   LLM 回复: {reply}")
                            
                            # 发送回复
                            send_group_message(group_id, reply)
                        else:
                            print(f"   ⏭️  未被@，跳过处理")
                    
                    elif msg_type == "private":
                        # 私聊消息处理（私聊总是回复，不需要@）
                        user_id = data.get("user_id")
                        raw_message = data.get("raw_message", "")
                        
                        print(f"\n💬 私信 来自用户 {user_id}:")
                        print(f"   内容: {raw_message}")
                        print(f"   调用 LLM...")
                        
                        # 调用 LLM 获取回复
                        reply = responder(f"private_{user_id}", raw_message)
                        print(f"   LLM 回复: {reply}")
                        
                        # 发送回复
                        send_private_message(user_id, reply)
    
    except websockets.exceptions.ConnectionClosed:
        print("✗ WebSocket 连接已关闭")
    except Exception as e:
        print(f"✗ 错误: {str(e)}")


async def main():
    """主函数"""
    print("=" * 50)
    print("   CS2 QQBOT导 启动")
    print("=" * 50)

    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=["gpt", "openrouter"], default="openrouter", help="选择后端: gpt 或 openrouter")
    parser.add_argument("--reply-all", action="store_true", help="暴力模式：回复所有群消息，无需 @ 提及")
    parser.add_argument("--ignore-whitelist", action="store_true", help="忽略群白名单，所有群都回复")
    args = parser.parse_args()

    if args.backend == "gpt":
        init_gpt_client()
        responder = get_gpt_response
    else:
        init_llm_client()
        responder = get_llm_response

    global REPLY_ALL
    REPLY_ALL = bool(args.aggressive)
    global IGNORE_WHITELIST
    IGNORE_WHITELIST = bool(args.ignore_whitelist)
    await listen_and_respond(responder)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n[已停止] Bot 已关闭")
