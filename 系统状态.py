import psutil
import os
import time
from decimal import Decimal
from 数据库 import 获取连接
from 配置 import 数据库配置

def 获取存储数据量():
    """获取数据库总存储数据量（MB）"""
    try:
        with 获取连接() as conn:
            with conn.cursor() as 游标:
                游标.execute(f"""
                    SELECT table_schema, SUM(data_length + index_length) / 1024 / 1024 AS total_mb
                    FROM information_schema.tables
                    WHERE table_schema = '{数据库配置['数据库名']}'
                """)
                结果 = 游标.fetchone()
                return round(float(结果[1]) if 结果 else 0.0, 2)
    except Exception as e:
        print(f"[获取存储数据量失败] {str(e)}")
        return 0.0

def 获取运行状态():
    """获取机器人运行状态"""
    进程 = psutil.Process(os.getpid())
    运行时间 = round(time.time() - 进程.create_time(), 2)
    return {
        "CPU占用率(%)": round(进程.cpu_percent(interval=1), 2),
        "内存占用(MB)": round(进程.memory_info().rss / 1024 / 1024, 2),
        "运行时间(秒)": 运行时间,
        "数据库存储(MB)": 获取存储数据量()
    }
