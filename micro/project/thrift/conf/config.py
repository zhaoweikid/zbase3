# vim: set ts=4 et sw=4 sts=4 fileencoding=utf-8 :
import os, sys
import datetime

# 服务主目录，即/home/xx/project
HOME = os.path.dirname(os.path.dirname(os.path.abspath("__file__")))
if os.path.basename(HOME).isdigit():
    HOME = os.path.dirname(HOME)

# 服务名称，也是服务目录名
NAME = os.path.basename(HOME) 

# 命名服务的地址
QFNAME = os.environ.get('QFNAME')

# IDC标识
QFIDC  = os.environ.get('QFIDC')

# 服务地址
HOST = '0.0.0.0'

# 服务端口
PORT = 7200

# 协议
PROTO = 'thrift'

# 服务开启工作进程数
MAX_PROC = 3

# 单进程最大并发，多线程模式下为线程数
MAX_CONN = 500

# 单进程最大处理请求数，达到处理请求数，工作进程会重启。小于等于0 表示无限制
MAX_REQ = 10000

# 调试模式: True/False
# 生产环境必须为False
DEBUG = False

# 日志文件配置
if DEBUG:
    LOGFILE = 'stdout'
else:
    LOGFILE = {'root': {'filename':{
        'DEBUG':os.path.join(HOME, "log/%s.log" % NAME),
        'ERROR':os.path.join(HOME, 'log/%s.error.log' % NAME)
    }}} 

START_TIME = str(datetime.datetime.now())[:19]

from database import *
from app import *


