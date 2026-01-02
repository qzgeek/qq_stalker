import json
from datetime import datetime, timedelta
import pymysql
from 数据库 import 获取连接
import re
from 配置 import 匹配消息上限
from ai工具 import 调用AI
from 系统状态 import 获取运行状态

async def ai驱动查询(消息文本: str, 群号: int, 用户号: int, 是否超级用户: bool, 消息上限: int = 匹配消息上限):
    角色 = "超级用户" if 是否超级用户 else "普通用户"
    ai结果 = await 调用AI(消息文本, 角色, 群号, 用户号)
    查询SQL = ai结果.get("query_sql", "")
    提示消息 = ai结果.get("prompt_msg", "正在查询，请稍候...")

    if 查询SQL.strip().upper() == "SELECT * FROM VIRTUAL_STATUS":
        if 是否超级用户:
            状态信息 = 获取运行状态()
            消息列表 = [{"系统状态": json.dumps(状态信息, ensure_ascii=False)}]
            return 消息列表, 提示消息
        else:
            return [], ""

    if not 查询SQL or not 查询SQL.strip().upper().startswith("SELECT"):
        print(f"[AI生成SQL无效] {查询SQL}")
        return [], 提示消息

    if "LIMIT" not in 查询SQL.upper():
        查询SQL += f" LIMIT {消息上限}"

    try:
        with 获取连接() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as 游标:
                游标.execute(查询SQL)
                结果列表 = 游标.fetchall()
                print(f"[SQL查询结果] 命中 {len(结果列表)} 条记录 | SQL: {查询SQL}")
                for 消息 in 结果列表:
                    if "消息" in 消息 and 消息["消息"]:
                        消息["消息"] = json.loads(消息["消息"])
        return 结果列表, 提示消息
    except Exception as e:
        print(f"[AI查询执行失败] {str(e)} | SQL: {查询SQL}")
        return [], "查询过程中出现错误，请稍后再试"

def 读取群消息(群号: int, 开始时间戳: int = None, 结束时间戳: int = None, 内容关键词: str = None, 消息上限: int = 匹配消息上限):
    表名 = f"g{群号}"
    sql = f"SELECT * FROM {表名} WHERE 1=1"
    params = []
    if 开始时间戳:
        sql += " AND 时间戳 >= %s"
        params.append(开始时间戳)
    if 结束时间戳:
        sql += " AND 时间戳 <= %s"
        params.append(结束时间戳)
    if 内容关键词:
        sql += " AND 消息 LIKE %s"
        params.append(f"%{内容关键词}%")
    sql += f" ORDER BY 时间戳 ASC LIMIT {消息上限}"

    try:
        with 获取连接() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as 游标:
                游标.execute(sql, params)
                结果列表 = 游标.fetchall()
                for 消息 in 结果列表:
                    消息["消息"] = json.loads(消息["消息"])
        return 结果列表
    except Exception as e:
        print(f"读取消息失败: {e}")
        return []

def 日期转时间戳(年: int, 月: int, 日: int):
    北京时间 = datetime(年, 月, 日, 0, 0, 0)
    UTC时间 = 北京时间 - timedelta(hours=8)
    开始时间戳 = int(UTC时间.timestamp())
    
    北京时间_结束 = datetime(年, 月, 日, 23, 59, 59)
    UTC时间_结束 = 北京时间_结束 - timedelta(hours=8)
    结束时间戳 = int(UTC时间_结束.timestamp())
    
    print(f"[时间转换] 北京时间: {年}-{月}-{日} 00:00:00 ~ 23:59:59")
    print(f"[时间转换] UTC时间戳: {开始时间戳} ~ {结束时间戳}")
    return 开始时间戳, 结束时间戳


# 该函数已弃用，但仍保留，备不时之需
# 该函数可删除
def 解析命令并查询(消息文本: str, 群号: int, 消息上限: int = 匹配消息上限):
    """
    自然语言指令解析
    支持多种自然语言表达方式
    """
    
    消息文本 = 消息文本.strip()
    print(f"[指令解析] 收到消息: {消息文本}")
    
    # 看看y年m月d日的消息
    日期匹配1 = re.search(r"看看(\d{4})年(\d{1,2})月(\d{1,2})日(?:的聊天记录|的消息|的聊天|的记录)?", 消息文本)
    if 日期匹配1:
        年, 月, 日 = map(int, 日期匹配1.groups())
        开始戳, 结束戳 = 日期转时间戳(年, 月, 日)
        print(f"[指令解析] 匹配到日期查询: {年}年{月}月{日}日")
        return 读取群消息(群号, 开始戳, 结束戳, 消息上限=消息上限)
    
    # 查看年/月/日的聊天
    日期匹配2 = re.search(r"(?:查看|看看|查询)(\d{4})[/\-年](\d{1,2})[/\-月](\d{1,2})日?", 消息文本)
    if 日期匹配2:
        年, 月, 日 = map(int, 日期匹配2.groups())
        开始戳, 结束戳 = 日期转时间戳(年, 月, 日)
        print(f"[指令解析] 匹配到日期查询(斜杠格式): {年}/{月}/{日}")
        return 读取群消息(群号, 开始戳, 结束戳, 消息上限=消息上限)
    
    # 今天
    if re.search(r"^(看看|查看|显示)?(今天|今日)(的聊天记录|的消息|的聊天|消息)?$", 消息文本):
        当前时间 = datetime.utcnow() + timedelta(hours=8)
        今天 = 当前时间.date()
        开始戳, 结束戳 = 日期转时间戳(今天.year, 今天.month, 今天.day)
        print(f"[指令解析] 匹配到今天查询: {今天}")
        return 读取群消息(群号, 开始戳, 结束戳, 消息上限=消息上限)
    
    # 昨天
    if re.search(r"^(看看|查看|显示)?(昨天|昨日)(的聊天记录|的消息|的聊天|消息)?$", 消息文本):
        当前时间 = datetime.utcnow() + timedelta(hours=8)
        昨天 = (当前时间 - timedelta(days=1)).date()
        开始戳, 结束戳 = 日期转时间戳(昨天.year, 昨天.month, 昨天.day)
        print(f"[指令解析] 匹配到昨天查询: {昨天}")
        return 读取群消息(群号, 开始戳, 结束戳, 消息上限=消息上限)
    
    # 前天
    if re.search(r"^(看看|查看|显示)?(前天)(的聊天记录|的消息|的聊天|消息)?$", 消息文本):
        当前时间 = datetime.utcnow() + timedelta(hours=8)
        前天 = (当前时间 - timedelta(days=2)).date()
        开始戳, 结束戳 = 日期转时间戳(前天.year, 前天.month, 前天.day)
        print(f"[指令解析] 匹配到前天查询: {前天}")
        return 读取群消息(群号, 开始戳, 结束戳, 消息上限=消息上限)
    
    # 找找包含"关键词"的消息
    关键词匹配1 = re.search(r'(?:找找|查找|搜索|查查)(?:一下)?包含[“"]([^"”]+)[”"]的消息', 消息文本)
    if 关键词匹配1:
        关键词 = 关键词匹配1.group(1)
        print(f"[指令解析] 匹配到关键词查询1: {关键词}")
        return 读取群消息(群号, 内容关键词=关键词, 消息上限=消息上限)
    
    # 搜索关于"关键词"的聊天
    关键词匹配2 = re.search(r'(?:搜索|查找|查查)(?:一下)?关于["“"]([^"”]+)[”"]的(?:聊天|消息)', 消息文本)
    if 关键词匹配2:
        关键词 = 关键词匹配2.group(1)
        print(f"[指令解析] 匹配到关键词查询2: {关键词}")
        return 读取群消息(群号, 内容关键词=关键词, 消息上限=消息上限)
    
    # 谁说过"关键词"
    谁说过匹配 = re.search(r'谁(?:说过|提到|讨论过)[\"\']([^\"\']+)[\"\']', 消息文本)
    if 谁说过匹配:
        关键词 = 谁说过匹配.group(1)
        print(f"[指令解析] 匹配到谁说过查询: {关键词}")
        return 读取群消息(群号, 内容关键词=关键词, 消息上限=消息上限)
    
    # 最近消息
    if re.search(r'^(看看|查看|显示)?最近(?:的聊天记录|的消息|的聊天|消息)?$', 消息文本):
        当前时间 = datetime.utcnow() + timedelta(hours=8)
        三天前 = (当前时间 - timedelta(days=3)).date()
        开始戳, 结束戳 = 日期转时间戳(三天前.year, 三天前.month, 三天前.day)
        print(f"[指令解析] 匹配到最近消息查询(3天)")
        return 读取群消息(群号, 开始戳, 结束戳, 消息上限=消息上限)
    
    # 最近n分钟的消息（中文数字）
    时间匹配1 = re.search(r'最近[一二三四五六七八九十两]?[分时]钟?(?:的消息|聊天|的聊天|的聊天记录)', 消息文本)
    if 时间匹配1:
        # 提取中文数字
        中文数字映射 = {
            '一': 1, '二': 2, '两': 2, '三': 3, '四': 4, 
            '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10
        }
        
        匹配文本 = 时间匹配1.group()
        if '小时' in 匹配文本 or '时' in 匹配文本 or '钟' in 匹配文本:
            单位 = '小时'
        else:
            单位 = '分钟'
        
        # 提取数字
        for 中文, 数字 in 中文数字映射.items():
            if 中文 in 匹配文本:
                数量 = 数字
                break
        else:
            # 如果没有明确数字，默认为5
            数量 = 5
        
        print(f"[指令解析] 匹配到中文时间查询: 最近{数量}{单位}")
        结束时间 = datetime.utcnow()
        
        if 单位 == '小时':
            开始时间 = 结束时间 - timedelta(hours=数量)
        else:
            开始时间 = 结束时间 - timedelta(minutes=数量)
        
        开始戳 = int(开始时间.timestamp())
        结束戳 = int(结束时间.timestamp())
        print(f"[指令解析] UTC时间戳范围: {开始戳} ~ {结束戳}")
        return 读取群消息(群号, 开始戳, 结束戳, 消息上限=消息上限)
    
    # 最近n分钟的消息（阿拉伯数字）
    时间匹配2 = re.search(r'最近(\d+)(分钟|分|小时|时)(?:的消息|聊天|的聊天|的聊天记录)?', 消息文本)
    if 时间匹配2:
        数量, 单位 = 时间匹配2.groups()
        数量 = int(数量)
        
        结束时间 = datetime.utcnow()
        
        if '小时' in 单位 or '时' in 单位:
            开始时间 = 结束时间 - timedelta(hours=数量)
        else:
            开始时间 = 结束时间 - timedelta(minutes=数量)
        
        开始戳 = int(开始时间.timestamp())
        结束戳 = int(结束时间.timestamp())
        # 修复：使用传入的消息上限，而非固定值
        print(f"[指令解析] 匹配到时间范围查询: 最近{数量}{单位}")
        print(f"[指令解析] UTC时间戳范围: {开始戳} ~ {结束戳}")
        return 读取群消息(群号, 开始戳, 结束戳, 消息上限=消息上限)
    
    # 最近n分钟的消息（简写）
    时间匹配3 = re.search(r'最近(\d+)分钟?(?:的消息|聊天|的聊天)', 消息文本)
    if 时间匹配3:
        数量 = int(时间匹配3.group(1))
        
        结束时间 = datetime.utcnow()
        开始时间 = 结束时间 - timedelta(minutes=数量)
        
        开始戳 = int(开始时间.timestamp())
        结束戳 = int(结束时间.timestamp())
        # 修复：使用传入的消息上限，而非固定值
        print(f"[指令解析] 匹配到简写时间查询: 最近{数量}分钟")
        print(f"[指令解析] UTC时间戳范围: {开始戳} ~ {结束戳}")
        return 读取群消息(群号, 开始戳, 结束戳, 消息上限=消息上限)
    
    # 最近一小时
    if re.search(r'^(看看|查看|显示)?(最近一小时|一小时内的消息|最近1小时的消息|一小时的消息)$', 消息文本):
        结束时间 = datetime.utcnow()
        开始时间 = 结束时间 - timedelta(hours=1)
        开始戳 = int(开始时间.timestamp())
        结束戳 = int(结束时间.timestamp())
        print(f"[指令解析] 匹配到最近一小时查询")
        # 修复：使用传入的消息上限，而非固定值20
        return 读取群消息(群号, 开始戳, 结束戳, 消息上限=消息上限)
    
    # 看看群聊天记录/显示聊天记录
    if re.search(r'^(看看|查看|显示)(?:一下)?(?:群)?聊天记录$', 消息文本):
        当前时间 = datetime.utcnow() + timedelta(hours=8)
        昨天 = (当前时间 - timedelta(days=1)).date()
        开始戳, 结束戳 = 日期转时间戳(昨天.year, 昨天.month, 昨天.day)
        print(f"[指令解析] 匹配到聊天记录查询")
        return 读取群消息(群号, 开始戳, 结束戳, 消息上限=消息上限)
    
    # === 7. 查看所有消息（需要明确指令）===
    if re.search(r'^(看看|查看|显示)(?:一下)?(?:所有|全部)(?:的)?(?:聊天记录|消息)$', 消息文本):
        print(f"[指令解析] 匹配到查看所有消息查询")
        # 修复：使用传入的消息上限，而非固定值100
        return 读取群消息(群号, 消息上限=消息上限)
    
    print(f"[指令解析] 未匹配到任何指令")
    return []
