# vim: set ts=4 et sw=4 sts=4 fileencoding=utf-8 :
import os
import sys
HOME = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(os.path.dirname(HOME), 'conf'))

from zbase3.base import loader
if __name__ == '__main__':
    loader.loadconf_argv(HOME)
else:
    loader.loadconf(HOME)

import config

if config.WORK_MODE == 'gevent':
    from gevent import monkey; monkey.patch_all()

from zbase3.base import logger
# 导入服务日志
if config.LOGFILE:
    log = logger.install(config.LOGFILE)
else:
    log = logger.install('stdout')


from zbase3.base import dbpool
from zbase3.web import core
from zbase3.web import runner
from zbase3.server import nameclient

import datetime
config.starttime = str(datetime.datetime.now())[:19]

# 导入WEB URLS
import urls
config.URLS = urls

app = core.WebApplication(config)

if __name__ == '__main__':
    # 导入自定义服务端口
    if len(sys.argv) > 2:
        config.PORT = int(sys.argv[2])

    log.info('WORK_MODE: %s', config.WORK_MODE)
    if config.WORK_MODE == 'simple':
        if config.NAMECENTER and config.MYNAME:
            t = threading.Thread(target=nameclient.server_report, 
                    args=(config.MYNAME, (config.HOST, config.PORT), config.PROTO, config.NAME_REPORT_TIME))
            t.daemon = True
            t.start()
        else:
            log.warn('no NAMECENTER and MYNAME, not report server info to namecenter')

        runner.run_simple(app, host=config.HOST, port=config.PORT)
    elif config.WORK_MODE == 'gevent':
        import gevent

        if config.NAMECENTER and config.MYNAME:
            gevent.spawn(nameclient.server_report(config.MYNAME, (config.HOST, config.PORT), config.PROTO, config.NAME_REPORT_TIME))
        else:
            log.warn('no NAMECENTER and MYNAME, not report server info to namecenter')

        runner.run_gevent(app, host=config.HOST, port=config.PORT)
    else:
        log.error('config.WORK_MODE must use simple/gevent !!!')

