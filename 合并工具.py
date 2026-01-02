import time
import json
from datetime import datetime, timedelta
from 配置 import 文件最大发送体积

MAX_FILE_SIZE = 文件最大发送体积 * 1024 * 1024

TYPE_SUFFIX_MAP = {
    "image": ".jpg",
    "file": ".bin",
    "video": ".mp4",
    "record": ".amr"
}

def 时间戳转北京时间(时间戳):
    """
    时间戳转北京时间，兼容None和非整数情况
    """
    if not 时间戳:
        return "未知时间"
    # 确保时间戳为整数
    try:
        时间戳_int = int(时间戳)
    except (ValueError, TypeError):
        return "未知时间"
    北京时 = datetime.utcfromtimestamp(时间戳_int) + timedelta(hours=8)
    return 北京时.strftime("%Y-%m-%d %H:%M:%S")

def 转换消息数据(查询结果列表):
    合并消息 = {
        "group_id": "",
        "messages": [],
        "news": [],
        "prompt": "[聊天记录]",
        "summary": "[聊天记录]",
        "source": "群聊的聊天记录"
    }

    if not 查询结果列表:
        return 合并消息

    合并消息["group_id"] = 查询结果列表[0].get("群号") or 查询结果列表[0].get("群 号") or ""

    for 单条消息 in 查询结果列表:
        用户号 = 单条消息.get("用户号") or 单条消息.get(" 用户号") or 0
        原始群昵称 = 单条消息.get("群昵称") or "未知用户"
        消息时间戳 = 单条消息.get("时间戳")
        带时间戳昵称 = f"{原始群昵称}({时间戳转北京时间(消息时间戳)})"
        原始消息内容列表 = json.loads(单条消息.get("消息", "[]")) if isinstance(单条消息.get("消息"), str) else 单条消息.get("消息", [])

        消息内容节点 = []
        单条消息文本 = ""
        文本内容 = []

        for 消息单元 in 原始消息内容列表:
            消息类型 = 消息单元.get("type")
            消息数据 = 消息单元.get("data", {})

            if 消息类型 == "image":
                file_size = int(消息数据.get("file_size", 0))
                img_url = 消息数据.get("url", "未知链接")
                file_name = 消息数据.get("file", "未知图片")
                if file_size > MAX_FILE_SIZE:
                    text_node = {
                        "type": "text",
                        "data": {"text": f"[图片：{file_name} {img_url}]"}
                    }
                    消息内容节点.append(text_node)
                    单条消息文本 += f"[图片：{file_name} {img_url}]"
                else:
                    消息内容节点.append({
                        "type": 消息类型,
                        "data": {
                            "file": file_name,
                            "url": img_url
                        }
                    })
                    单条消息文本 += f"[图片:{file_name}]"
                continue

            if 消息类型 == "video":
                file_size = int(消息数据.get("file_size", 0))
                video_url = 消息数据.get("url", "未知链接")
                file_name = 消息数据.get("file", "未知视频")
                if file_size > MAX_FILE_SIZE:
                    text_node = {
                        "type": "text",
                        "data": {"text": f"[视频：{file_name} {video_url}]"}
                    }
                    消息内容节点.append(text_node)
                    单条消息文本 += f"[视频：{file_name} {video_url}]"
                else:
                    消息内容节点.append({
                        "type": 消息类型,
                        "data": {
                            "file": file_name,
                            "url": video_url
                        }
                    })
                    单条消息文本 += f"[视频:{file_name}]"
                continue

            if 消息类型 == "file":
                file_size = int(消息数据.get("file_size", 0))
                file_url = 消息数据.get("url", "未知链接")
                file_name = 消息数据.get("file", "未知文件")
                
                if not file_url and "file_id" in 消息数据:
                    text_node = {
                        "type": "text",
                        "data": {"text": "[群文件]"}
                    }
                    消息内容节点.append(text_node)
                    单条消息文本 += "[群文件]"
                    continue

                if file_size > MAX_FILE_SIZE:
                    text_node = {
                        "type": "text",
                        "data": {"text": f"[文件：{file_name} {file_url}]"}
                    }
                    消息内容节点.append(text_node)
                    单条消息文本 += f"[文件：{file_name} {file_url}]"
                else:
                    消息内容节点.append({
                        "type": 消息类型,
                        "data": {
                            "name": file_name,
                            "size": file_size,
                            "url": file_url
                        }
                    })
                    单条消息文本 += f"[文件:{file_name}]"
                continue

            if 消息类型 == "record":
                file_size = int(消息数据.get("file_size", 0))
                record_url = 消息数据.get("url", "未知链接")
                file_name = 消息数据.get("file", "未知语音")
                if file_size > MAX_FILE_SIZE:
                    text_node = {
                        "type": "text",
                        "data": {"text": f"[语音：{file_name} {record_url}]"}
                    }
                    消息内容节点.append(text_node)
                    单条消息文本 += f"[语音：{file_name} {record_url}]"
                else:
                    消息内容节点.append({
                        "type": 消息类型,
                        "data": {
                            "file": file_name,
                            "url": record_url
                        }
                    })
                    单条消息文本 += f"[语音:{file_name}]"
                continue

            if 消息类型 in ["text", "face", "at", "reply"]:
                if 消息类型 == "face":
                    处理后数据 = {"id": 消息数据.get("id", 0)}
                    单条消息文本 += f"[表情:{消息数据.get('id', 0)}]"
                    消息内容节点.append({
                        "type": 消息类型,
                        "data": 处理后数据
                    })
                elif 消息类型 == "at":
                    处理后数据 = 消息数据
                    at_qq = 消息数据.get("qq", "")
                    单条消息文本 += f"@QQ{at_qq}"
                    消息内容节点.append({
                        "type": 消息类型,
                        "data": 处理后数据
                    })
                elif 消息类型 == "reply":
                    处理后数据 = 消息数据
                    reply_id = 消息数据.get("id", "")
                    单条消息文本 += f"[回复:{reply_id}]"
                    消息内容节点.append({
                        "type": 消息类型,
                        "data": 处理后数据
                    })
                elif 消息类型 == "text":
                    文本 = 消息数据.get("text", "")
                    if 文本:
                        文本内容.append(文本)
                        单条消息文本 += 文本
                        消息内容节点.append({
                            "type": 消息类型,
                            "data": 消息数据
                        })
            else:
                类型文本 = f"[{消息类型}]"
                单条消息文本 += 类型文本
                消息内容节点.append({
                    "type": "text",
                    "data": {"text": 类型文本}
                })
        
        if not 消息内容节点 and 单条消息文本:
            消息内容节点.append({
                "type": "text",
                "data": {"text": 单条消息文本}
            })
        
        if len(消息内容节点) == 0:
            for 文本 in 文本内容:
                消息内容节点.append({
                    "type": "text",
                    "data": {"text": 文本}
                })

        合并消息["messages"].append({
            "type": "node",
            "data": {
                "user_id": 用户号,
                "nickname": 带时间戳昵称,
                "content": 消息内容节点
            }
        })
        合并消息["news"].append({"text": f"{原始群昵称}：{单条消息文本}"})

    合并消息["news"] = 合并消息["news"][:3]

    return 合并消息
