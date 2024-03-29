# coding: utf-8
from gevent import monkey
monkey.patch_all()
import os, sys
HOME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(HOME, 'conf'))

from zbase3.base import loader
if __name__ == '__main__':
    loader.loadconf_argv(HOME)
else:
    loader.loadconf(HOME)

import config
#if config.WORK_MODE == 'gevent':
#    from gevent import monkey
#    monkey.patch_all()
from zbase3.base import logger
log = logger.install(config.LOGFILE)
from zbase3.micro import rpcore
import pprint
import multiprocessing
import logging
import main

handler = None
for k,v in main.__dict__.items():
    if k == 'MainHandler':
        handler = v
        log.info('Handler: %s', k)
        break
if not handler:
    for k,v in main.__dict__.items():
        if k.endswith('Handler'):
            if issubclass(v, rpcore.Handler):
                handler = v
                log.info('Handler: %s', k)
                break
if not handler:
    print('Not found handler in main.py !!! class must named XXXXHandler !!!')
    log.error('Not found handler in main.py !!! class must named XXXXHandler !!!')
    sys.exit(-1)

cores = multiprocessing.cpu_count()
log.info('cpu cores: %d', cores)
if config.MAX_PROC > cores*2:
    log.warning('config.MAX_PROC(%d) > cpu cores(%d*2), please check', config.MAX_PROC, cores)

if len(sys.argv) > 2:
    config.PORT = int(sys.argv[2])

if config.WORK_MODE == 'gevent':
    server = rpcore.GeventServer(config, handler)
else:
    server = rpcore.ThreadServer(config, handler)
server.forever()

