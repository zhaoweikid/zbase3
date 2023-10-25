# vim: set ts=4 et sw=4 sts=4 fileencoding=utf-8 :

import os
import sys
HOME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# URLS配置
URLS = None

# 静态路径配置
# 所有静态文件访问必须通过这里设置。key为路径的前部分，value为真实本地路径
STATICS = {'/s/': os.path.join(HOME, 'static/')}

# 模板配置, 没有配置将不能使用mako服务器端模板引擎
TEMPLATE = {
    'cache': True,
    'path': 'templates',
    'tmp': os.path.join(HOME, 'tmp'),
}

# 默认在此目录下的所有都是APP
# 每个APP有自己独立的url和handler。在app的__init__.py里设置
# APP的静态文件默认路径为 /app/app_name/static/
APP_PATH = os.path.join(HOME, 'bin/apps')

# 中间件
MIDDLEWARE = (
    # middleware
)

# 页面编码
CHARSET = 'UTF-8'

# session配置
# 1. session存储在文件中，expire为过期时间（秒），path为存储路径
# {'store':'SessionFile',  'expire':30, 'config':{'path':'/tmp'}}
# 2. session存储在redis中，expire为过期时间（秒），addr为redis的地址
# {'store':'SessionRedis', 'expire':30, 'server':{'host':'127.0.0.1', 'port':6379, 'db':0}}
SESSION = {
    'store':'SessionRedis', 
    'expire':3600, 
    #'server':[{'addr':('127.0.0.1',6379), 'timeout':1000}],
    'cookie_name': 'sid',
    'config':{
        'redis_conf': {
            'host':'127.0.0.1', 
            'port':6379,
            'db':0, 
        },
        'user_key':'userid',
    }
}




