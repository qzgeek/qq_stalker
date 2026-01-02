import aiohttp
import json
import uuid
from typing import Optional
import asyncio
from 配置 import AList配置, 文件最大上传体积, 重命名等待间隔, 重命名重试次数, 重命名重试间隔

TYPE_SUFFIX_MAP = {
    "image": ".jpg",
    "file": ".bin",
    "video": ".mp4",
    "record": ".amr"
}

ALIST_CONFIG = {
    "base_url": AList配置["上传地址"],
    "port": AList配置["端口"],
    "use_https": AList配置["上传HTTPS"],
    "token": AList配置["令牌"],
    "root_path": AList配置["根目录"],
    "max_size": 文件最大上传体积 * 1024 * 1024,
    "public_download_domain": AList配置["下载地址"]
}

DOWNLOAD_WAIT_TIME = 重命名等待间隔
RENAME_RETRY_TIMES = 重命名重试次数
RENAME_RETRY_INTERVAL = 重命名重试间隔

async def _get_alist_first_filename(alist_api_url: str, target_path: str) -> Optional[str]:
    headers = {
        'Authorization': ALIST_CONFIG["token"],
        'Content-Type': 'application/json'
    }
    payload = {
        "path": target_path,
        "password": "",
        "page": 1,
        "per_page": 10,
        "refresh": True
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url=f"{alist_api_url}/api/fs/list",
                headers=headers,
                data=json.dumps(payload),
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status != 200:
                    print(f"[List接口调用失败] 状态码: {resp.status}")
                    return None
                result = await resp.json()
                if result.get("code") != 200:
                    print(f"[List接口返回错误] {result.get('message')} | 目标路径: {target_path}")
                    return None
                file_list = [item for item in result.get("data", {}).get("content", []) if not item.get("is_dir")]
                if not file_list:
                    return None
                return file_list[0].get("name")
    except Exception as e:
        print(f"[List接口请求异常] {str(e)}")
        return None

async def _rename_alist_file(alist_api_url: str, file_path: str, new_name: str) -> bool:
    headers = {
        'Authorization': ALIST_CONFIG["token"],
        'Content-Type': 'application/json'
    }
    payload = {
        "path": file_path,
        "name": new_name
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url=f"{alist_api_url}/api/fs/rename",
                headers=headers,
                data=json.dumps(payload),
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                result = await resp.json()
                if resp.status == 200 and result.get("code") == 200:
                    print(f"[文件重命名成功] {file_path} -> {new_name}")
                    return True
                else:
                    print(f"[文件重命名失败] {result.get('message')} | 请求体: {payload}")
                    return False
    except Exception as e:
        print(f"[重命名请求异常] {str(e)}")
        return False

async def alist_offline_download(文件url: str, 原始文件名: str = "未知文件", 文件类型: str = "file", 文件体积: int = 0) -> Optional[str]:
    if 原始文件名 == "未知文件":
        后缀 = TYPE_SUFFIX_MAP.get(文件类型, ".bin")
        原始文件名 += 后缀

    uid = str(uuid.uuid4()).replace("-", "")
    target_path = f"{ALIST_CONFIG['root_path']}/{uid}"
    scheme = "https" if ALIST_CONFIG["use_https"] else "http"
    alist_api_url = f"{scheme}://{ALIST_CONFIG['base_url']}:{ALIST_CONFIG['port']}"

    headers = {
        'Authorization': ALIST_CONFIG["token"],
        'Content-Type': 'application/json'
    }
    payload = json.dumps({
        "path": target_path,
        "urls": [文件url],
        "tool": "aria2",
        "delete_policy": "delete_on_upload_succeed"
    })

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url=f"{alist_api_url}/api/fs/add_offline_download",
                headers=headers,
                data=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                result = await resp.json()
                if resp.status != 200 or result.get("code") != 200:
                    print(f"[离线下载任务创建失败] {result.get('message', '未知错误')}")
                    return None
        print(f"[离线下载任务创建成功] 存储目录: {target_path}")

        print(f"[等待文件下载] 等待 {DOWNLOAD_WAIT_TIME} 秒...")
        await asyncio.sleep(DOWNLOAD_WAIT_TIME)

        origin_filename = None
        for _ in range(3):
            origin_filename = await _get_alist_first_filename(alist_api_url, target_path)
            if origin_filename:
                break
            print(f"[重试获取文件名] 等待10秒后重试...")
            await asyncio.sleep(10)
        if not origin_filename:
            print(f"[获取文件名失败] 多次重试后仍无法获取，目录: {target_path}")
            return None

        valid_name = 原始文件名.replace("/", "_").replace("\\", "_").replace(":", "_").replace("*", "_").replace("?", "_").replace("\"", "_").replace("<", "_").replace(">", "_").replace("|", "_")
        old_file_path = f"{target_path}/{origin_filename}"
        rename_success = False
        for retry in range(RENAME_RETRY_TIMES + 1):
            if await _rename_alist_file(alist_api_url, old_file_path, valid_name):
                rename_success = True
                break
            else:
                if retry < RENAME_RETRY_TIMES:
                    print(f"[重命名重试] 剩余次数: {RENAME_RETRY_TIMES - retry} | 等待 {RENAME_RETRY_INTERVAL} 秒")
                    await asyncio.sleep(RENAME_RETRY_INTERVAL)
        if not rename_success:
            print(f"[重命名最终失败] 放弃重命名，使用原文件名: {origin_filename}")
            valid_name = origin_filename

        final_url = f"{ALIST_CONFIG['public_download_domain']}/d{ALIST_CONFIG['root_path']}/{uid}/{valid_name}"
        print(f"[离线下载完成] 最终链接: {final_url}")
        return final_url

    except Exception as e:
        print(f"[请求异常] {str(e)}")
        return None

def 检查文件大小(文件大小: str) -> bool:
    try:
        大小 = int(文件大小)
        最大体积 = int(ALIST_CONFIG["max_size"])
        return 大小 <= 最大体积
    except (ValueError, TypeError):
        print(f"[大小校验失败] 无效值: {文件大小}")
        return False
