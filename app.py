from WS服务器 import OneBotWSServer
import asyncio
import json
import re
import random
import aiohttp
import uuid
import time
from functools import wraps
from datetime import datetime, timedelta
from 数据库 import 插入消息数据, 更新消息文件url
from 匹配查询 import 解析命令并查询, ai驱动查询
from 文件上传 import 检查文件大小, alist_offline_download
from 配置 import 每分钟最大查询次数, 单条合并消息上限, 单次查询最大合并数, 消息发送延迟范围, 分片发送延迟范围, 定时发送时间, 监听地址, 监听端口, Token, 文件最大上传体积, 控制台打印事件, 超级用户列表, 功能开关, 查询关键词组, 一言主接口, 一言备用接口
from 系统状态 import 获取运行状态
import 消息发送

群查询记录 = {}
消息插入锁 = asyncio.Lock()
机器人ID = None
最近查询群聊 = {}
频率限制存储 = {}

def 是否超级用户(用户号: int) -> bool:
    return 用户号 in 超级用户列表

def 频率限制装饰器(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        global 频率限制存储
        群号 = args[1] if len(args) > 1 else 0
        
        if 群号 == 0:
            return await func(*args, **kwargs)
        
        当前时间 = time.time()
        频率限制存储[群号] = [t for t in 频率限制存储.get(群号, []) if 当前时间 - t < 60]
        if len(频率限制存储[群号]) >= 每分钟最大查询次数:
            print(f"[频率限制] 群{群号} 1分钟内查询次数已达上限")
            return [], "查询过于频繁，请1分钟后再试"
        频率限制存储[群号].append(当前时间)
        return await func(*args, **kwargs)
    return wrapper

@频率限制装饰器
async def 处理指令(消息文本: str, 群号: int, server: OneBotWSServer, 用户号: int = 0, 指令来源: str = "group"):
    """
    指令来源: group=群聊指令, private=超级用户私聊指令
    """
    global 机器人ID
    if not 机器人ID:
        print("[错误] 机器人ID未初始化")
        return
    最近查询群聊[群号] = datetime.now()
    
    # ========== AI查询逻辑 ==========
    是否超级 = 是否超级用户(用户号)
    ai查询结果, 提示消息 = await ai驱动查询(消息文本, 群号, 用户号, 是否超级)
    
    # 发送提示消息
    if not server._connections:
        print("[错误] 无客户端连接")
        return
    客户端ID = next(iter(server._connections.keys()))
    # 调用消息发送模块的函数
    目标ID = 群号 if 指令来源 == "group" else 用户号
    await 消息发送.发送提示消息(server, 客户端ID, 指令来源, 目标ID, 提示消息)

    结果 = ai查询结果 if ai查询结果 else []
    if not 结果:
        print(f"[AI指令处理] 无查询结果 | 指令: {消息文本}")
        return
    
    # 分片发送消息
    await 消息发送.随机延迟()
    await 消息发送.分片发送消息(server, 结果, 指令来源, 群号, 用户号)

def 修复_file_url(消息数据: dict) -> str:
    url = 消息数据.get("url", "")
    file_name = 消息数据.get("file", "")
    if url.endswith("?fname=") and file_name:
        return f"{url}{file_name}"
    return url

def 打包(事件: dict):
    return {
        "人机号": 事件.get("self_id", 0),
        "用户号": 事件.get("user_id", 0),
        "时间戳": 事件.get("time", 0),
        "消息号": 事件.get("message_id", 0),
        "群昵称": 事件.get("sender", {}).get("nickname", ""),
        "长度": 事件.get("font", 0),
        "群名": 事件.get("group_name", ""),
        "群号": 事件.get("group_id", 0),
        "消息": json.dumps(事件.get("message", []), ensure_ascii=False)
    }

async def 处理消息中的文件(群号: int, 消息号: int, 消息列表: list):
    for 索引, 消息单元 in enumerate(消息列表):
        消息类型 = 消息单元.get("type")
        消息数据 = 消息单元.get("data", {})
        if 消息类型 not in ["image", "file", "video"]:
            continue
        
        文件大小 = 消息数据.get("file_size", "0")
        原始文件名 = 消息数据.get("file", "")
        if not 原始文件名:
            原始文件名 = f"未知{消息类型}_{uuid.uuid4().hex[:8]}"
        if 消息类型 == "file":
            原始url = 修复_file_url(消息数据)
            if not 原始url and "file_id" in 消息数据:
                print(f"[过滤] 消息{消息号}仅含file_id无链接，标记为[群文件]")
                continue
        else:
            原始url = 消息数据.get("url", "")
        if not 检查文件大小(文件大小) == True:
            print(f"[过滤] 消息{消息号}文件超过{文件最大上传体积}M，丢弃")
            continue
        
        新url = await alist_offline_download(
            文件url=原始url,
            原始文件名=原始文件名,
            文件类型=消息类型,
            文件体积=int(文件大小) if 文件大小.isdigit() else 0
        )
        if 新url:
            成功 = await asyncio.get_event_loop().run_in_executor(
                None,
                更新消息文件url,
                群号, 消息号, 消息列表, 新url, 索引
            )
            if 成功:
                print(f"[URL更新成功] 消息{消息号}")
            else:
                print(f"[URL更新失败] 消息{消息号}")
        else:
            print(f"[下载失败] 消息{消息号}")

async def 监听发送成功事件(事件: dict):
    global 机器人ID
    if 事件.get("post_type") != "message_sent":
        return
    if 事件.get("user_id") != 机器人ID or 事件.get("message_type") != "group":
        return
    群号 = 事件.get("group_id")
    消息ID = 事件.get("message_id")
    print(f"✅ [事件确认] 群 {群号} 合并消息发送成功 | 消息ID: {消息ID}")

async def 获取一言():
    主接口 = 一言主接口
    备用接口 = 一言备用接口
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(主接口, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("hitokoto", "冒泡")
        except Exception as e:
            print(f"主接口获取失败: {str(e)}")
        try:
            async with session.get(备用接口, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("hitokoto", "冒泡")
        except Exception as e:
            print(f"备用接口获取失败: {str(e)}")
    return "冒泡"

async def 定时发送一言(server: OneBotWSServer):
    while True:
        当前时间 = datetime.now()
        当前小时 = 当前时间.hour
        for (目标小时, 时间窗口) in 定时发送时间:
            if (目标小时 - 时间窗口) <= 当前小时 <= (目标小时 + 时间窗口):
                发送标记文件 = f".sent_{目标小时}_{当前时间.date()}.flag"
                try:
                    with open(发送标记文件, "r") as f:
                        continue
                except FileNotFoundError:
                    随机延迟秒数 = random.randint(0, 时间窗口 * 3600)
                    print(f"[定时发送] 随机延迟 {随机延迟秒数} 秒后发送一言")
                    await asyncio.sleep(随机延迟秒数)

                    一言内容 = await 获取一言()
                    for 群号 in 最近查询群聊.keys():
                        if not server._connections:
                            print("[定时发送] 无客户端连接，跳过发送")
                            continue
                        客户端ID = next(iter(server._connections.keys()))
                        try:
                            await server.call_api(
                                client_id=客户端ID,
                                action="send_group_msg",
                                params={"group_id": 群号, "message": 一言内容},
                                timeout=60
                            )
                            print(f"✅ [定时发送成功] 向群 {群号} 发送一言")
                        except Exception as e:
                            print(f"[定时发送失败] 群 {群号}: {str(e)}")
                    with open(发送标记文件, "w") as f:
                        f.write("sent")
        await asyncio.sleep(60)

async def 监听(事件: dict, server: OneBotWSServer):
    if 控制台打印事件 == True:
        print(json.dumps(事件))
    global 机器人ID
    if not 机器人ID and 事件.get("self_id"):
        机器人ID = 事件.get("self_id")
        print(f"[初始化] 机器人ID: {机器人ID}")
    await 监听发送成功事件(事件)

    消息类型 = 事件.get("message_type")
    群号 = 事件.get("group_id", 0)
    用户号 = 事件.get("user_id", 0)
    是否超级 = 是否超级用户(用户号)
    消息文本 = ""

    # 群消息处理
    if 事件.get("post_type") == "message" and 事件.get("message_type") == "group":
        async with 消息插入锁:
            包 = 打包(事件)
            插入消息数据(包)
        
        群号 = 包.get("群号")
        消息号 = 包.get("消息号")
        消息列表 = json.loads(包.get("消息", "[]"))
        asyncio.create_task(处理消息中的文件(群号, 消息号, 消息列表))
        
        消息文本 = "".join([
            msg.get("data", {}).get("text", "") 
            for msg in 事件.get("message", []) 
            if msg.get("type") == "text"
        ]).strip()
        
        消息内容列表 = 事件.get("message", [])
        if 消息内容列表:
            消息摘要 = []
            for msg in 消息内容列表:
                消息类型_单元 = msg.get("type")
                if 消息类型_单元 == "text":
                    text_content = msg.get("data", {}).get("text", "")
                    if text_content.strip():
                        消息摘要.append(f'文本:"{text_content[:50]}{"..." if len(text_content) > 50 else ""}"')
                elif 消息类型_单元 == "image":
                    消息摘要.append(f'[图片]')
                elif 消息类型_单元 == "video":
                    消息摘要.append(f'[视频]')
                elif 消息类型_单元 == "face":
                    消息摘要.append(f'[表情]')
                elif 消息类型_单元 == "at":
                    qq = msg.get("data", {}).get("qq", "")
                    消息摘要.append(f'[@QQ{qq}]')
                elif 消息类型_单元 == "reply":
                    reply_id = msg.get("data", {}).get("id", "")
                    消息摘要.append(f'[回复:{reply_id}]')
                elif 消息类型_单元 == "record":
                    消息摘要.append(f'[语音]')
                elif 消息类型_单元 == "file":
                    消息摘要.append(f'[文件]')
                else:
                    消息摘要.append(f'[{消息类型_单元}]')
            
            发送者昵称 = 事件.get("sender", {}).get("nickname", "未知用户")
            if 消息摘要:
                日志内容 = f"[消息记录] 群{群号} {发送者昵称}: " + " ".join(消息摘要)
                print(日志内容)
    
    # 私聊消息处理
    elif 事件.get("post_type") == "message" and 事件.get("message_type") == "private":
        消息文本 = "".join([
            msg.get("data", {}).get("text", "") 
            for msg in 事件.get("message", []) 
            if msg.get("type") == "text"
        ]).strip()

    # ========== 核心指令分发逻辑 ==========
    if 消息文本.strip():
        # 超级用户私聊指令
        if 消息类型 == "private" and 是否超级 and 功能开关["超级用户私聊功能"]:
            # 系统状态查询
            if any(kw in 消息文本 for kw in ["运行状态", "存储数据量", "系统状态", "查看状态", "看看状态"]):
                if 功能开关["系统状态查询功能"]:
                    状态信息 = 获取运行状态()
                    状态文本 = "主机状态：\n" + "\n".join([f"{k}: {v}" for k, v in 状态信息.items()])
                    if server._connections:
                        客户端ID = next(iter(server._connections.keys()))
                        try:
                            await server.call_api(
                                client_id=客户端ID,
                                action="send_private_msg",
                                params={"user_id": 用户号, "message": [{"type": "text", "data": {"text": 状态文本}}]},
                                timeout=10
                            )
                        except Exception as e:
                            print(f"[发送状态信息失败] {str(e)}")
                return
            
            # 提取目标群号
            群号匹配 = re.search(r"群(\d+)", 消息文本)
            目标群号 = int(群号匹配.group(1)) if 群号匹配 else 0
            print(f"[超级用户私聊指令] 用户{用户号}: {消息文本} | 目标群: {目标群号}")
            
            # 调用处理指令
            await 处理指令(消息文本, 目标群号, server, 用户号, 指令来源="private")
            return
        
        # 普通用户群指令
        elif 消息类型 == "group" and 功能开关["群聊查询功能"]:
            状态指令关键词 = ["运行状态", "存储数据量", "系统状态", "查看状态", "看看状态"]
            # 系统状态查询
            if any(kw == 消息文本.strip() for kw in 状态指令关键词):
                if 功能开关["系统状态查询功能"]:
                    print(f"[普通用户群指令] 群{群号} 用户{用户号}: 查看状态")
                    状态信息 = 获取运行状态()
                    状态文本 = "机器人当前运行状态：\n" + "\n".join([f"{k}: {v}" for k, v in 状态信息.items()])
                    if server._connections:
                        客户端ID = next(iter(server._connections.keys()))
                        try:
                            await 消息发送.随机延迟()
                            await server.call_api(
                                client_id=客户端ID,
                                action="send_group_msg",
                                params={"group_id": 群号, "message": [{"type": "text", "data": {"text": 状态文本}}]},
                                timeout=10
                            )
                            print(f"✅ [发送状态成功] 群 {群号}")
                        except Exception as e:
                            print(f"[发送状态信息失败] {str(e)}")
                return
            
            # ========== 查询指令判断：必须同时包含 机器人昵称 + 动词 + 名词 ==========
            包含动词 = any(词 in 消息文本 for 词 in 查询关键词组["动词"])
            包含名词 = any(词 in 消息文本 for 词 in 查询关键词组["名词"])
            包含机器人昵称 = any(词 in 消息文本 for 词 in 查询关键词组["机器人昵称"])
            是查询指令 = 包含动词 and 包含名词 and 包含机器人昵称 and not any(kw in 消息文本 for kw in 状态指令关键词)
            
            if 是查询指令:
                print(f"[普通用户群指令] 群{群号} 用户{用户号}: {消息文本}")
                await 处理指令(消息文本, 群号, server, 用户号, 指令来源="group")


def 生成事件处理器(server: OneBotWSServer):
    async def 处理器(事件: dict):
        await 监听(事件, server)
    return 处理器

if __name__ == "__main__":
    server = OneBotWSServer(host=监听地址, port=监听端口, access_token=Token)
    server.on_event(生成事件处理器(server))
    print("[服务启动] OneBot WS服务已开启")
    loop = asyncio.get_event_loop()
    loop.create_task(定时发送一言(server))
    loop.run_until_complete(server.start())
