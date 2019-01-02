# coding: utf-8
import os, sys
from zbase3.micro import core
from zbase3.base.dbpool import get_connection_exception
import json
import datetime, time
import config
import microtest
from microtest import Test


# 所有服务必须有ping接口
class PingHandler (core.Handler):
    # thrift生成的接口对象
    define = Test

    def ping(self):
        now = datetime.datetime.now()
        retdata = {'time':str(now)[:19], 'dbtime':'', 'starttime':config.starttime,
                'pid':os.getpid()}
        if hasattr(config, 'DATABASE'):
            keys = list(config.DATABASE.keys())
            
            with get_connection_exception(keys[0]) as conn:
                ret = conn.get("select now()", isdict=False)
                retdata['dbtime'] = str(ret[0])[:19]

        if hasattr(config, 'PORT'):
            retdata['port'] = config.PORT

        retobj = {'respcd':'0000', 'resperr':'', 'data':retdata}

        return json.dumps(retobj)


