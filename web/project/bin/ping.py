# coding: utf-8
import os, sys
from zbase3.web import core
from zbase3.base.dbpool import get_connection_exception
import logging
import datetime, time
import json

import config

log = logging.getLogger()


class Ping (core.Handler):
    def GET(self):
        indata = self.req.input()

        now = datetime.datetime.now()
        retdata = {'time':str(now)[:19], 'dbtime':'', 'starttime':config.starttime,
                'id':indata.get('id','0'), 'pid':os.getpid()}
        if hasattr(config, 'DATABASE'):
            keys = list(config.DATABASE.keys())
            
            with get_connection_exception(keys[0]) as conn:
                ret = conn.get("select now()", isdict=False)
                retdata['dbtime'] = str(ret[0])[:19]

        if hasattr(config, 'PORT'):
            retdata['port'] = config.PORT

        retobj = {'respcd':'0000', 'resperr':'', 'data':retdata}
        self.write(json.dumps(retobj))
            




