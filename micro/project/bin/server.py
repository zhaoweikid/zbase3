# coding: utf-8
import os, sys
HOME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(HOME, 'conf'))
QFNAME = os.environ.get('QFNAME')
QFIDC = os.environ.get('QFIDC','')
import config
config.QFNAME = QFNAME
config.QFIDC = QFIDC

import datetime, time
config.starttime = str(datetime.datetime.now())[:19]

from zbase3.base import logger
logger.install(config.LOGFILE)

from zbase3.server import thriftserver
#from zbase3.thriftclient import *
from zbase3.micro import core
import main

handler = None
for k,v in main.__dict__.items():
    if k.endswith('Handler'):
        if issubclass(v, core.Handler):
            handler = v
            break
if not handler:
    print('Not found thrift handler in main.py !!! class must named XXXXHandler !!!')
    sys.exit(-1)

server = core.MicroThriftServer(handler.define, handler, config)
server.forever()

