import argparse
import asyncio
import websockets
import json
import requests
from openai import OpenAI
import os
from dotenv import load_dotenv
from pathlib import Path
import logging
import time
import random

# Configure logging so `mcp_comm` debug/info logs appear on the terminal.
# Default to INFO to avoid excessive noise; set to DEBUG to see all debug messages.
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(name)s: %(message)s')


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


SYSTEM_PROMPT = _safe_read_prompt("prompt_smart.txt")
# 仅使用 prompt.txt 作为系统提示，不再加载 prompt_02.txt
# ==================== 群白名单配置 ====================
# 只有在这个列表中的群号才会启用 Bot 功能
# 设置为 "ALL" 表示全部群都启用，[] 表示不允许任何群
# 管理员可以在群里说 "@机器人 出来吧" 来添加当前群到白名单
# 管理员可以在群里说 "@机器人 退下吧" 来移除当前群的白名单
GROUP_WHITELIST = []
# GROUP_WHITELIST = "ALL"  # 取消注释此行以允许所有群

# ==================== 管理员账号配置 ====================
ADMIN_ACCOUNT = 635818639 # 请填写管理员QQ账号（数字）

# ==================== Bot 昵称配置 ====================
# 群内其他bot的昵称列表，遇到这些昵称的用户会：
# 1. 消息格式改为"群内bot{昵称}：消息内容"
# 2. 自动跳过回复（100%跳过），但保存到历史记录
BOT_NICKNAMES = ["爱吃奶糖"]  # 可以根据需要添加更多bot昵称

# ==================== 全局变量 ====================
gpt_client = None
llm_client = None
conversation_histories = {}  # 按会话ID区分的对话历史 {session_id: [history]}
member_cache = {}  # 缓存群成员信息 {group_id: {user_id: {card, nickname}}}
bot_nickname = None  # 缓存机器人昵称
REPLY_ALL = False
IGNORE_WHITELIST = False
QUIET_MODE = False
REPLY_PROBABILITY = 0.3 #0.3  # 回复概率30%
# 回复延迟配置（毫秒）：从环境变量读取，默认 10-100ms
REPLY_DELAY_MIN = int(os.getenv("REPLY_DELAY_MIN", "10"))
REPLY_DELAY_MAX = int(os.getenv("REPLY_DELAY_MAX", "100"))


def get_bot_nickname(self_id=None):
    """获取机器人昵称
    
    Args:
        self_id: 机器人的QQ号（可选，用于验证）
    
    Returns:
        str: 机器人昵称，如果获取失败返回 None
    """
    global bot_nickname
    
    # 如果已经缓存，直接返回
    if bot_nickname:
        return bot_nickname
    
    try:
        url = f"{API_URL}/get_login_info"
        headers = {
            "Authorization": f"Bearer {API_TOKEN}",
            "Content-Type": "application/json"
        }
        response = requests.post(url, json={}, headers=headers, timeout=5)
        if response.status_code == 200:
            result = response.json()
            if result.get("status") == "ok" or result.get("retcode") == 0:
                data = result.get("data", {})
                nickname = data.get("nickname") or data.get("user_name")
                if nickname:
                    bot_nickname = nickname
                    if not QUIET_MODE:
                        print(f"✓ 获取到机器人昵称: {nickname}")
                    return nickname
    except Exception as e:
        if not QUIET_MODE:
            print(f"✗ 获取机器人昵称失败: {e}")
    
    return None


def build_system_prompt(self_id=None, group_id=None):
    """构建系统提示词，包含机器人昵称信息
    
    Args:
        self_id: 机器人的QQ号（可选）
        group_id: 群号（可选，用于获取群昵称）
    
    Returns:
        str: 完整的系统提示词
    """
    prompt = SYSTEM_PROMPT
    
    nickname = None
    
    # 如果有群号，先尝试获取机器人在该群的昵称（群昵称优先）
    if group_id and self_id:
        member_info = get_group_member_info_api(group_id, int(self_id))
        if member_info:
            # 优先使用群昵称（card）
            nickname = member_info.get("card")
    
    # 如果没有群昵称，获取QQ昵称（一般群都是自己设置昵称，所以基本上就是QQ昵称）
    if not nickname:
        nickname = get_bot_nickname(self_id)
    
    # 如果还是没有获取到昵称，使用 self_id
    if not nickname and self_id:
        nickname = str(self_id)
    
    # 如果有昵称，添加到 system prompt
    if nickname:
        prompt = f"{prompt}\n\n你现在的昵称是：{nickname}"
    
    return prompt


def init_gpt_client():
    """初始化 LLM 客户端"""
    global gpt_client
    if not GPT_API_KEY:
        print("✗ 未提供 GPT_API_KEY，跳过 GPT 客户端初始化")
        return
    gpt_client = OpenAI(api_key=GPT_API_KEY)
    print("✓ GPT 客户端初始化成功")


def get_gpt_response(session_id, message, self_id=None, group_id=None):
    """调用 GPT API 获取回复
    
    Args:
        session_id: 会话标识符（群ID或 private_用户ID）
        message: 用户消息
        self_id: 机器人的QQ号（可选，用于构建 system prompt）
        group_id: 群号（可选，用于获取群昵称）
    """
    try:
        if not gpt_client:
            return "GPT 调用失败: GPT 客户端未初始化"
        
        # 获取或创建该会话的对话历史
        if session_id not in conversation_histories:
            # 构建包含机器人昵称的 system prompt
            system_prompt = build_system_prompt(self_id, group_id)
            conversation_histories[session_id] = [
                {"role": "system", "content": system_prompt}
            ]
            if not QUIET_MODE:
                print(f"✓ 已为会话 {session_id} 初始化对话历史")
        
        history = conversation_histories[session_id]
        
        # 添加用户消息到历史
        history.append({
            "role": "user",
            "content": message
        })
        
        # 调用 GPT API
        params = {
            "model": GPT_MODEL,
            "messages": history,
            "temperature": 1.0,
            "stream": False,
        }
        # 对于非 gpt-5 系列模型，设置 max_tokens 与 temperature
        if not GPT_MODEL.startswith("gpt-5"):
            params.update({"max_completion_tokens": 100, })

        response = gpt_client.chat.completions.create(**params)
        
        # 获取回复
        reply = response.choices[0].message.content
        
        # 保存助手回复到历史
        history.append({
            "role": "assistant",
            "content": reply
        })
        
        # 只保留最近 20 条消息，防止历史过长
        if len(history) > 21:  # system + 20条对话
            history[:] = [history[0]] + history[-20:]
        
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

def add_message_to_history(session_id, message, self_id=None, group_id=None):
    """只添加消息到对话历史，不调用 LLM API
    
    Args:
        session_id: 会话标识符
        message: 用户消息
        self_id: 机器人的QQ号（可选，用于构建 system prompt）
        group_id: 群号（可选）
    """
    # 获取或创建该会话的对话历史
    if session_id not in conversation_histories:
        # 构建包含机器人昵称的 system prompt
        system_prompt = build_system_prompt(self_id, group_id)
        conversation_histories[session_id] = [
            {"role": "system", "content": system_prompt}
        ]
        if not QUIET_MODE:
            print(f"✓ 已为会话 {session_id} 初始化对话历史（仅添加消息）")
    
    history = conversation_histories[session_id]
    
    # 添加用户消息到历史
    history.append({
        "role": "user",
        "content": message
    })
    
    # 只保留最近 20 条消息，防止历史过长
    if len(history) > 21:  # system + 20条对话
        history[:] = [history[0]] + history[-20:]


def get_llm_response(session_id, message, self_id=None, group_id=None):
    """调用 openrouter API 获取回复
    
    Args:
        session_id: 会话标识符（群ID或 private_用户ID）
        message: 用户消息
        self_id: 机器人的QQ号（可选，用于构建 system prompt）
        group_id: 群号（可选，用于获取群昵称）
    """
    try:
        if not llm_client:
            return "openrouter 调用失败: OpenRouter 客户端未初始化"
        
        # 获取或创建该会话的对话历史
        if session_id not in conversation_histories:
            # 构建包含机器人昵称的 system prompt
            system_prompt = build_system_prompt(self_id, group_id)
            conversation_histories[session_id] = [
                {"role": "system", "content": system_prompt}
            ]
            if not QUIET_MODE:
                print(f"✓ 已为会话 {session_id} 初始化对话历史")
        
        history = conversation_histories[session_id]
        
        # 添加用户消息到历史
        history.append({
            "role": "user",
            "content": message
        })
        
        # 调用 openrouter API
        response = llm_client.chat.completions.create(
            model="xiaomi/mimo-v2-flash:free",
            #model="kwaipilot/kat-coder-pro:free",
            # model="nvidia/nemotron-nano-12b-v2-vl:free",
            messages=history,
            max_tokens=2000,
            temperature=0.7,
            stream=False,
        )
        
        # 获取回复
        reply = response.choices[0].message.content
        
        # DEBUG: 打印原始回复以便调试
        if not QUIET_MODE:
            print(f"   [DEBUG] 原始回复: {repr(reply)}")

        # 移除思考过程 <think>...</think>
        import re
        reply = re.sub(r'<think>.*?</think>', '', reply, flags=re.DOTALL).strip()

        # 保存助手回复到历史
        history.append({
            "role": "assistant",
            "content": reply
        })
        
        # 只保留最近 20 条消息，防止历史过长
        if len(history) > 21:  # system + 20条对话
            history[:] = [history[0]] + history[-20:]
        
        return reply
    
    except Exception as e:
        return f"openrouter 调用失败: {str(e)}"
#get llm rresponse end





def fetch_market_index():
    """查询 SteamDT 大盘指数（同步版本）
    
    Returns:
        str: 格式化的大盘信息，如果查询失败返回错误信息
    """
    url = "https://api.steamdt.com/user/item/block/v1/summary"
    current_ts = str(int(time.time() * 1000))
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.steamdt.com/",
        "Content-Type": "application/json"
    }
    
    params = {"timestamp": current_ts}
    payload = {
        "type": "BROAD",
        "level": 0,
        "platform": "ALL",
        "typeVal": "",
        "timestamp": current_ts
    }
    
    try:
        response = requests.post(url, params=params, json=payload, headers=headers, timeout=10)
        if response.status_code == 200:
            result = response.json()
            if result.get("success") and result.get("data"):
                data = result["data"]
                index = data.get("index", "N/A")
                name = data.get("name", "大盘")
                rise_fall_rate = data.get("riseFallRate", "0")
                rise_fall_diff = data.get("riseFallDiff", "0")
                
                # 格式化信息
                if isinstance(rise_fall_rate, (int, float)):
                    rate_str = f"{rise_fall_rate:+.2f}%"
                else:
                    rate_str = str(rise_fall_rate)
                
                if isinstance(rise_fall_diff, (int, float)):
                    diff_str = f"{rise_fall_diff:+.2f}"
                else:
                    diff_str = str(rise_fall_diff)
                
                return f"你查了一下现在大盘是：{index}点，今日涨跌幅：{rate_str}，今日涨跌值：{diff_str}"
            else:
                error_msg = result.get("errorMsg", "查询失败")
                return f"你查了一下大盘，但是查询失败了：{error_msg}"
        else:
            return f"你查了一下大盘，但是接口返回错误：HTTP {response.status_code}"
    except requests.exceptions.Timeout:
        return "你查了一下大盘，但是查询超时了"
    except Exception as e:
        return f"你查了一下大盘，但是发生了错误：{str(e)}"


def apply_reply_delay():
    """应用随机回复延迟"""
    if REPLY_DELAY_MIN >= 0 and REPLY_DELAY_MAX >= REPLY_DELAY_MIN:
        delay_ms = random.randint(REPLY_DELAY_MIN, REPLY_DELAY_MAX)
        delay_seconds = delay_ms / 1000.0  # 转换为秒
        if delay_seconds > 0:
            time.sleep(delay_seconds)
            if not QUIET_MODE:
                print(f"   ⏱️  延迟 {delay_ms}ms 后发送")


def send_group_message(group_id, message):
    """发送群组消息"""
    try:
        # 应用随机延迟
        apply_reply_delay()
        
        url = f"{API_URL}/send_group_msg"
        headers = {
            "Authorization": f"Bearer {API_TOKEN}",
            "Content-Type": "application/json"
        }
        # 移除消息前后的换行符
        message = message.strip()
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
        # 应用随机延迟
        apply_reply_delay()
        
        url = f"{API_URL}/send_private_msg"
        headers = {
            "Authorization": f"Bearer {API_TOKEN}",
            "Content-Type": "application/json"
        }
        # 移除消息前后的换行符
        message = message.strip()
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


def extract_reply_info(message_data):
    """提取回复信息（被回复的消息内容）
    
    返回: (被回复的消息内容, 被回复的用户ID) 或 (None, None)
    """
    if not isinstance(message_data, list):
        return None, None
    
    for item in message_data:
        if item.get("type") == "reply":
            reply_data = item.get("data", {})
            replied_text = reply_data.get("text", "")  # 被回复的消息内容
            replied_user_id = reply_data.get("qq", "")  # 被回复的用户ID
            return replied_text, replied_user_id
    
    return None, None


def has_image(message_data):
    """检测消息中是否包含图片"""
    if not isinstance(message_data, list):
        return False
    
    for item in message_data:
        if item.get("type") == "image":
            return True
    return False


def get_group_member_info_api(group_id, user_id):
    """通过 API 获取群成员信息（包括群昵称和昵称）
    
    Args:
        group_id: 群号
        user_id: 用户QQ号
    
    Returns:
        dict: {card: 群昵称, nickname: 昵称, ...} 或 None
    """
    # 先从缓存中查找
    if group_id in member_cache and user_id in member_cache[group_id]:
        return member_cache[group_id][user_id]
    
    try:
        url = f"{API_URL}/get_group_member_info"
        headers = {
            "Authorization": f"Bearer {API_TOKEN}",
            "Content-Type": "application/json"
        }
        data = {
            "group_id": group_id,
            "user_id": user_id,
            "no_cache": False  # 使用缓存
        }
        response = requests.post(url, json=data, headers=headers, timeout=5)
        if response.status_code == 200:
            result = response.json()
            # NapCat API 可能返回 status="ok" 或 retcode=0
            if result.get("status") == "ok" or result.get("retcode") == 0:
                member_info = result.get("data", {})
                # 缓存结果
                if group_id not in member_cache:
                    member_cache[group_id] = {}
                member_cache[group_id][user_id] = member_info
                return member_info
    except Exception as e:
        if not QUIET_MODE:
            print(f"   [WARN] 获取群成员信息失败 (群{group_id}, 用户{user_id}): {e}")
    return None


def extract_text_with_mentions(raw_message, message_data=None, group_id=None):
    """从消息中提取文本内容，保留 mention 信息（转换为 @用户名 格式）
    
    Args:
        raw_message: 原始消息文本，包含 CQCode
        message_data: 消息数据数组，用于获取 mention 用户的完整信息
        group_id: 群号（用于通过 API 获取群昵称）
    
    Returns:
        str: 提取的文本，mention 转换为 @群昵称 或 @昵称 或 @QQ号
    """
    import re
    
    # 从 message_data 中构建 mention 用户信息映射 {qq: display_name}
    mention_map = {}
    if isinstance(message_data, list):
        for item in message_data:
            if item.get("type") == "at":
                at_data = item.get("data", {})
                at_qq = str(at_data.get("qq", ""))
                if not at_qq:
                    continue
                
                display_name = None
                
                # 优先使用 message_data 中的 card（群昵称）
                display_name = at_data.get("card")
                
                # 如果没有 card，尝试使用 name（昵称）
                if not display_name:
                    display_name = at_data.get("name")
                
                # 如果 message_data 中都没有，且提供了 group_id，通过 API 获取
                if not display_name and group_id:
                    member_info = get_group_member_info_api(group_id, int(at_qq))
                    if member_info:
                        # 优先级：群昵称（card） > 昵称（nickname）
                        display_name = member_info.get("card") or member_info.get("nickname")
                
                # 如果还是没有，使用 QQ 号
                if not display_name:
                    display_name = at_qq
                
                mention_map[at_qq] = display_name
    
    # 替换 mention 的 CQCode
    def replace_mention(match):
        cq_code = match.group(0)
        qq_match = re.search(r'qq=(\d+)', cq_code)
        if qq_match:
            qq = qq_match.group(1)
            # 优先从 mention_map 中获取（群昵称/昵称）
            if qq in mention_map:
                return f"@{mention_map[qq]}"
            # 其次从 CQCode 中提取 name
            name_match = re.search(r'name=([^,\]]+)', cq_code)
            if name_match:
                return f"@{name_match.group(1)}"
            # 最后使用 QQ 号
            return f"@{qq}"
        return cq_code
    
    # 替换 mention 的 CQCode
    text = re.sub(r'\[CQ:at[^\]]+\]', replace_mention, raw_message)
    
    # 移除其他 CQCode（如图片、表情等），但保留 mention
    text = re.sub(r'\[CQ:(?!at)[^\]]+\]', '', text)
    
    return text.strip()


def extract_text_from_message(raw_message):
    """从消息中提取纯文本内容（去掉 CQCode）
    
    注意：此函数会移除所有 mention，如需保留 mention，请使用 extract_text_with_mentions
    """
    import re
    # 移除所有 CQCode，如 [CQ:at,qq=xxxxx]、[CQ:image,file=xxx] 等
    text = re.sub(r'\[CQ:[^\]]+\]', '', raw_message)
    return text.strip()


def is_bot_user(sender_info, group_id=None, user_id=None):
    """检测用户是否是bot（根据昵称匹配）
    
    Args:
        sender_info: 发送者信息字典（包含nickname、card等）
        group_id: 群号（可选，用于获取群昵称）
        user_id: 用户QQ号（可选，用于获取完整信息）
    
    Returns:
        tuple: (是否是bot, bot昵称) 或 (False, None)
    """
    if not BOT_NICKNAMES:
        return False, None
    
    # 获取用户昵称（优先级：群昵称 > QQ昵称）
    nickname = None
    if sender_info:
        nickname = sender_info.get("card") or sender_info.get("nickname")
    
    # 如果没有昵称且提供了 group_id 和 user_id，尝试通过 API 获取
    if not nickname and group_id and user_id:
        member_info = get_group_member_info_api(group_id, user_id)
        if member_info:
            nickname = member_info.get("card") or member_info.get("nickname")
    
    # 如果没有昵称，使用 user_id
    if not nickname and user_id:
        nickname = str(user_id)
    
    # 检查昵称是否在 BOT_NICKNAMES 列表中
    if nickname and nickname in BOT_NICKNAMES:
        return True, nickname
    
    return False, None


def build_message_with_context(raw_message, message_data, user_id, sender_info=None, group_id=None):
    """构建包含回复上下文和用户信息的完整消息
    
    Args:
        raw_message: 原始消息文本
        message_data: 消息数据结构
        user_id: 发送者QQ号
        sender_info: 发送者信息字典（包含nickname等）
        group_id: 群号（可选，用于获取 mention 用户的群昵称）
    
    Returns:
        tuple: (构建后的消息内容, 是否是bot, bot昵称) 或 (消息内容, False, None)
    """
    # 检测是否是bot
    is_bot, bot_nickname = is_bot_user(sender_info, group_id, user_id)
    
    # 获取用户昵称，如果没有则使用QQ号
    if sender_info and sender_info.get("nickname"):
        user_name = sender_info.get("nickname")
    elif sender_info and sender_info.get("card"):
        user_name = sender_info.get("card")  # 群名片
    else:
        user_name = str(user_id)
    
    # 如果是bot，使用特殊格式
    if is_bot:
        # 检测是否有图片
        if has_image(message_data):
            message_content = f"群内bot{bot_nickname}：发送了一张你看不了的图片"
        else:
            # 使用新函数提取文本，保留 mention 信息
            text_content = extract_text_with_mentions(raw_message, message_data, group_id)
            if text_content:
                message_content = f"群内bot{bot_nickname}：{text_content}"
            else:
                message_content = f"群内bot{bot_nickname}：发送了一条空消息"
    else:
        # 普通用户，使用原有格式
        # 检测是否有图片
        if has_image(message_data):
            message_content = f"{user_name}发送了一张你看不了的图片"
        else:
            # 使用新函数提取文本，保留 mention 信息（优先使用群昵称，然后是昵称，最后是QQ号）
            text_content = extract_text_with_mentions(raw_message, message_data, group_id)
            if text_content:
                message_content = f"{user_name}说：{text_content}"
            else:
                message_content = f"{user_name}发送了一条空消息"
    
    # 检查是否有回复内容
    replied_text, replied_user_id = extract_reply_info(message_data)
    if replied_text:
        # 如果有回复内容，加入上下文
        final_message = f"[回复: {replied_text}] {message_content}"
    else:
        final_message = message_content
    
    return final_message, is_bot, bot_nickname


def is_group_whitelisted(group_id):
    """检查群号是否在白名单中"""
    # 如果白名单为字符串 "ALL"，允许所有群
    if GROUP_WHITELIST == "ALL":
        return True
    
    # 如果白名单为空、None 或不是列表，不允许任何群
    if not GROUP_WHITELIST or not isinstance(GROUP_WHITELIST, list):
        return False
    
    # 检查群号是否在白名单中
    return group_id in GROUP_WHITELIST


def add_group_to_whitelist(group_id):
    """添加群号到白名单"""
    if group_id not in GROUP_WHITELIST:
        GROUP_WHITELIST.append(group_id)
        print(f"✓ 已添加群 {group_id} 到群白名单")
        return True
    return False


def remove_group_from_whitelist(group_id):
    """从白名单移除群号，同时清除该群的对话历史"""
    if group_id in GROUP_WHITELIST:
        GROUP_WHITELIST.remove(group_id)
        print(f"✓ 已移除群 {group_id} 从群白名单")
        
        # 清除该群的对话历史
        if group_id in conversation_histories:
            del conversation_histories[group_id]
            print(f"✓ 已清除群 {group_id} 的对话历史")
        return True
    return False


def is_mentioned_bot(message_data, self_id):
    """检查消息中是否 mention 了机器人
    
    Args:
        message_data: 消息数据数组
        self_id: 机器人的QQ号
    
    Returns:
        bool: 是否 mention 了机器人
    """
    if not self_id:
        return False
    
    # 从 message_data 数组中检查（优先）
    if isinstance(message_data, list):
        for item in message_data:
            if item.get("type") == "at":
                at_data = item.get("data", {})
                at_qq = str(at_data.get("qq", ""))
                # self_id 可能是字符串或整数，需要转换比较
                if str(at_qq) == str(self_id):
                    return True
    
    return False


def check_admin_group_command(data):
    """检查管理员是否发出了群管理命令（添加/移除群白名单）
    
    返回: "add_group", "remove_group", 或 None
    """
    if ADMIN_ACCOUNT == 0:
        return None
    
    user_id = data.get("user_id")
    if user_id != ADMIN_ACCOUNT:
        return None
    
    raw_message = data.get("raw_message", "")
    self_id = data.get("self_id")
    message_data = data.get("message", [])
    
    # 检查是否 mention 了机器人（优先从 message_data 检查）
    is_mentioned = is_mentioned_bot(message_data, self_id)
    
    # 如果 message_data 中没有找到，尝试从 raw_message 中检查（兼容性）
    if not is_mentioned and raw_message and self_id:
        import re
        # 使用正则表达式匹配，支持可能的额外参数
        mention_pattern = rf'\[CQ:at,qq={re.escape(str(self_id))}(?:,.*?)?\]'
        is_mentioned = bool(re.search(mention_pattern, raw_message))
    
    if not is_mentioned:
        return None
    
    # 提取纯文本内容进行关键词检查
    text_content = extract_text_from_message(raw_message)
    
    if "出来吧" in text_content:
        return "add_group"
    elif "退下吧" in text_content or "下去吧" in text_content:
        return "remove_group"
    
    return None


def handle_message(data, responder):
    """处理接收到的消息"""
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
            sender_info = data.get("sender", {})  # 获取发送者信息
            
            # 🔍 调试：打印完整消息结构（静默模式下跳过）
            if not QUIET_MODE:
                print(f"📨 群消息 [{group_id}] 来自用户 {user_id}:")
                print(f"   Raw: {raw_message}")
                print(f"   Message 结构: {message_data}")
                print(f"   Self ID: {self_id}")
            
            # ✅ 优先检查群管理命令（管理员 mention 机器人 + "出来吧"/"退下吧"）
            group_command = check_admin_group_command(data)
            if group_command == "add_group":
                add_group_to_whitelist(group_id)
                send_group_message(group_id, "来了")
                return
            elif group_command == "remove_group":
                send_group_message(group_id, "886")
                remove_group_from_whitelist(group_id)
                return
            
            # ✅ 检查是否应该回复
            # 如果忽略白名单或启用 REPLY_ALL 模式，直接回复所有群
            # 否则只回复在白名单中的群
            if not (IGNORE_WHITELIST or REPLY_ALL) and not is_group_whitelisted(group_id):
                if not QUIET_MODE:
                    print(f"   ❌ 群号不在白名单中且未启用 REPLY_ALL，跳过处理")
                return

            # 构建包含回复上下文的完整消息（传递 group_id 以便获取群昵称）
            text_content, is_bot, bot_nickname = build_message_with_context(raw_message, message_data, user_id, sender_info, group_id)
            
            # 检查是否是bot用户
            if is_bot:
                # Bot 用户：保存到历史记录但不回复（100%跳过，不经过随机概率判断）
                if not QUIET_MODE:
                    print(f"   🤖 检测到bot用户：{bot_nickname}，保存到历史但不回复")
                # 检查消息中是否包含"大盘"关键词
                extracted_text = extract_text_from_message(raw_message)
                if "大盘" in extracted_text:
                    market_info = fetch_market_index()
                    text_content = f"{text_content}\n{market_info}"
                # 添加消息到历史记录但不调用 LLM
                add_message_to_history(group_id, text_content, self_id=self_id, group_id=group_id)
                return
            
            # 随机概率判断（普通用户才进行随机判断）
            if random.random() > REPLY_PROBABILITY:
                if not QUIET_MODE:
                    print(f"   🎲 随机跳过回复（概率：{int(REPLY_PROBABILITY*100)}%）")
                return
            
            # 检查消息中是否包含"大盘"关键词
            extracted_text = extract_text_from_message(raw_message)
            if "大盘" in extracted_text:
                if not QUIET_MODE:
                    print(f"   🔍 检测到'大盘'关键词，正在查询大盘信息...")
                market_info = fetch_market_index()
                # 将查询结果添加到消息中
                text_content = f"{text_content}\n{market_info}"
                if not QUIET_MODE:
                    print(f"   📊 大盘信息: {market_info}")
            
            if not QUIET_MODE:
                print(f"   ✅ 调用 LLM...")
                print(f"   提取内容: {text_content}")
            
            # 使用群ID作为会话ID，这样同一个群的所有用户共享对话历史
            # 传递 self_id 和 group_id 以便在 system prompt 中加入机器人昵称
            reply = responder(group_id, text_content, self_id=self_id, group_id=group_id)
            
            if not QUIET_MODE:
                print(f"   LLM 回复: {reply}")
            
            # 检查是否调用失败，若失败则不发送群消息
            if reply.startswith("openrouter 调用失败") or reply.startswith("GPT 调用失败"):
                if not QUIET_MODE:
                    print(f"   ❌ API 调用失败，已拦截错误消息发送")
            else:
                # 发送回复
                send_group_message(group_id, reply)
        
        elif msg_type == "private":
            # 私聊消息处理（私聊总是回复，不需要@）
            user_id = data.get("user_id")
            raw_message = data.get("raw_message", "")
            self_id = data.get("self_id")  # 私聊也有 self_id
            
            if not QUIET_MODE:
                print(f"💬 私信 来自用户 {user_id}:")
                print(f"   内容: {raw_message}")
            
            # 检查消息中是否包含"大盘"关键词
            text_content = raw_message
            if "大盘" in raw_message:
                if not QUIET_MODE:
                    print(f"   🔍 检测到'大盘'关键词，正在查询大盘信息...")
                market_info = fetch_market_index()
                # 将查询结果添加到消息中
                text_content = f"{raw_message}\n{market_info}"
                if not QUIET_MODE:
                    print(f"   📊 大盘信息: {market_info}")
            
            if not QUIET_MODE:
                print(f"   调用 LLM...")
            
            # 调用 LLM 获取回复
            # 对于私聊，group_id 为 None，只传递 self_id（用于获取QQ昵称）
            reply = responder(f"private_{user_id}", text_content, self_id=self_id, group_id=None)
            
            if not QUIET_MODE:
                print(f"   LLM 回复: {reply}")
            
            # 发送回复
            send_private_message(user_id, reply)


async def listen_and_respond(responder):
    """监听消息并使用 GPT 回复（自动重连）"""
    extra_headers = [("Authorization", f"Bearer {WS_TOKEN}")]
    reconnect_delay = 5  # 初始重连延迟（秒）
    max_reconnect_delay = 60  # 最大重连延迟
    
    while True:
        try:
            async with websockets.connect(WS_URL, extra_headers=extra_headers) as ws:
                print("✓ WebSocket 连接成功，等待消息...")
                reconnect_delay = 5  # 连接成功后重置延迟
                
                while True:
                    message = await ws.recv()
                    data = json.loads(message)
                    handle_message(data, responder)
    
        except websockets.exceptions.ConnectionClosed:
            print(f"✗ WebSocket 连接已关闭，{reconnect_delay}秒后尝试重连...")
        except Exception as e:
            print(f"✗ 错误: {str(e)}，{reconnect_delay}秒后尝试重连...")
        
        # 等待后重连
        await asyncio.sleep(reconnect_delay)
        # 增加延迟时间（指数退避），防止频繁重连
        reconnect_delay = min(reconnect_delay * 1.5, max_reconnect_delay)
        reconnect_delay = int(reconnect_delay)


async def main():
    """主函数"""
    print("=" * 50)
    print("   CS2 QQBOT导 启动")
    print("=" * 50)

    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=["gpt", "openrouter"], default="openrouter", help="选择后端: gpt 或 openrouter")
    # 支持新旗标 --replyall，同时保留 --reply-all 作为别名
    parser.add_argument("--replyall", "--reply-all", dest="reply_all", action="store_true", help="回复所有群消息，无需 @ 提及")
    parser.add_argument("--ignore-whitelist", action="store_true", help="忽略群白名单，所有群都回复")
    parser.add_argument("--quiet", action="store_true", help="静默模式，减少控制台输出")
    parser.add_argument("--delay-min", type=int, default=None, help="回复延迟最小值（毫秒），默认从环境变量 REPLY_DELAY_MIN 读取，否则为 10")
    parser.add_argument("--delay-max", type=int, default=None, help="回复延迟最大值（毫秒），默认从环境变量 REPLY_DELAY_MAX 读取，否则为 100")
    args = parser.parse_args()

    if args.backend == "gpt":
        init_gpt_client()
        responder = get_gpt_response
    else:
        init_llm_client()
        responder = get_llm_response

    global REPLY_ALL
    REPLY_ALL = bool(args.reply_all)
    global IGNORE_WHITELIST
    IGNORE_WHITELIST = bool(args.ignore_whitelist)
    global QUIET_MODE
    QUIET_MODE = args.quiet
    global REPLY_DELAY_MIN, REPLY_DELAY_MAX
    if args.delay_min is not None:
        REPLY_DELAY_MIN = args.delay_min
    if args.delay_max is not None:
        REPLY_DELAY_MAX = args.delay_max
    
    # 验证延迟范围
    if REPLY_DELAY_MIN < 0:
        REPLY_DELAY_MIN = 0
    if REPLY_DELAY_MAX < REPLY_DELAY_MIN:
        REPLY_DELAY_MAX = REPLY_DELAY_MIN
    
    if not QUIET_MODE:
        print(f"⚙️  回复延迟范围: {REPLY_DELAY_MIN}-{REPLY_DELAY_MAX}ms")
    
    # MCP 连接自检：检查 MCP 服务是否在线（使用 streamable-http）
    mcp_available = False
    try:
        mcp_config_path = Path(__file__).with_name("mcp_servers.json")
        if mcp_config_path.exists():
            with open(mcp_config_path, "r", encoding="utf-8") as f:
                mcp_cfg = json.load(f)
            servers = mcp_cfg.get("servers", [])
            for server in servers:
                server_id = server.get("id", "")
                url = server.get("base_url", "")
                if url:
                    try:
                        # HTTP 模式：尝试 /mcp/list_tools 确认服务可用
                        list_url = f"{url.rstrip('/')}/mcp/list_tools"
                        if not QUIET_MODE:
                            print(f"🔗 连接到 MCP( {server_id} ) HTTP: {list_url}")
                        resp = requests.post(list_url, json={"server_id": server_id}, timeout=6)
                        if resp.status_code == 200:
                            if not QUIET_MODE:
                                try:
                                    print("✓ MCP 列表接口返回：", resp.json())
                                except Exception:
                                    print("✓ MCP 列表接口返回 200 (非 JSON)")
                            mcp_available = True
                            continue
                    except requests.exceptions.ReadTimeout:
                        if not QUIET_MODE:
                            print(f"✓ MCP( {server_id} ) HTTP 请求超时（可能为流式或响应缓慢）")
                        mcp_available = True
                        continue
                    except Exception as e:
                        if not QUIET_MODE:
                            print(f"✗ MCP( {server_id} ) HTTP 连接失败: {e}")
    except Exception as e:
        if not QUIET_MODE:
            print(f"✗ MCP 配置加载失败: {e}")

    if not mcp_available:
        if not QUIET_MODE:
            print("⚠ MCP 服务不可用，Bot 仅使用 LLM 回复")
    
    
    await listen_and_respond(responder)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n[已停止] Bot 已关闭")
