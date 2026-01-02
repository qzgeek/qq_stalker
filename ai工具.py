import aiohttp
import json
import re
from datetime import datetime, timedelta
from 配置 import AI配置

# 获取当前北京时间和时间戳
def get_current_beijing_time_info():
    # 计算北京时间（UTC+8）
    beijing_time = datetime.utcnow() + timedelta(hours=8)
    # 当天0点和23:59:59的时间戳
    today_start = datetime(beijing_time.year, beijing_time.month, beijing_time.day, 0, 0, 0)
    today_end = datetime(beijing_time.year, beijing_time.month, beijing_time.day, 23, 59, 59)
    # 转换为时间戳
    current_timestamp = int(beijing_time.timestamp())
    today_start_timestamp = int(today_start.timestamp())
    today_end_timestamp = int(today_end.timestamp())
    
    return {
        "current_time": beijing_time.strftime("%Y-%m-%d %H:%M:%S"),
        "current_timestamp": current_timestamp,
        "today_start": today_start.strftime("%Y-%m-%d 00:00:00"),
        "today_start_timestamp": today_start_timestamp,
        "today_end": today_end.strftime("%Y-%m-%d 23:59:59"),
        "today_end_timestamp": today_end_timestamp
    }

系统提示词 = """
你是一个群聊记录查询机器人的AI助手，必须严格按照以下要求输出，无任何多余内容，仅返回标准JSON字符串。
 
一、核心规则（强制执行，不可违反）
 
操作限制
- 仅允许生成 SELECT 查询语句，禁止生成 INSERT/UPDATE/DELETE 等任何修改类语句
- 禁止使用函数、子查询、JOIN 等复杂语法，仅支持基础 WHERE 筛选和 LIMIT 限制
- 排序规则：用户未指定排序方式时，默认添加  ORDER BY 时间戳 ASC  正序排列；用户明确要求正序/逆序时，按用户指令调整排序方式
表名规则
- 群聊数据存储表名格式为： g + 群号 
- 示例：群号 1054140738 → 表名  g1054140738 ；群号 906314036 → 表名  g906314036 
- 绝对禁止使用用户号、昵称等作为表名
- 普通用户必须使用指令传入的群号生成表名，禁止使用其他群号
可用字段
- 固定字段列表：消息号、人机号、用户号、时间戳、群昵称、昵称、群名、群号、长度、消息
- 仅可使用上述字段进行筛选，禁止使用字段列表外的名称
权限限制
- 超级用户：可查询任意群聊数据 + 可查询系统状态（固定 SQL：SELECT * FROM virtual_status）
- 普通用户：仅能查询指令发出群聊的数据，禁止查询其他群聊；绝对禁止查询 virtual_status 表
- 普通用户查询其他群聊、查询系统状态的指令，直接返回空 SQL（query_sql 为空字符串）
时间计算规则（关键！）
- 我会提供当前北京时间、当天0点/23:59:59的时间戳
- 你需要根据用户指令计算目标日期的时间戳范围：
今天：使用提供的 today_start_timestamp ~ today_end_timestamp
昨天：today_start_timestamp - 86400 ~ today_end_timestamp - 86400 （86400=1天秒数）
前天：today_start_timestamp - 172800 ~ today_end_timestamp - 172800 （172800=2天秒数）
- 禁止使用任何占位符（如{今天开始戳}），必须填入具体的数字时间戳
用户指定排序支持规则
- 用户指令包含“正序”“按时间正序”“最早到最晚”等表述时，使用  ORDER BY 时间戳 ASC 
- 用户指令包含“逆序”“倒序”“按时间逆序”“最新到最早”等表述时，使用  ORDER BY 时间戳 DESC 
- 用户未指定排序方式时，默认使用  ORDER BY 时间戳 ASC  正序排列
 
二、典型场景示例（覆盖90%用户指令，严格参考格式）
 
场景1：普通用户查询本群前天所有消息（默认正序）
 
- 输入信息：当前北京时间 2026-01-05 10:00:00，today_start_timestamp=1736025600，today_end_timestamp=1736111999
- 用户指令：发一下前天的聊天记录
- 计算逻辑：前天时间戳 = 今天戳 - 2*86400 → 1735852800 ~ 1735939199
- 正确输出：
{"query_sql": "SELECT * FROM g906314036 WHERE 时间戳 >= 1735852800 AND 时间戳 <= 1735939199 ORDER BY 时间戳 ASC LIMIT 400", "prompt_msg": "正在查询本群前天的聊天记录"}
 
场景2：普通用户查询自身今日发言（指定逆序）
 
- 输入信息：当前北京时间 2026-01-05 10:00:00，today_start_timestamp=1736025600，today_end_timestamp=1736111999
- 用户指令：帮我看看我今天都说了些啥，按时间逆序
- 用户号：190759468，群号：1054140738
- 正确输出：
{"query_sql": "SELECT * FROM g1054140738 WHERE 用户号 = 190759468 AND 时间戳 >= 1736025600 AND 时间戳 <= 1736111999 ORDER BY 时间戳 DESC LIMIT 400", "prompt_msg": "正在查询你今天在本群的发言记录"}
 
场景3：普通用户查询昨天消息（指定正序）
 
- 输入信息：当前北京时间 2026-01-05 10:00:00，today_start_timestamp=1736025600，today_end_timestamp=1736111999
- 用户指令：发昨天的聊天记录，要最早到最晚的顺序
- 群号：906314036
- 计算逻辑：昨天时间戳 = 今天戳 - 86400 → 1735939200 ~ 1736025599
- 正确输出：
{"query_sql": "SELECT * FROM g906314036 WHERE 时间戳 >= 1735939200 AND 时间戳 <= 1736025599 ORDER BY 时间戳 ASC LIMIT 400", "prompt_msg": "正在查询本群昨天的聊天记录"}
 
场景4：普通用户越权查询（直接返回空）
 
- 用户指令：查询群906314036的消息
- 已知条件：普通用户，指令群号 1054140738
- 正确输出：
{"query_sql": "", "prompt_msg": "你无权限查询其他群聊的消息"}
 
场景5：用户要求查询明天消息（违反常识，无视指令）
 
- 用户指令：发一下明天的聊天记录
- 已知条件：普通用户，指令群号 906314036
- 正确输出：
{"query_sql": "", "prompt_msg": "无法查询未发生的聊天记录"}
 
三、输出格式要求（严格遵守，缺一不可）
 
仅返回一个 JSON 对象，包含且仅包含两个字段：
- query_sql：生成的查询语句（符合上述规则），无权限/无法解析时为空字符串
- prompt_msg：给用户的提示文案，简洁友好，不超过20字
JSON 字符串必须合法，无语法错误，无多余逗号、引号
禁止输出任何解释性文字、代码块标记（如 ```json）、注释等内容
 
四、 注意
 
人不可能知道明天的聊天记录的，当你被问到这类违反常识的指令时，应当无视该问题，返回空查询语句和对应提示
"""

# 系统状态关键词兜底
系统状态关键词 = ["状态", "运行状态", "系统状态", "存储数据量"]

async def 调用AI(消息内容: str, 角色: str = "普通用户", 群号: int = None, 用户号: int = None) -> dict:
    # 超级用户查状态，直接返回虚拟表SQL，跳过AI调用
    if 角色 == "超级用户" and any(kw in 消息内容 for kw in 系统状态关键词):
        return {
            "query_sql": "SELECT * FROM virtual_status",
            "prompt_msg": "正在查询系统状态，请稍候~"
        }

    # 获取当前北京时间和时间戳信息
    time_info = get_current_beijing_time_info()

    """
    调用AI接口生成查询语句和提示消息，增加嵌套JSON解析容错
    :param 消息内容: 用户指令
    :param 角色: 普通用户/超级用户
    :param 群号: 普通用户指令所在群号
    :param 用户号: 指令发送者QQ号
    :return: {"query_sql": str, "prompt_msg": str}
    """
    # 核心修改：把时间信息传给AI，让AI计算具体时间戳
    用户提示词 = f"""
角色：{角色}
指令发送者QQ号：{用户号}
指令所在群号：{群号}
**当前时间信息（北京时间）**：
- 当前时间：{time_info['current_time']}
- 当前时间戳：{time_info['current_timestamp']}
- 今天0点时间戳：{time_info['today_start_timestamp']}
- 今天23:59:59时间戳：{time_info['today_end_timestamp']}
**强制要求**：
1.  普通用户只能查询群{群号}的数据，表名必须为g{群号}，禁止使用其他群号！
2.  时间筛选必须用具体数字时间戳，禁止用任何占位符！
用户指令：{消息内容}
**注意：输出必须是标准JSON，无任何多余内容，严格遵守系统提示词示例格式**
"""

    headers = {
        "Authorization": f"Bearer {AI配置['key']}",
        "Content-Type": "application/json"
    }
    data = {
        "model": AI配置["model"],
        "messages": [
            {"role": "system", "content": 系统提示词},
            {"role": "user", "content": 用户提示词}
        ],
        "max_tokens": AI配置["max_tokens"],
        "temperature": 0.1,
        "stop": None
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                AI配置["url"],
                headers=headers,
                data=json.dumps(data, ensure_ascii=False),
                timeout=AI配置["timeout"]
            ) as resp:
                if resp.status != 200:
                    print(f"[AI调用失败] 状态码：{resp.status}，响应内容：{await resp.text()}")
                    return {"query_sql": "", "prompt_msg": "正在处理你的请求，请稍候..."}
                
                # 1. 先解析完整的AI接口响应
                接口响应 = json.loads(await resp.text())
                # 2. 提取assistant返回的content字段（核心目标JSON）
                ai_content = 接口响应["choices"][0]["message"]["content"].strip()
                print(f"[AI提取的content] {ai_content}")

                # 3. 容错解析JSON，去掉可能的```json标记
                ai_content = re.sub(r"^```json|```$", "", ai_content).strip()
                try:
                    return json.loads(ai_content)
                except json.JSONDecodeError:
                    print(f"[AI格式错误] 无法解析content中的JSON: {ai_content}")
                    return {"query_sql": "", "prompt_msg": "正在处理你的请求，请稍候..."}
    except Exception as e:
        print(f"[AI调用异常] {str(e)}")
        return {"query_sql": "", "prompt_msg": "正在处理你的请求，请稍候..."}
