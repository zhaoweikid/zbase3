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

# APP就是一个子目录
APPS = (

)

# 中间件
MIDDLEWARE = (
    # middleware
)

# WEB根路径
DOCUMENT_ROOT = HOME

# 页面编码
CHARSET = 'UTF-8'

# session配置
# store:DiskSessionStore, expire:x, path:/tmp
# store:RedisSessionStore, expire:x, 'addr':[(ip,port)]
# store:MemcachedSessionStore, expire:x, addr:[(ip,port)]
SESSION = {'store':'DiskSessionStore', 'expire':30, 'path':'/tmp'}


