import os
import sys
from webconfig import *

HOME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# 服务地址
HOST = '0.0.0.0'

# 服务端口
PORT = 8000

# 服务名称上报时间间隔，单位秒
NAME_REPORT_TIME = 10

# 命名服务的地址
NAMECENTER = os.environ.get('NAMECENTER')

# IDC标识
IDC = os.environ.get('IDC')

# 调试模式: True/False
# 生产环境必须为False
DEBUG = True

# 日志文件配置
if DEBUG:
    LOGFILE = 'stdout'
else:
    LOGFILE = os.path.join(HOME, 'log/project.log')

# 数据库配置
DATABASES = {
}
