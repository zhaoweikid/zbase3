# vim: set ts=4 et sw=4 sts=4 fileencoding=utf-8 :

import os
import sys
from webconfig_debug import *

# 服务地址
HOST = '0.0.0.0'

# 服务端口
PORT = 6200

# 协议
PROTO = 'http'

# 工作模式:  simple/gevent
# simple使用多线程模式启动server
# gevent会使用gevent方式启动server
WORK_MODE = 'gevent'

# 服务名称，也是服务目录名
MYNAME = os.path.basename(HOME) 
os.environ['MYNAME'] = MYNAME

# 服务名称上报时间间隔，单位秒
NAME_REPORT_TIME = 9

# 命名服务的地址
NAMECENTER = os.environ.get('NAMECENTER')

# IDC标识
IDC  = os.environ.get('IDC')


# 调试模式: True/False
# 生产环境必须为False
DEBUG = False

# 日志文件配置
if DEBUG:
    LOGFILE = 'stdout'
else:
    LOGFILE = os.path.join(HOME, 'log/project.log')


# 数据库配置
DATABASE = {
    'test': {
        'engine':'pymysql',
        'db': 'test',
        'host': '127.0.0.1',
        'port': 3306,
        'user': 'root',
        'passwd': '123456',
        'charset': 'utf8',
        'conn': 3,
    },
}

