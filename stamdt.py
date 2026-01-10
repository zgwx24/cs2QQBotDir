
import aiohttp
import asyncio
import time
from typing import Dict, Any, List, Optional

# 通用 Header
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.steamdt.com/",
    "Content-Type": "application/json"
}

# 接口地址定义
URL_SUMMARY = "https://api.steamdt.com/user/item/block/v1/summary"   # 大盘
URL_RELATION = "https://api.steamdt.com/user/item/block/v1/relation" # 热门板块列表

async def fetch_steamdt_index() -> Dict[str, Any]:
    """
    Fetch the 'BROAD' market index (General Market) from SteamDT.
    Retrieves the main market index, rise/fall counts, and overall status.
    """
    current_ts = str(int(time.time() * 1000))
    params = {"timestamp": current_ts}
    
    payload = {
        "type": "BROAD",
        "level": 0,
        "platform": "ALL",
        "typeVal": "",
        "timestamp": current_ts
    }

    try:
        async with aiohttp.ClientSession() as session:
            # 使用 URL_SUMMARY
            async with session.post(URL_SUMMARY, params=params, json=payload, headers=HEADERS) as response:
                if response.status == 200:
                    result = await response.json()
                    if result.get("success"):
                        return result["data"]
                    else:
                        return {"error": result.get("errorMsg")}
                return {"error": f"HTTP {response.status}"}
    except Exception as e:
        return {"error": str(e)}

async def fetch_steamdt_hot_sectors(day_range: str = "1") -> List[Dict[str, Any]]:
    """
    Fetch the list of 'HOT' item sectors (e.g., Arsenal Phase 1, Doppler, Gloves).
    
    Args:
        day_range (str): Time range for data (default "1" for 1 day).
    """
    current_ts = str(int(time.time() * 1000))
    params = {"timestamp": current_ts}
    
    payload = {
        "type": "HOT",
        "level": 0,
        "platform": "ALL",
        "typeDay": day_range,
        "timestamp": current_ts
    }

    try:
        async with aiohttp.ClientSession() as session:
            # 【核心修改】这里改成了 URL_RELATION
            async with session.post(URL_RELATION, params=params, json=payload, headers=HEADERS) as response:
                if response.status == 200:
                    result = await response.json()
                    
                    if result.get("success") and isinstance(result.get("data"), list):
                        data_list = result["data"]
                        
                        # 数据清洗：去掉 trendList 防止 Token 爆炸
                        cleaned_data = []
                        for item in data_list:
                            summary = {
                                "name": item.get("name"),
                                "index": item.get("index"),         # 当前指数
                                "change_val": item.get("riseFallDiff"), # 涨跌值
                                "change_rate": item.get("riseFallRate"),# 涨跌幅%
                                "type": item.get("type")
                            }
                            cleaned_data.append(summary)
                            
                        return cleaned_data
                    else:
                        return [{"error": result.get("errorMsg", "Unknown error")}]
                return [{"error": f"HTTP {response.status}"}]
    except Exception as e:
        return [{"error": str(e)}]

if __name__ == "__main__":
    # 本地测试
    print("--- Testing Index (Summary) ---")
    print(asyncio.run(fetch_steamdt_index()))
    
    print("\n--- Testing Hot Sectors (Relation) ---")
    res = asyncio.run(fetch_steamdt_hot_sectors())
    
    # 打印前2个结果验证
    import json
    print(json.dumps(res[:2], indent=2, ensure_ascii=False))

# import aiohttp
# import asyncio
# import time
# from typing import Dict, Any

# # 【关键修改】：加上 -> Dict[str, Any] 类型提示
# # 【关键修改】：加上 """文档字符串"""，这会变成 MCP 工具的 description
# async def fetch_steamdt_index() -> Dict[str, Any]:
#     """
#     Fetch the current SteamDT market index summary.
#     Retrieves real-time data including the market index, rise/fall rates, 
#     and the number of items rising or falling.
    
#     Returns:
#         dict: A dictionary containing market index data (index, riseFallRate, etc.)
#     """
#     url = "https://api.steamdt.com/user/item/block/v1/summary"
    
#     current_ts = str(int(time.time() * 1000))
    
#     headers = {
#         "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
#         "Referer": "https://www.steamdt.com/",
#         "Content-Type": "application/json"
#     }

#     params = {"timestamp": current_ts}
    
#     payload = {
#         "type": "BROAD",
#         "level": 0,
#         "platform": "ALL",
#         "typeVal": "",
#         "timestamp": current_ts
#     }

#     try:
#         async with aiohttp.ClientSession() as session:
#             async with session.post(url, params=params, json=payload, headers=headers) as response:
#                 if response.status == 200:
#                     result = await response.json()
#                     if result.get("success"):
#                         return result["data"]
#                     else:
#                         return {"error": result.get("errorMsg")}
#                 else:
#                     return {"error": f"HTTP {response.status}"}
#     except Exception as e:
#         return {"error": str(e)}

# if __name__ == "__main__":
#     # 测试运行
#     print(asyncio.run(fetch_steamdt_index()))



# import aiohttp
# import asyncio
# import time

# async def fetch_steamdt_index():
#     url = "https://api.steamdt.com/user/item/block/v1/summary"
    
#     # 动态生成时间戳
#     current_ts = str(int(time.time() * 1000))
    
#     headers = {
#         "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
#         "Referer": "https://www.steamdt.com/",
#         "Content-Type": "application/json"
#     }

#     # URL 参数
#     params = {"timestamp": current_ts}

#     # Body 载荷
#     payload = {
#         "type": "BROAD",
#         "level": 0,
#         "platform": "ALL",
#         "typeVal": "",
#         "timestamp": current_ts
#     }

#     try:
#         # 创建异步会话
#         async with aiohttp.ClientSession() as session:
#             # 发送 POST 请求 (注意这里是 await)
#             async with session.post(url, params=params, json=payload, headers=headers) as response:
                
#                 if response.status == 200:
#                     # 解析 JSON (这也是异步操作，需要 await)
#                     result = await response.json()
                    
#                     if result.get("success"):
#                         data = result["data"]
#                         print(f"✅ [Async] 抓取成功 - {time.strftime('%H:%M:%S')}")
#                         print("-" * 30)
#                         print(f"板块: {data.get('name')}")
#                         print(f"指数: {data.get('index')}")
#                         print(f"涨跌: {data.get('riseFallRate')}%")
#                         print("-" * 30)
#                         return data
#                     else:
#                         print(f"❌ 业务报错: {result.get('errorMsg')}")
#                 else:
#                     print(f"❌ HTTP 报错: {response.status}")
                    
#     except Exception as e:
#         print(f"❌ 发生异常: {e}")

# async def main():
#     # 这里演示单次调用
#     await fetch_steamdt_index()
    
#     # 如果你想做一个简单的死循环监控，可以这样写：
#     # while True:
#     #     await fetch_steamdt_index()
#     #     await asyncio.sleep(5) # 异步等待5秒

# if __name__ == "__main__":
#     # 启动异步事件循环
#     asyncio.run(main())