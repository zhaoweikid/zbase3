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

def _json_default_trans(obj):
	'''json对处理不了的格式的处理方法'''
	if isinstance(obj, datetime.datetime):
		return obj.strftime('%Y-%m-%d %H:%M:%S')
	if isinstance(obj, datetime.date):
		return obj.strftime('%Y-%m-%d')
	raise TypeError('%r is not JSON serializable' % obj)


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
            self.ses = None

            if self.session_conf:
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
        obj = {'ret':OK, 'err':''}
        if data:
            obj['data'] = data
        s = json.dumps(obj, separators=(',', ':'), default=_json_default_trans)
        log.info('succ: %s', s)
        self.write(s)

    def fail(self, ret=ERR, err='internal error', debug=''):
        obj = {'ret':ret, 'err':err}
        if debug:
            obj['debug'] = debug
        s = json.dumps(obj, separators=(',', ':'), default=_json_default_trans)
        log.info('fail: %s', s)
        self.write(s)



