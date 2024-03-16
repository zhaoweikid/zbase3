# coding: utf-8
import os, sys, uuid, threading
import re, time, types, mimetypes
import urllib, urllib.request
from zbase3.web import template, reloader, session, middleware
from zbase3.base import dbpool, logger
from zbase3.base.logger import REQUEST_ID_MAP
from zbase3.web.httpcore import Request, Response, NotFound
import traceback, logging
from zbase3.web.httpcore import MethodNotAllowed

log = logging.getLogger()

class HandlerFinish(Exception):
    def __init__(self, code=500, value=''):
        self.code = code
        self.value = value

    def __str__(self):
        return 'HandlerFinish: %d %s' % (self.code, self.value)

class Handler(object):
    def __init__(self, app, req, handler=None):
        self.webapp = app
        self.conf = app.settings
        self.req = req
        req.allowed_methods = []

        if not handler:
            reqid = self.req.get_header('X-Req-Id', '')
            log.debug('X-Req-Id: %s', reqid)
            logger.set_req_id(reqid)

            self.resp = Response()
            self.create_session()
        else:
            self.resp = handler.resp
            self.ses = handler.ses
            
        self.write = self.resp.write

    def create_session(self):
        '''初始化session'''
        sid = self.get_cookie_sid()
        self.ses = session.create(self.conf.SESSION, sid)

    def initial(self):
        '''请求处理前调用，自定义初始化内容'''
        pass

    def finish(self):
        '''请求结束调用'''
        if self.ses:
            self.ses.auto_save()
        self.resp.headers['X-Req-Id'] = logger.get_req_id()

    def get_cookie(self, cookie_name):
        return self.req.cookie.get(cookie_name, '')

    def get_cookie_sid(self):
        return self.get_cookie(self.conf.SESSION.get('cookie_name', 'sid'))

    def set_cookie(self, *args, **kwargs):
        self.resp.set_cookie(*args, **kwargs)

    def set_headers(self, headers=None):
        if headers:
            for k,v in headers.items():
                self.resp.headers[k] = v

    def redirect(self, *args, **kwargs):
        '''http重定向'''
        return self.resp.redirect(*args, **kwargs)

    def GET(self):
        self.resp = MethodNotAllowed()

    POST = HEAD = DELETE = PUT = GET

    def OPTIONS(self, *args, **kwargs):
        '''
            OPTIONS请求方法的主要用途有两个：
            1、获取服务器支持的HTTP请求方法；也是黑客经常使用的方法。
            2、用来检查服务器的性能。例如：
                AJAX进行跨域请求时的预检，需要向另外一个域名的资源发送一个HTTP OPTIONS请求头，用以判断实际发送的请求是否安全。
        '''
        origin = self.req.environ.get('HTTP_ORIGIN','')
        self.resp.headers['Access-Control-Allow-Origin'] = origin
        self.resp.headers['Access-Control-Allow-Credentials'] = 'true'
        self.resp.headers['Access-Control-Allow-Methods'] = ','.join(self.allowed_methods)
        # request headers
        req_headers = self.req.environ.get('HTTP_ACCESS_CONTROL_REQUEST_HEADERS', '')
        self.resp.headers['Access-Control-Allow-Headers'] = req_headers
        self.resp.headers['Access-Control-Max-Age'] = '86400'  # ,允许这个预请求的参数缓存的秒数,在此期间,不用发出另一条预检请求
        self.resp.status=200
        return

    def render(self, *args, **kwargs):
        '''服务器端模板渲染'''
        if template.render:
            kwargs.update({
                '_handler':self
            })
            self.write(template.render(*args, **kwargs))

app = None

class WebApplication(object):
    def __init__(self, settings):
        '''
        settings:
            #DOCUMENT_ROOT: web root path
            DEBUG: True/False
            CHARSET: utf-8
            LOGGER: log file
            HOME: project home path
            TEMPLATE: {'path':xx,'tmp':xx,'cache':True}
            DATABASE: database config
            APPS: app
            URLS: (('/', index.Index), )
            STATICS
            SESSION
            MIDDLEWARE
        '''
        global app
        app = self

        # 切换到字典static,兼容列表型
        if hasattr(settings, 'STATICS'):
            if isinstance(settings.STATICS, (list,tuple)):
                settings.STATICS = dict(zip(settings.STATICS,settings.STATICS))
        else:
            settings.STATICS = {}

        self.allowed_methods = set(('GET', 'HEAD', 'POST', 'DELETE', 'PUT', 'OPTIONS'))
        self.charset = 'utf-8'
        self._all_static_paths = {}
        self.settings = settings
        self.install()
        
        self._all_static_paths.update(self.settings.STATICS)
        for k,v in self._all_static_paths.items():
            log.debug('static: {0} => {1}'.format(k,v))

        self.debug = getattr(settings, 'DEBUG', False)
        if not self.debug and getattr(settings, 'ENV', '') != 'product':
            self.debug = True
        self.charset = getattr(settings, 'CHARSET', 'utf-8')

        self.reloader = None
        if self.debug:
            self.reloader = reloader.Reloader()


    def add_urls(self, urls, appname=''):
        for item in urls:
            kwargs = None
            if len(item) == 3:
                kwargs = item[2]
            self.add_url(item[0], item[1], kwargs, appname)
 

    def add_url(self, path, handlecls, kwargs=None, appname=''):
        if type(handlecls) == str:
            mod, cls = handlecls.rsplit('.', 1)
            mod = __import__(mod, None, None, [''])
            obj = getattr(mod, cls)
        else:
            obj = handlecls

        urlpath = path
        if appname:
            urlpath = '^/' + appname + urlpath.lstrip('^').rstrip('$') + '$'
        else:
            urlpath = '^' + urlpath.lstrip('^').rstrip('$') + '$'

        log.debug('url: %s %s', urlpath, handlecls)
        if not kwargs:
            kwargs = {}
        self.urls.append((re.compile(urlpath), obj, kwargs))



    def install(self):
        #if hasattr(self.settings, 'HOME') and self.settings.HOME not in sys.path:
            #sys.path.insert(0, self.settings.HOME)
        if hasattr(self.settings, 'HOME'):
            confpath = os.path.join(self.settings.HOME, 'conf')
            if os.path.isdir(confpath) and confpath not in sys.path:
                sys.path.insert(0, confpath)


        if hasattr(self.settings, 'TEMPLATE') and self.settings.TEMPLATE:
            tplcf = self.settings.TEMPLATE
            if tplcf['tmp'] and not os.path.isdir(tplcf['tmp']):
                os.mkdir(tplcf['tmp'])
            if tplcf['path']:
                log.info('initial template')
                template.install(tplcf['path'], tplcf['tmp'], tplcf['cache'],
                                 self.settings.CHARSET)

        if hasattr(self.settings, 'DATABASE') and self.settings.DATABASE:
            log.info('initial database')
            dbpool.install(self.settings.DATABASE)

        self.urls = []
        if hasattr(self.settings, 'APP_PATH'):
            log.debug('APP_PATH: %s', self.settings.APP_PATH)
            if self.settings.APP_PATH and os.path.isdir(self.settings.APP_PATH):
                apps = os.listdir(self.settings.APP_PATH)
                sys.path.append(self.settings.APP_PATH)
                for appname in apps:
                    if '.' in appname:
                        continue
                    self.add_app(appname)

        log.info('initial url')
        if hasattr(self.settings.URLS, 'urls'):
            self.add_urls(self.settings.URLS.urls)
        else:
            self.add_urls(self.settings.URLS)

    def run(self, host='0.0.0.0', port=8000):
        from gevent.wsgi import WSGIServer

        server = WSGIServer((host, port), self)
        server.backlog = 1024
        try:
            log.info("Server running on %s:%d" % (host, port))
            server.serve_forever()
        except KeyboardInterrupt:
            server.stop()


    def add_app(self, appname):
        log.info('add app:%s', appname)
        m = __import__(appname)
        self.add_urls(m.urls, appname)
        self._all_static_paths['/app/{0}/static'.format(appname)] = \
            os.path.join(self.settings.HOME, 'bin/apps', appname, 'static')
        return m

    def __call__(self, environ, start_response):
        times = [time.time()]
        req  = None
        resp = None
        viewobj = None
        try:
            if self.reloader:
                if self.reloader():
                    self.install()
            req = Request(environ)
            times.append(time.time())
            rpath = req.path

            # 静态文件
            if self._all_static_paths:
                for k,v in self._all_static_paths.items():
                    if rpath.startswith(k):
                        fpath = rpath.replace(k, v, 1)
                        log.debug('local {0} => {1}'.format(rpath, fpath))
                        if os.path.isfile(fpath):
                            resp = self.static_file(req, fpath)
                        else:
                            resp = NotFound('Not Found')
                        break
            if resp is None:
                # 匹配url
                for regex, view, kwargs in self.urls:
                    match = regex.match(rpath)
                    if match is not None:
                        if req.method not in self.allowed_methods:
                            raise NotImplemented
                        args    = ()
                        kw = {}
                        kw.update(kwargs)
                        mkwargs = match.groupdict()
                        if mkwargs:
                            kw.update(mkwargs)
                        else:
                            args = match.groups()
                        #log.debug('url match:%s %s', args, kwargs)

                        times.append(time.time())
                        viewobj = view(self, req)
                        #viewobj.config = self.settings

                        midwares = []
                        try:
                            viewobj.initial()
                            viewobj.allowed_methods = self.allowed_methods

                            if hasattr(self.settings, 'MIDDLEWARE'):
                                for x in self.settings.MIDDLEWARE:
                                    log.debug('run middleware %s', x)
                                    try:
                                        obj = middleware.__dict__[x]()
                                    except:
                                        log.warning('middleware %s create error!')
                                        log.warning(traceback.format_exc())
                                        continue
                                    obj.before(viewobj, *args, **kw)
                                    midwares.append(obj)

                            ret = getattr(viewobj, req.method)(*args, **kw)
                            if ret:
                                if isinstance(ret, (str, bytes)) and not viewobj.resp.content:
                                    viewobj.resp.write(ret)
                                elif isinstance(ret, Response):
                                    viewobj.resp = ret

                            for obj in midwares:
                                obj.after(viewobj)

                            viewobj.finish()

                        except HandlerFinish as e:
                            log.info(str(e))
                            if not viewobj.resp.content:
                                viewobj.resp.result(e.code, e.value)
                        resp = viewobj.resp
                        break
                else:
                    resp = NotFound('Not Found')
        except Exception as e:
            times.append(time.time())
            log.warn('web call error: %s', traceback.format_exc())

            if not viewobj or not viewobj.resp.content:
                if self.debug:
                    resp = Response('<pre>%s</pre>' % traceback.format_exc(), 500)
                else:
                    resp = Response('internal error', 500)

        times.append(time.time())
        #s = '%s %s %s ' % (req.method, req.path, str(viewobj.__class__)[8:-2])
        s = [str(resp.status), req.method, rpath]
        s.append('%d' % ((times[-1]-times[0])*1000000))
        #s.append('%d' % ((times[1]-times[0])*1000000))
        s.append('%d' % ((times[-1]-times[-2])*1000000))
        try:
            if req.query_string:
                s.append(req.query_string[:1024])
            if req.method in ('POST', 'PUT'):
                s.append(str(req.postdata())[:1024])
            if not req.input() and req.data:
                s.append(str(req.data)[:1024])
            # if resp.content and resp.headers['Content-Type'].startswith('application/json'):
            if resp.content and resp.content[0] == 123 and resp.content[-1] == 125:  # json, start { end }
                s.append(str(resp.content)[:1024])
        except:
            log.error(traceback.format_exc())
        if not rpath.startswith(tuple(self.settings.STATICS.keys())):
            log.warn('|'.join(s))

        return resp(environ, start_response)

    def static_file(self, req, fpath):
        mtype, encoding = mimetypes.guess_type(fpath)
        if not mtype:
            mtype = 'application/octet-stream'

        try:
            reqtm = 0
            reqgmt = req.environ.get('HTTP_IF_MODIFIED_SINCE')
            if reqgmt:
                reqgmt = reqgmt[:reqgmt.find('GMT') + 3]
                reqtm  = time.strptime(reqgmt, '%a, %d %b %Y %H:%M:%S GMT')
                if type(reqtm) != float:
                    reqtm = time.mktime(reqtm) + (time.mktime(time.localtime()) - time.mktime(time.gmtime()))
        except:
            log.warn(traceback.format_exc())
            reqtm  = 0

        mtime = os.path.getmtime(fpath)
        gmt   = time.strftime('%a, %d %b %Y %H:%M:%S GMT', time.gmtime(mtime))
        if mtime > reqtm or mtype == 'application/octet-stream':
            with open(fpath, 'rb') as f:
                s = f.read()
            resp = Response(s, mimetype=mtype)
        else:
            resp = Response('', status=304, mimetype=mtype)
        resp.headers['Last-Modified'] = gmt

        return resp


def route(path):
    '''给handler类用的url装饰器'''
    def _(h):
        app.add_url(path, h)
        return h
    return _





