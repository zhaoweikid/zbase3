# coding: utf-8
from gevent import monkey; monkey.patch_all()
import os, sys
HOME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(HOME, 'conf'))
import config

from zbase3.base import logger
logger.install(config.LOGFILE)

from zbase3.server import thriftserver
from zbase3.micro import thriftcore
import main

handler = None
for k,v in main.__dict__.items():
    if k.endswith('Handler'):
        if issubclass(v, thriftcore.Handler):
            handler = v
            break
if not handler:
    print('Not found thrift handler in main.py !!! class must named XXXXHandler !!!')
    sys.exit(-1)

server = thriftcore.MicroThriftServer(handler.define, handler, config)
server.forever()

