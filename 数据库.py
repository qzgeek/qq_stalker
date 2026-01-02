import pymysql
from dbutils.pooled_db import PooledDB
import json
from 配置 import 数据库配置

DB_CONFIG = {
    "host": 数据库配置["主机地址"],
    "port": 数据库配置["端口"],
    "user": 数据库配置["用户名"],
    "password": 数据库配置["密码"],
    "database": 数据库配置["数据库名"],
    "charset": 数据库配置["字符编码"],
    "maxconnections": 数据库配置["最大连接数"],
    "mincached": 数据库配置["最小缓存连接数"],
    "maxcached": 数据库配置["最大缓存连接数"],
    "blocking": 数据库配置["连接阻塞"]
}

POOL = PooledDB(creator=pymysql,** DB_CONFIG)

def 获取连接():
    return POOL.connection()

## 此处不慎将用户昵称写记了“群昵称”，“昵称”才是群昵称并且目前记录的都是空值。作者临近开源才发现这个Bug，懒得修了，等之后第二版一起修_(:зゝ∠)_
def 创建群表(群号: int) -> str:
    表名 = f"g{群号}"
    创建表SQL = f"""
    CREATE TABLE IF NOT EXISTS {表名} (
        消息号 BIGINT PRIMARY KEY COMMENT '消息ID',
        人机号 BIGINT COMMENT '机器人QQ号',
        用户号 BIGINT COMMENT '发送者QQ号',
        时间戳 BIGINT NOT NULL COMMENT '消息发送时间戳',
        群昵称 VARCHAR(50) COMMENT '群友用户名',
        昵称 VARCHAR(50) COMMENT '群友群昵称',
        群名 VARCHAR(100) COMMENT '群名称',
        群号 BIGINT COMMENT '群号',
        长度 INT COMMENT '消息文字内容长度（应该吧）',
        消息 TEXT COMMENT '消息内容',
        INDEX idx_timestamp (时间戳)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='群{群号}消息记录表';
    """
    try:
        with 获取连接() as conn:
            with conn.cursor() as 游标:
                游标.execute(创建表SQL)
            conn.commit()
        return 表名
    except Exception as e:
        print(f"创建表失败: {e}")
        return ""

def 插入消息数据(消息包: dict):
    群号 = 消息包.get("群号")
    if not 群号:
        return
    表名 = 创建群表(群号)
    if not 表名:
        return

    插入SQL = f"""
    INSERT INTO {表名} 
    (消息号,人机号,用户号,时间戳,群昵称,昵称,群名,群号,长度,消息)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    ON DUPLICATE KEY UPDATE 消息=VALUES(消息);
    """
    数据元组 = (
        消息包.get("消息号", 0),
        消息包.get("人机号", 0),
        消息包.get("用户号", 0),
        消息包.get("时间戳", 0),
        消息包.get("群昵称", ""),
        消息包.get("昵称", ""),
        消息包.get("群名", ""),
        消息包.get("群号", 0),
        消息包.get("长度", 0),
        消息包.get("消息", "")
    )
    try:
        with 获取连接() as conn:
            with conn.cursor() as 游标:
                游标.execute(插入SQL, 数据元组)
            conn.commit()
    except Exception as e:
        print(f"插入消息失败: {e}")

def 更新消息文件url(群号: int, 消息号: int, 原消息列表: list, 新文件url: str, 消息单元索引: int) -> bool:
    """
    更新数据库中指定消息的文件url
    :param 群号: 群聊ID
    :param 消息号: 消息唯一ID
    :param 原消息列表: 原始的消息array列表
    :param 新文件url: Alist返回的新文件链接
    :param 消息单元索引: 消息列表中要修改的文件单元索引
    :return: 成功返回True，失败返回False
    """
    表名 = f"g{群号}"
    try:
        # 修改指定索引的消息单元的url
        原消息列表[消息单元索引]["data"]["url"] = 新文件url
        新消息内容 = json.dumps(原消息列表, ensure_ascii=False)

        # 执行更新SQL
        with 获取连接() as conn:
            with conn.cursor() as 游标:
                更新SQL = f"UPDATE {表名} SET 消息 = %s WHERE 消息号 = %s"
                游标.execute(更新SQL, (新消息内容, 消息号))
                conn.commit()
        return 游标.rowcount > 0
    except Exception as e:
        print(f"更新文件url失败: {e}")
        return False
