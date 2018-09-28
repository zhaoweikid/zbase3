# coding: utf-8
# many more advanced things
from zbase3.web.core import Handler, HandlerFinish
from zbase3.web.session import SessionRedis
from zbase3.web.httpcore import Response
import json
import logging

log = logging.getLogger()

OK  = 0
ERR = -1

class APIHandler (Handler):
    session_conf = None
    def initial(self):
        self.set_headers({'Content-Type': 'application/json; charset=UTF-8'})
        name = self.req.path.split('/')[-1]
        # name: _xxxx means private method, only called in LAN , 
        #       xxxx_ means not need check session
        if name.endswith('_'):
            return

        if name.startswith('_'): # private
            c = self.req.clientip()
            log.debug('clientip:%s', c)
            if not c.startswith(('192.168.', '10.', '127.')):
                self.resp = Response('Access Deny', 403)
                raise HandlerFinish
        else:
            # check session
            sid = self.get_cookie('sid')
            if not sid:
                self.resp = Response('Session Error', 403)
                raise HandlerFinish

            self.ses = SessionRedis(server=self.session_conf, sid=sid)
            if self.ses.get('uid'):
                self.resp = Response('Session Error', 403)
                raise HandlerFinish
        

    def finish(self):
        if self.ses and self.ses.sid:
            self.ses.save()
            self.set_cookie('sid', self.ses.sid)


    def succ(self, data=None):
        obj = {'ret':OK}
        if data:
            obj['data'] = data
        s = json.dumps(obj, separators=(',', ':'))
        log.info('succ: %s', s)
        self.write(s)

    def fail(self, errstr=u'internal error'):
        obj = {'ret':ERR, 'err':errstr}
        s = json.dumps(obj, separators=(',', ':'))
        log.info('fail: %s', s)
        self.write(s)



