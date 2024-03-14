# vim: set ts=4 et sw=4 sts=4 fileencoding=utf-8 :

import os
import sys
import logging
import time
import datetime
import json
from zbase3.web import core
from zbase3.web import template
from zbase3.web.advance import APIHandler
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


@core.route('/test')
class Test (core.Handler):
    def GET(self):
        self.write('test ok')


class MyAPI1(APIHandler):
    def GET(self):
        now = datetime.datetime.now()
        return self.succ(now)



class MyAPI2(APIHandler):
    '''
    需要先/api2/login登录后才可以访问其他接口
    '''
    session_conf = config.SESSION
    session_nocheck = [
        '/api2/login',
    ]

    def login(self):
        self.ses['userid'] = '1000'
        return {'userid':'1000'}

    def logout(self):
        self.ses.clear()
        return {}

    def now(self):
        now = datetime.datetime.now()
        self.ses['t'] = now
        return str(now)[:19]

    def today(self):
        now = datetime.datetime.today()
        return {'day':str(now.date()), 'time':int(time.time())}

    def myerror(self):
        return '1201', 'error: %d' % int(time.time())


    def succ(self, data=None):
        '''成功返回的结构，如果结果不一样，需要重新定义'''
        obj = {'respcd':'0000', 'resperr':''}
        if data:
            obj['data'] = data
        s = json.dumps(obj)
        log.info('succ: %s', s)
        self.write(s)

    def fail(self, ret='1000', err='internal error', debug=''):
        '''成功返回的结构，如果结果不一样，需要重新定义'''
        obj = {'respcd':ret, 'resperr':err}
        if debug:
            obj['debug'] = debug
        s = json.dumps(obj)
        log.info('fail: %s', s)
        self.write(s)








