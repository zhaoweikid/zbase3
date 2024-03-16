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
                if ret[0] != OK:
                    self.fail(ret[0], ret[1])
                else:
                    self.succ(ret[1])
            elif ret is not None:
                self.succ(ret)
        else:
            self.resp = NotFound('Not Found: ' + self.req.path)  

    POST = GET
    
    def succ(self, data=None, write=True):
        '''成功返回的结构，如果结果不一样，需要重新定义'''
        obj = {'code':self._errcode(OK)}
        if data:
            obj['data'] = data
        else:
            obj['data'] = {}
        s = json.dumps(obj)
        #log.info('succ: %s', s)
        if write:
            self.write(s)
        return s

    def fail(self, code=ERR, err='', data=None, write=True):
        '''成功返回的结构，如果结果不一样，需要重新定义'''
        cd = self._errcode(code)
        cdstr = str(cd)
        obj = {'code':cd, 'err':err, 'data':{}}
        if not err:
            obj['err'] = self._errmsg(code)
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
        if not viewobj.conf.SESSION or not viewobj.conf.SESSION.get('enable', True):
            log.info('no session config or not enable, not check session')
            return
        # handler如果有设置check_session = False，此handler不检查session
        if hasattr(viewobj, 'check_session') and not viewobj.check_session:
            log.info('view not need check session')
            return
        
        if not viewobj.ses:
            viewobj.create_session()

        path = viewobj.req.path
        # 不需要检查session的url
        # url_private有设置，那么不在里面的url都是public
        if hasattr(viewobj, 'url_private') and path not in viewobj.url_private:
            return
        # url_public有设置，那么不在里面的url都是private
        if hasattr(viewobj, 'url_public') and path in viewobj.url_public:
            return

        # 检查session
        # 1. 没有cookie
        #if not self.get_cookie_sid():
        #    log.info('session not found sid')
        #    raise HandlerFinish(403, 'session id error')
        # 2. 没有session数据
        if not viewobj.ses.data:
            log.info('session %s no data', viewobj.ses.sid)
            raise HandlerFinish(403, 'session data error')

    def after(self, viewobj, *args, **kwargs):
         # 请求时不带sid，但是请求处理完成后有session data，写入sesion
        if viewobj.ses and viewobj.ses.auto_save():
            viewobj.set_cookie('sid', viewobj.ses.sid)


middleware.SessionMiddleware = SessionMiddleware

class SignMiddleware:

    def get_app(self, viewobj, appid):
        conf = viewobj.conf.MIDDLEWARE_CONF
        return conf['apps'].get(appid)

        #with get_connection('usercenter') as conn:
        #    app = conn.select_one('apps', where={'appid':appid})
        #    return app

    def before(self, viewobj, *args, **kwargs):
        '''X-APPID, X-SIGN, X-METHOD'''

        path = viewobj.req.path

        # 不需要检查sign的url
        if hasattr(viewobj, 'url_private') and path not in viewobj.url_private:
            return
        if hasattr(viewobj, 'url_public') and path in viewobj.url_public:
            return
        if hasattr(viewobj, 'url_nosign') and path not in viewobj.url_nosign:
            return
 
        headers = viewobj.req.headers()
        log.debug('headers:%s', headers)
        appid = headers.get(viewobj.conf.OPENSDK_SIGN_VAR['appid'], '')
        sign = headers.get(viewobj.conf.OPENSDK_SIGN_VAR['sign'], '').lower()
        method = headers.get(viewobj.conf.OPENSDK_SIGN_VAR['method'], 'md5')

        log.debug('appid:%s sign:%s', appid, sign)

        app = self.get_app(viewobj, appid)
        if not app:
            viewobj.fail(ERR_SIGN, '签名错误, appid错误')
            raise HandlerFinish(500, '签名错误, appid错误')

        secret = app['secret']
        if isinstance(secret, str):
            secret = secret.encode()
        s = viewobj.req.postdata() + secret
        x = hashlib.md5()
        x.update(s)
        sign_result = x.hexdigest()
        log.debug('sign result:%s', sign_result)
        if sign != sign_result:
            log.debug('sign error input:%s compute:%s', sign, sign_result)
            viewobj.fail(ERR_SIGN, '签名错误')
            raise HandlerFinish()

        viewobj.ses['userid'] = app['userid']

        return

    def after(self, viewobj, *args, **kwargs):
        return 

middleware.SignMiddleware = SignMiddleware

