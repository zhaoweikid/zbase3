# vim: set ts=4 et sw=4 sts=4 fileencoding=utf-8 :

import os
import sys
HOME = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(os.path.dirname(HOME), 'conf'))

from zbase3.base import logger,loader
if __name__ == '__main__':
    loader.loadconf_argv(HOME)
else:
    loader.loadconf(HOME)

import config
import urls

# 导入服务日志
if config.LOGFILE:
    log = logger.install(config.LOGFILE)
else:
    log = logger.install('stdout')

from zbase3.base import dbpool
from zbase3.web import core
from zbase3.web import runner

import datetime
config.starttime = str(datetime.datetime.now())[:19]
# 导入数据库
#dbpool.install(config.DATABASE)

# 导入WEB URLS
config.URLS = urls

app = core.WebApplication(config)

if __name__ == '__main__':
    # 导入自定义服务端口
    if len(sys.argv) > 2:
        config.PORT = int(sys.argv[2])
    runner.run_simple(app, host=config.HOST, port=config.PORT)

