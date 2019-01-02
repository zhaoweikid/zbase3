# vim: set ts=4 et sw=4 sts=4 fileencoding=utf-8 :

import os
import sys

HOME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 服务地址
HOST = '0.0.0.0'

# 服务端口
PORT = 7200

# 服务开启进程数
PROCS = 2

# 单进程最大并发
MAX_CONN = 1000

# 调试模式: True/False
# 生产环境必须为False
DEBUG = False

# 日志文件配置
LOGFILE = 'stdout'
#LOGFILE = {'root': {'filename':{'DEBUG':os.path.join(HOME, "log/project.log"),'ERROR':os.path.join(HOME, 'log/project.error.log')}}} 

# 数据库配置
DATABASE = {
    'test': {
        'engine':'pymysql',
        'db': 'test',
        'host': '127.0.0.1',
        'port': 3306,
        'user': 'zhaowei',
        'passwd': '123456',
        'charset': 'utf8',
        'conn': 10,
    },
}

