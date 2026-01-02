import asyncio
import json
import random
from 配置 import 单条合并消息上限, 单次查询最大合并数, 消息发送延迟范围, 分片发送延迟范围

async def 随机延迟():
    延迟秒数 = random.randint(*消息发送延迟范围)
    print(f"[发送延迟] 等待 {延迟秒数} 秒后发送消息")
    await asyncio.sleep(延迟秒数)

async def 分片随机延迟():
    延迟秒数 = random.randint(*分片发送延迟范围)
    print(f"[分片延迟] 等待 {延迟秒数} 秒后发送下一分片")
    await asyncio.sleep(延迟秒数)

def 拆分消息分片(消息列表: list) -> list:
    分片列表 = []
    总条数 = len(消息列表)
    for i in range(0, 总条数, 单条合并消息上限):
        分片 = 消息列表[i:i + 单条合并消息上限]
        分片列表.append(分片)
    return 分片列表

def 生成超限提示消息(剩余条数: int, 原始群昵称: str, 原始时间戳: int) -> dict:
    from 合并工具 import 时间戳转北京时间
    提示文本 = f"⚠️ 本次查询还有 {剩余条数} 条消息未展示，已达到单次查询3条合并消息上限"
    return {
        "type": "node",
        "data": {
            "user_id": 0,
            "nickname": f"系统提示({时间戳转北京时间(原始时间戳)})",
            "content": [{"type": "text", "data": {"text": 提示文本}}]
        }
    }

def 过滤合并消息类型(合并消息: dict) -> dict:
    过滤后的_messages = []
    for node in 合并消息.get("messages", []):
        content = node.get("data", {}).get("content", [])
        过滤后的_content = [
            item for item in content 
            if item.get("type") in ["text", "face", "at", "reply"]
        ]
        if 过滤后的_content:
            node["data"]["content"] = 过滤后的_content
            过滤后的_messages.append(node)
    合并消息["messages"] = 过滤后的_messages
    return 合并消息

async def 发送提示消息(server, 客户端ID, 指令来源, 目标ID, 提示消息):
    try:
        if 指令来源 == "group":
            提示参数 = {
                "group_id": 目标ID,
                "message": [{"type": "text", "data": {"text": 提示消息}}]
            }
            await server.call_api(client_id=客户端ID, action="send_group_msg", params=提示参数, timeout=10)
        else:
            提示参数 = {
                "user_id": 目标ID,
                "message": [{"type": "text", "data": {"text": 提示消息}}]
            }
            await server.call_api(client_id=客户端ID, action="send_private_msg", params=提示参数, timeout=10)
    except Exception as e:
        print(f"[发送提示消息失败] {str(e)}")

async def 分片发送消息(server, 结果, 指令来源, 目标ID, 用户号=None):
    from 合并工具 import 转换消息数据

    消息分片列表 = 拆分消息分片(结果)
    总分片数 = len(消息分片列表)
    实际发送分片数 = min(总分片数, 单次查询最大合并数)
    print(f"[分片处理] 总分片数: {总分片数} | 实际发送: {实际发送分片数}")
    
    if not server._connections:
        print("[错误] 无客户端连接")
        return
    客户端ID = next(iter(server._connections.keys()))

    for 分片索引 in range(实际发送分片数):
        当前分片 = 消息分片列表[分片索引]
        合并消息 = 转换消息数据(当前分片)

        if 分片索引 == 实际发送分片数 - 1 and 总分片数 > 实际发送分片数:
            剩余条数 = len(结果) - 单条合并消息上限 * 实际发送分片数
            原始消息 = 结果[0]
            原始群昵称 = 原始消息.get("群昵称", "系统")
            原始时间戳 = 原始消息.get("时间戳", int(asyncio.get_event_loop().time()))
            提示消息_node = 生成超限提示消息(剩余条数, 原始群昵称, 原始时间戳)
            合并消息["messages"].insert(0, 提示消息_node)
            print(f"[超限提示] 已添加提示，剩余 {剩余条数} 条消息未发送")

        try:
            if 指令来源 == "group":
                合并消息["group_id"] = 目标ID
                响应 = await server.call_api(
                    client_id=客户端ID,
                    action="send_group_forward_msg",
                    params=合并消息,
                    timeout=60
                )
                发送标识 = f"群 {目标ID}"
            else:
                合并消息["user_id"] = 用户号
                响应 = await server.call_api(
                    client_id=客户端ID,
                    action="send_private_forward_msg",
                    params=合并消息,
                    timeout=60
                )
                发送标识 = f"私聊 {用户号}"

            if 响应.get("status") == "ok":
                print(f"✅ [分片发送成功] {发送标识} | 分片 {分片索引+1}/{实际发送分片数}")
            else:
                print(f"[分片发送失败] {发送标识} | 分片 {分片索引+1} | 响应: {json.dumps(响应, ensure_ascii=False)}")
                过滤后的合并消息 = 过滤合并消息类型(合并消息)
                if 指令来源 == "group":
                    响应 = await server.call_api(
                        client_id=客户端ID,
                        action="send_group_forward_msg",
                        params=过滤后的合并消息,
                        timeout=60
                    )
                else:
                    响应 = await server.call_api(
                        client_id=客户端ID,
                        action="send_private_forward_msg",
                        params=过滤后的合并消息,
                        timeout=60
                    )
                if 响应.get("status") == "ok":
                    print(f"✅ [分片重发成功] {发送标识} | 分片 {分片索引+1}")
                else:
                    print(f"[分片重发失败] {发送标识} | 分片 {分片索引+1}")
        except asyncio.TimeoutError:
            print(f"[分片超时] {发送标识} | 分片 {分片索引+1}")
            过滤后的合并消息 = 过滤合并消息类型(合并消息)
            try:
                if 指令来源 == "group":
                    响应 = await server.call_api(
                        client_id=客户端ID,
                        action="send_group_forward_msg",
                        params=过滤后的合并消息,
                        timeout=60
                    )
                else:
                    响应 = await server.call_api(
                        client_id=客户端ID,
                        action="send_private_forward_msg",
                        params=过滤后的合并消息,
                        timeout=60
                    )
                if 响应.get("status") == "ok":
                    print(f"✅ [分片超时重发成功] {发送标识} | 分片 {分片索引+1}")
            except Exception as e:
                print(f"[分片超时重发失败] {发送标识} | 分片 {分片索引+1}: {str(e)}")
        except Exception as e:
            print(f"[分片异常] {发送标识} | 分片 {分片索引+1}: {str(e)}")
            过滤后的合并消息 = 过滤合并消息类型(合并消息)
            try:
                if 指令来源 == "group":
                    响应 = await server.call_api(
                        client_id=客户端ID,
                        action="send_group_forward_msg",
                        params=过滤后的合并消息,
                        timeout=60
                    )
                else:
                    响应 = await server.call_api(
                        client_id=客户端ID,
                        action="send_private_forward_msg",
                        params=过滤后的合并消息,
                        timeout=60
                    )
                if 响应.get("status") == "ok":
                    print(f"✅ [分片异常重发成功] {发送标识} | 分片 {分片索引+1}")
            except Exception as e2:
                print(f"[分片异常重发失败] {发送标识} | 分片 {分片索引+1}: {str(e2)}")

        if 分片索引 < 实际发送分片数 - 1:
            await 分片随机延迟()

    if 总分片数 > 实际发送分片数:
        print(f"[查询超限] {发送标识} 本次查询共 {总分片数} 个分片，已截断至 {实际发送分片数} 个")
