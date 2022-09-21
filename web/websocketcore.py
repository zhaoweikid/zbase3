import re
import time
import base64
import hashlib
import logging

from gevent.pywsgi import WSGIServer
from gevent.pywsgi import WSGIHandler
from zbase3.web.core import WebApplication, Handler as WebHandler
from zbase3.web.websocket import WebSocketError
from zbase3.web.websocket import WebSocket, Stream
from zbase3.base import logger

log = logging.getLogger()


class Client(object):
    def __init__(self, address, ws):
        self.address = address
        self.ws = ws


class WebSocketHandler(object):
    PROTOCOL_NAME = ''

    def __init__(self, environ, ws):
        self.environ = environ
        self.ws = ws

    def handle(self):
        self.on_open()
        while True:
            try:
                message = self.ws.receive()
                stime = time.time()
            except WebSocketError:
                if not getattr(self, 'server_close', False):
                    self.on_close('close')
                break
            if message:
                resp = self.on_message(message)
                log.info(
                    'time=%s|origin=%s|req=%s|resp=%s',
                    time.time()-stime,
                    self.environ.get('HTTP_X_REAL_IP', '') or self.environ.get(
                        'REMOTE_ADDR', '') or '-',
                    message, resp or ''
                )
                if resp:
                    self.ws.send(resp)

    def on_open(self, *args, **kwargs):
        pass

    def on_close(self, *args, **kwargs):
        pass

    def on_message(self, message, *args, **kwargs):
        return message

    @classmethod
    def protocol_name(cls):
        return cls.PROTOCOL_NAME

    @property
    def server(self):

        return self.ws.handler.server

    @property
    def handler(self):

        return self.ws.handler


class WebSocketApplication(object):
    def __init__(self, urls, settings):
        self.conf = settings
        self.urls = urls

    def _app_by_path(self, environ_path):
        """匹配对应的application
        """
        for path, app in self.urls:
            if re.match(path, environ_path):
                return app
        return None

    def app_protocol(self, path):
        """子协议匹配如果设置了子协议 客户端进行匹配
        """
        app = self._app_by_path(path)

        if hasattr(app, 'protocol_name'):
            return app.protocol_name()
        else:
            return ''

    def __call__(self, environ, start_response):
        environ = environ
        current_app = self._app_by_path(environ['PATH_INFO'])

        if current_app is None:
            raise Exception("No apps defined")

        ws = environ['wsgi.websocket']
        current_app = current_app(environ, ws)
        current_app.ws = ws
        current_app.conf = self.conf
        current_app.handle()
        return []


class WebSocketHTTPApplication(object):
    """支持 websocket http server
    """

    def __init__(self, settings):
        self._register_app(settings)

    def _register_app(self, settings):
        urls = settings.URLS.urls
        self.websocket_urls, self.http_urls = [], []
        for url in urls:
            if issubclass(url[1], WebHandler):
                self.http_urls.append(url)
            elif issubclass(url[1], WebSocketHandler):
                self.websocket_urls.append(url)

        self.websocket_app = WebSocketApplication(
            self.websocket_urls, settings)

        settings.URLS.urls = self.http_urls
        self.http_app = WebApplication(settings)
        self.http_path = [k[0] for k in self.http_urls]

    def __call__(self, environ, start_response):
        path = environ.get('PATH_INFO', '')
        if path in self.http_path:
            return self.http_app(environ, start_response)
        else:
            return self.websocket_app(environ, start_response)


class WebSocketWSGIHandler(WSGIHandler):

    def __init__(self, *args, **kwargs):
        super(WebSocketWSGIHandler, self).__init__(*args, **kwargs)

    SUPPORTED_VERSIONS = ('13', '8', '7')
    GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

    def run_websocket(self):
        """
        1. 调用websockethandler 处理业务逻辑
        """
        # wsgi 内部参数设定
        if getattr(self, 'prevent_wsgi_call', False):
            return

        if not hasattr(self.server, 'clients'):
            self.server.clients = {}

        try:
            self.server.clients[self.client_address] = Client(
                self.client_address, self.websocket)
            list(self.application(self.environ, lambda s, h, e=None: []))
        finally:
            del self.server.clients[self.client_address]
            if not self.websocket.closed:
                self.websocket.close()
            self.environ.update({
                'wsgi.websocket': None
            })
            self.websocket = None

    def run_application(self):
        """wsgi 复用run_application 方法
        """
        # 支持http协议
        # 由于wsgiserver参数限制 目前只能通过接口区分使用 不支持模糊匹配
        self.http_flag = False
        path = self.environ.get('PATH_INFO', '')
        if path in self.application.http_path:
            self.http_flag = True
            return super().run_application()

        # 设置请求头部log id websocket 可以设置头部信息
        reqid = self.environ.get('X-Req-Id', '')
        logger.set_req_id(reqid)
        log.debug('X-Req-Id: %s', reqid)
        # 获取请求结果
        self.result = self.upgrade_websocket()

        if hasattr(self, 'websocket'):
            if self.status and not self.headers_sent:
                self.write('')
            self.run_websocket()
        else:
            self.result = ['No Websocket protocol defined']
            self.close_connection = True

    def upgrade_websocket(self):
        """判断请求头部信息是否正确 返回处理结果
        """
        if self.environ.get('REQUEST_METHOD', '') != 'GET':
            # websocket 必须是GET方法
            log.info('Can only upgrade connection if using GET method.')
            return

        upgrade = self.environ.get('HTTP_UPGRADE', '').lower()

        if upgrade == 'websocket':
            connection = self.environ.get('HTTP_CONNECTION', '').lower()

            if 'upgrade' not in connection:
                # 值必须为upgrade
                log.warning("Client didn't ask for a connection "
                            "upgrade")
                return ['Websocket protocol Error']
        else:
            # 不是websocket 连接 不处理直接返回
            return ['Websocket protocol Error']

        # websocket 协议必须是http1.1
        if self.request_version != 'HTTP/1.1':
            self.start_response('402 Bad Request', [])
            log.warning("Bad server protocol in headers")
            return ['Bad protocol version']

        if self.environ.get('HTTP_SEC_WEBSOCKET_VERSION'):
            return self.upgrade_connection()
        else:
            log.warning("No protocol defined")
            self.start_response('426 Upgrade Required', [
                ('Sec-WebSocket-Version', ', '.join(self.SUPPORTED_VERSIONS))])

            return ['No Websocket protocol version defined']

    def upgrade_connection(self):
        """
        1. 判断支持websocket协议版本
        2. 判断是否传入HTTP_SEC_WEBSOCKET_KEY值 记录着握手过程中必不可少的键值
        3. Sec-WebSocket-Protocol: chat, superchat 协议支持
        """

        log.info("Attempting to upgrade connection")

        version = self.environ.get("HTTP_SEC_WEBSOCKET_VERSION")

        if version not in self.SUPPORTED_VERSIONS:
            msg = "Unsupported WebSocket Version: {0}".format(version)

            log.warning(msg)
            self.start_response('400 Bad Request', [
                ('Sec-WebSocket-Version', ', '.join(self.SUPPORTED_VERSIONS))
            ])

            return [msg]

        key = self.environ.get("HTTP_SEC_WEBSOCKET_KEY", '').strip()

        if not key:
            # 5.2.1 (3)
            msg = "Sec-WebSocket-Key header is missing/empty"

            log.warning(msg)
            self.start_response('400 Bad Request', [])

            return [msg]

        try:
            key_len = len(base64.b64decode(key))
        except TypeError:
            msg = "Invalid key: {0}".format(key)

            log.warning(msg)
            self.start_response('400 Bad Request', [])

            return [msg]

        if key_len != 16:
            msg = "Invalid key: {0}".format(key)

            log.warning(msg)
            self.start_response('400 Bad Request', [])

            return [msg]

        # Check for WebSocket Protocols
        requested_protocols = self.environ.get(
            'HTTP_SEC_WEBSOCKET_PROTOCOL', '')
        protocol = None

        if hasattr(self.application, 'app_protocol'):
            allowed_protocol = self.application.app_protocol(
                self.environ['PATH_INFO'])

            if allowed_protocol and allowed_protocol in requested_protocols:
                protocol = allowed_protocol
                log.info("Protocol allowed: {0}".format(protocol))

        self.websocket = WebSocket(self.environ, Stream(self), self)
        self.environ.update({
            'wsgi.websocket_version': version,
            'wsgi.websocket': self.websocket
        })

        accept = base64.b64encode(
            hashlib.sha1((key + self.GUID).encode("latin-1")).digest()
        ).decode("latin-1")

        # 默认支持跨域
        http_origin = self.environ.get('HTTP_ORIGIN', '')

        headers = [
            ("Upgrade", "websocket"),
            ("Connection", "Upgrade"),
            ("Sec-WebSocket-Accept", accept),
            ("Access-Control-Allow-Origin", http_origin),
        ]

        if protocol:
            headers.append(("Sec-WebSocket-Protocol", protocol))

        log.info("WebSocket request accepted, switching protocols")
        self.start_response("101 Switching Protocols", headers)

    def log_request(self):
        if not self.http_flag and '101' not in str(self.status):
            log.info(self.format_request())

    @property
    def active_client(self):
        return self.server.clients[self.client_address]

    def start_response(self, status, headers, exc_info=None):
        """
        Called when the handler is ready to send a response back to the remote
        endpoint. A websocket connection may have not been created.
        """
        writer = super(WebSocketWSGIHandler, self).start_response(
            status, headers, exc_info=exc_info)

        self._prepare_response()

        return writer

    def _prepare_response(self):
        """websocket 不支持部分http协议 
        """
        assert not self.headers_sent

        if not self.environ.get('wsgi.websocket'):
            # a WebSocket connection is not established, do nothing
            return

        # content_length 不设置
        self.provided_content_length = False

        # The websocket is now controlling the response
        self.response_use_chunked = False

        # Once the request is over, the connection must be closed
        self.close_connection = True

        # Prevents the Date header from being written
        self.provided_date = True


class WebSocketServer(WSGIServer):
    handler_class = WebSocketWSGIHandler

    def __init__(self, *args, **kwargs):
        self.clients = {}
        super(WebSocketServer, self).__init__(*args, **kwargs)

    def handle(self, socket, address):
        handler = self.handler_class(socket, address, self)
        handler.handle()

    def serve_forever(self):
        log.info('%s server started at:%d', self.address[0], self.address[1])
        super().serve_forever()
