# coding: utf-8
# many more advanced things
from zbase3.web.core import Handler, HandlerFinish
from zbase3.web import session, middleware
from zbase3.web.httpcore import Response, NotFound
from zbase3.server.defines import *
import json
import logging

log = logging.getLogger()

# 错误码对应的描述
errmsg = {}


class APIHandler (Handler):
    # 不需要检查session的url在url_public中设置
    # url_public = [url1,url2,...]
    url_public = []

    def initial_session(self):
        pass

    def initial(self):
        self.set_headers({'Content-Type': 'application/json; charset=UTF-8'})
        return

    def finish(self):
        pass

    def GET(self, name):
        '''自动根据url的正则分组的名字匹配函数名。返回是一个值即为成功，两个值就是失败'''
        func = getattr(self, name, None)
        # 对外接口必须有使用validator
        if func and func.__doc__ == 'validator':
            ret = func()
            if isinstance(ret, tuple) and len(ret) == 2:
                self.fail(ret[0], ret[1])
            elif ret is not None:
                self.succ(ret)
        else:
            self.resp = NotFound('Not Found: ' + self.req.path)  

    POST = GET
    
    def succ(self, data=None, write=True):
        '''成功返回的结构，如果结果不一样，需要重新定义'''
        obj = {'ret':self._errcode(OK), 'err':''}
        if data:
            obj['data'] = data
        else:
            obj['data'] = {}
        s = json.dumps(obj)
        #log.info('succ: %s', s)
        if write:
            self.write(s)
        return s

    def fail(self, ret=ERR, err='', data=None, write=True):
        '''成功返回的结构，如果结果不一样，需要重新定义'''
        cd = self._errcode(ret)
        cdstr = str(cd)
        obj = {'ret':cd, 'err':err, 'data':{}}
        if not err:
            obj['err'] = self._errmsg(ret)
        elif cdstr not in err:
            obj['err'] = err + '({})'.format(cdstr)
        if data:
            obj['data'] = data
        s = json.dumps(obj)
        #log.info('fail: %s', s)
        if write:
            self.write(s)
        return s

    def _errcode(self, code):
        return code

    def _errmsg(self, code):
        cd = self._errcode(code)
        return errmsg.get(code, '操作失败，请联系客服({})'.format(cd))


class SessionMiddleware:
    def before(self, viewobj, *args, **kwargs):
        if not viewobj.config.SESSION or not viewobj.config.SESSION.get('enable', True):
            log.info('no session config or not enable, not check session')
            return
        if hasattr(viewobj, 'check_session') and not viewobj.check_session:
            log.info('view not need check session')
            return
        sid = viewobj.get_cookie(viewobj.config.SESSION['cookie_name'])
        log.debug('sid: %s', sid)
        viewobj.ses = session.create(viewobj.config.SESSION, sid)

        # 不需要检查session的url
        #log.debug('path:%s, url_public:%s', viewobj.req.path, viewobj.url_public)
        if viewobj.url_public and viewobj.req.path in viewobj.url_public:
            return

        # 检查session
        # 1. 没有cookie
        if not sid:
            log.info('session not found sid')
            raise HandlerFinish(403, 'session id error')
        # 2. 没有session数据
        if not viewobj.ses.data:
            log.info('session %s no data', sid)
            raise HandlerFinish(403, 'session data error')

    def after(self, viewobj, *args, **kwargs):
         # 请求时不带sid，但是请求处理完成后有session data，写入sesion
        if viewobj.ses and viewobj.ses.auto_save():
            viewobj.set_cookie('sid', viewobj.ses.sid)


middleware.SessionMiddleware = SessionMiddleware


