# vim: set ts=4 et sw=4 sts=4 fileencoding=utf-8 :

import os
import sys
HOME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# URLS配置
URLS = None

# 静态路径配置
# 此转换主要用户url路径和文件本地路径有差异的情况
# 格式: {URL_PART: LOCAL_PATH}
# 文件路径为：DOCUMENT_ROOT + URL_PATH.replace(URL_PART, LOCAL_PATH)
# 如：http://127.0.0.1/s/test.html，通过以下默认的STATICS配置转换后,
#     本地文件路径为：DOCUMENT_ROOT + /bin/static/test.html
STATICS = {'/s/':'/bin/static/'}

# 模板配置
TEMPLATE = {
    'cache': False,
    'path': 'templates',
    'tmp': os.path.join(HOME, '../tmp'),
}

# 默认在此目录下的所有都是APP
# 每个APP有自己独立的url和handler
APP_PATH = os.path.join(HOME, 'bin/apps')

# 中间件
MIDDLEWARE = (
    # middleware
)

# WEB根路径
DOCUMENT_ROOT = HOME

# 页面编码
CHARSET = 'UTF-8'

# session配置
# 1. session存储在文件中，expire为过期时间（秒），path为存储路径
# {'store':'SessionFile',  'expire':30, 'path':'/tmp'}
# 2. session存储在redis中，expire为过期时间（秒），addr为redis的地址
# {'store':'SessionRedis', 'expire':30, 'server':[{'addr':(ip,port), 'timeout':1000}]}

#SESSION = {'store':'SessionFile', 'expire':30, 'path':'/tmp'}

SESSION = {
    'store':'SessionRedis', 
    'expire':3600, 
    #'server':[{'addr':('127.0.0.1',6379), 'timeout':1000}],
    'cookie_name':'sid',
    'config':{
        'redis_conf': {
            'host':'127.0.0.1', 
            'port':6379,
            'db':0, 
        },
        'user_key':'userid',
    }

}

