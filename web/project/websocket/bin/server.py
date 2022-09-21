import os
import sys
from gevent import monkey
monkey.patch_all()

HOME = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(os.path.dirname(HOME), 'conf'))

from zbase3.base import loader
if __name__ == '__main__':
    loader.loadconf_argv(HOME)
else:
    loader.loadconf(HOME)

import config
from zbase3.base import logger
if config.LOGFILE:
    log = logger.install(config.LOGFILE)
else:
    log = logger.install('stdout')

from zbase3.base import dbpool
from zbase3.web.websocketcore import WebSocketHTTPApplication, WebSocketServer

import urls

dbpool.install(config.DATABASES)

config.URLS = urls

app = WebSocketHTTPApplication(config)

server = WebSocketServer((config.HOST, config.PORT), application=app)
server.serve_forever()
