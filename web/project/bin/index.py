# vim: set ts=4 et sw=4 sts=4 fileencoding=utf-8 :

import os
import sys
import logging
import time
import json

from zbase3.web import core
from zbase3.web import template
from zbase3.base.dbpool import get_connection_exception

import config


log = logging.getLogger()

class Index(core.Handler):
    def GET(self):
        log.debug('headers %s', self.req.headers())
        log.debug('get cookie %s' % self.req.cookie)

        with get_connection_exception('test') as db:
            data = db.query('show processlist')

        t = str(time.time())
        log.debug('set cookie time: %s', t)

        self.resp.set_cookie('time', t, expires = int(time.time()) + 20 )
        self.write(template.render('index.html', data=data))


    def POST(self):
        data = self.req.input()
        self.write(str(data))


