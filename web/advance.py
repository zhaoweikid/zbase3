# coding: utf-8
# many more advanced things
from zbase3.web.core import Handler, HandlerFinish
from zbase3.web import session
from zbase3.web.httpcore import Response
import json
import logging

log = logging.getLogger()

OK  = 0
ERR = -1

class APIHandler (Handler):
    # 只要配置了sessino_conf, 所有的url都会检查session，不需要检查的再session_nocheck中设置
    session_conf = None
    # 不检查session的url, {url:method} or [url1,url2,...]
    session_nocheck = {}

    def initial(self):
        self.set_headers({'Content-Type': 'application/json; charset=UTF-8'})
        name = self.req.path.split('/')[-1]

        sid = self.get_cookie('sid')
        log.debug('sid: %s', sid)
        self.ses = None
        if self.session_conf:
            self.ses = session.create(self.session_conf, sid)

        # name: _xxxx means private method, only called in LAN , 
        #       xxxx_ means not need check session
        if name.endswith('_'):
            log.debug('no need check session 1')
            return

        if isinstance(self.session_nocheck, dict):
            noses_method = self.session_nocheck.get(self.req.path)
            if noses_method and (noses_method == '*' or noses_method == self.req.method):
                log.debug('no need check session 2')
                return
        elif isinstance(self.session_nocheck, (list,tuple)):
            if self.req.path in self.session_nocheck:
                log.debug('no need check session 3')
                return

        if name.startswith('_'): # private
            c = self.req.clientip()
            log.debug('clientip:%s', c)
            if not c.startswith(('192.168.', '10.', '127.')):
                self.resp = Response(status=403)
                raise HandlerFinish

        # check session
        if not sid:
            log.info('not found sid')
            self.resp = Response('403 sesson error 1', status=403)
            raise HandlerFinish

        if not self.ses:
            log.info('session %s no obj', sid)
            self.resp = Response('403 session error 2', status=403)
            raise HandlerFinish

        if not self.ses.data:
            log.info('session %s no data', sid)
            self.resp = Response('403 session error 3', status=403)
            raise HandlerFinish

        
    def finish(self):
        # 请求时不带sid，但是请求处理完成后有session data，写入sesion
        #if isinstance(self.ses, dict):
        #    if self.ses:
        #        ses = self.ses
        #        self.create_session()
        #        self.ses.update(ses)
        #    else:
        #        return
        #if self.ses:
        #    if self.ses.data:
        #        self.ses.save()
        #        self.set_cookie('sid', self.ses.sid)
        #    else:
        #        self.ses.remove()

        if self.ses and self.ses.auto_save():
            self.set_cookie('sid', self.ses.sid)


    def create_session(self):
        self.ses = session.create(self.session_conf)
        return self.ses


    def GET(self, name):
        '''自动根据url的正则分组的名字匹配函数名。返回是一个值即为成功，两个值就是失败'''
        func = getattr(self, name, None)
        if func:
            ret = func()
            if isinstance(ret, tuple) and len(ret) == 2:
                self.fail(ret[0], ret[1])
            elif ret:
                self.succ(ret)
        else:
            self.resp = NotFound('Not Found: ' + self.req.url)  

    POST = GET
    
    def succ(self, data=None):
        '''成功返回的结构，如果结果不一样，需要重新定义'''
        obj = {'ret':OK, 'err':''}
        if data:
            obj['data'] = data
        s = json.dumps(obj)
        #log.info('succ: %s', s)
        self.write(s)
        return s

    def fail(self, ret=ERR, err='internal error', debug=''):
        '''成功返回的结构，如果结果不一样，需要重新定义'''
        obj = {'ret':ret, 'err':err}
        if debug:
            obj['debug'] = debug
        s = json.dumps(obj)
        #log.info('fail: %s', s)
        self.write(s)
        return s



