# vim: set ts=4 et sw=4 sts=4 fileencoding=utf-8 :

import os
import sys
import logging
import time
from zbase3.web import core
from zbase3.web import template
from zbase3.base.dbpool import with_database

import config

log = logging.getLogger()

class Index(core.Handler):
    @with_database('test')
    def GET(self):
        log.debug('headers %s', self.req.headers())
        log.debug('get cookie %s' % self.req.cookie)

        data = self.db.query('show processlist')

        t = str(time.time())
        log.debug('set cookie time: %s', t)

        self.resp.set_cookie('time', t, expires = int(time.time()) + 20 )
        self.write(template.render('index.html', data=data))

    def POST(self):
        data = self.req.input()
        self.write(str(data))


