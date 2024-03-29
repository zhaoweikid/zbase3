# coding: utf-8

if __name__ == '__main__':
    from gevent import monkey;

    monkey.patch_all()

from gevent.pywsgi import WSGIServer
from zbase3.base.excepts import MethodError, MethodFail
from zbase3.server.rpc import *
from zbase3.web import core
from zbase3.web.validator import with_anno_check

log = logging.getLogger()


def recvall(sock, count):
    buf = []
    while count:
        newbuf = sock.recv(count)
        if not newbuf:
            return b''.join(buf)
        count -= len(newbuf)
        if count == 0 and not buf:
            return newbuf
        buf.append(newbuf)
    return b''.join(buf)


def call_handler(handlercls, data, addr, allow_noreply=True, vlog=True, dumpheader=True):
    p1 = ReqProto.loads(data)
    p2 = RespProto.fromReq(p1)

    start = time.time()
    try:
        log.debug('call %s %s', p1.name, p1.params)
        handler = handlercls(addr, p1, p2)
        if hasattr(handler, "_initial"):
            handler._initial()

        f = obj = handler
        for name in p1.name.split('.', 1):
            if name.startswith('_'):
                raise MethodError()
            obj = f
            f = getattr(f, name, None)
            if not f:
                raise MethodError()

        # XXX 装饰器兼容, 防止self参数丢掉
        fn = with_anno_check(f.__func__)
        if isinstance(p1.params, dict):
            p2ret = fn(obj, **p1.params)
        else:
            p2ret = fn(obj, *p1.params)

        if isinstance(p2ret, tuple):
            if len(p2ret) == 2:  # 返回两个
                p2.retcode, p2.result = p2ret
            elif len(p2ret) == 3:  # 返回三个有扩展数据
                p2.retcode, p2.result, p2.extend = p2ret
            else:
                raise ValueError("handler return value error, must []/{}/(int,obj)/(int,obj,obj")
        else:
            # 只返回一个(不能是tuple类型)表示成功，返回的是成功的数据
            p2.retcode, p2.result = 0, p2ret

        if hasattr(handler, "_finish"):
            handler._finish()
    except MethodError as e:
        # 没有此方法
        log.warning('not found method: ' + p1.name)
        p2.msgtype = TYPE_REPLY_EXCEPT
        p2.retcode = ERR_METHOD
        p2.result = "error, not found method " + p1.name
    except MethodFail as e:
        # 方法调用返回了失败
        log.warning('method run return fail: ' + p1.name)
        p2.retcode = e.retcode
        p2.result = e.result
    except Exception as e:
        p2.msgtype = TYPE_REPLY_EXCEPT
        p2.retcode = ERR_EXCEPT
        p2.result = str(e)
        log.info(traceback.format_exc())
    finally:
        if vlog:
            end = time.time()
            log.info('f=%s|remote=%s:%d|id=%d|t=%d|arg=%s|mt=%d|ret=%d|data=%s',
                     p1.name, addr[0], int(addr[1]), p1.msgid, int((end - start) * 1000000),
                     p1.params, p2.msgtype, p2.retcode, json.dumps(p2.result))

    if allow_noreply and p1.msgtype == TYPE_CALL_NOREPLY:
        return ''

    ret = p2.dumps(dumpheader)
    return ret


class ServerHandler:
    def __init__(self, handlercls):
        self._handlercls = handlercls
        self.reqs = 0
        self.max_req = 0

    def check_req(self):
        if self.max_req > 0 and self.reqs > self.max_req:
            log.warning('request max, quit %d>%d', self.reqs, self.max_req)
            if hasattr(self, 'stop'):
                self.stop()
            else:
                os._exit(0)

        self.reqs += 1

    def handle(self, sock, addr):
        pass


class TCPServerHandler(ServerHandler):
    def handle(self, sock, addr):
        def read_data(n):
            ret = recvall(sock, n)
            if isinstance(ret, bytes):
                return ret.decode('utf-8')
            return ret

        def write_data(data):
            if isinstance(data, str):
                data = data.encode('utf-8')
            return sock.sendall(data)

        while True:
            self.check_req()

            headstr = read_data(8)
            # log.debug('read head:%s', headstr)
            if not headstr:
                log.debug('client conn close, break')
                break
            bodylen = int(headstr)
            data = read_data(bodylen)
            # log.debug('read body:%s', data)
            if not data or len(data) != bodylen:
                log.info('read rpc body error, body=%d read=%d', bodylen, len(data))
                break

            ret = call_handler(self._handlercls, data, addr, True, True)
            if ret:
                write_data(ret)


class TCPServer(StreamServer, TCPServerHandler):
    def __init__(self, addr, handlercls, spawn='default'):
        StreamServer.__init__(self, addr, spawn=spawn)
        TCPServerHandler.__init__(self, handlercls)


class UDPServerHandler(ServerHandler):
    def handle(self, data, addr):
        self.check_req()

        ret = call_handler(self._handlercls, data[8:], addr, True, True)
        if ret:
            self.socket.sendto(ret, addr)


class UDPServer(DatagramServer, UDPServerHandler):
    def __init__(self, addr, handlercls):
        DatagramServer.__init__(self, addr)
        UDPServerHandler.__init__(self, handlercls)


class HTTPServerHandler(core.Handler):
    def POST(self, cls):
        log.debug('post data:%s', self.req.data)

        addr = (self.req.clientip(), 0)
        ret = call_handler(cls, self.req.data, addr, False, True, False)
        self.write(ret)


class HTTPServer(WSGIServer):

    def __init__(self, addr, handlercls, conf=None):
        if not conf:
            class C: pass

            conf = C()
            conf.URLS = (('^.*$', HTTPServerHandler, {'cls': handlercls}),)
        app = core.WebApplication(conf)
        WSGIServer.__init__(self, addr, app)


class Handler:
    def __init__(self, addr, data, resp):
        self.addr = addr
        self.data = data
        self.resp = resp

        logger.set_req_id(self.data.logid)

    def ping(self, name=''):
        '''服务状态检测'''
        return 0, {'now': str(datetime.datetime.now())[:19], 'data': 'pong', 'name': name}


class Server:
    def __init__(self, port, handlercls, proto='tcp'):
        self.port = port
        self.handlercls = handlercls
        self.proto = proto
        self.server = []

        server_map = {
            'tcp': TCPServer,
            'udp': UDPServer,
            'http': HTTPServer,
        }
        ps = proto.split(',')
        if len(ps) == 2:
            for p in ps:
                self.server.append(server_map[p](('0.0.0.0', port), self.handlercls))
                log.info('%s server started at:%d', p, port)
        else:
            self.server.append(server_map[ps[0]](('0.0.0.0', port), self.handlercls))
            log.warning('server started at:%d', port)

    def start(self):
        if len(self.server) == 2:
            gevent.spawn(self.server[0].serve_forever)
            self.server[1].serve_forever()
            log.warning("server stopped")
        else:
            self.server[0].serve_forever()
            log.warning("server stopped")


def test_server(port=7000):
    global log
    log = logger.install('stdout')

    class MyHandler(Handler):
        def ping(self):
            return 0, 'pong'

        def haha(self):
            return 'haha'

        def error(self):
            raise MethodFail(-1, 'call error function')

    server = Server(port, MyHandler, proto='tcp,udp')
    server.start()


def test_http_server(port=7000):
    global log
    log = logger.install('stdout')

    class MyHandler(Handler):
        pass

    server = Server(port, MyHandler, proto='http')
    server.start()


def test():
    f = globals()[sys.argv[1]]
    if len(sys.argv) == 3:
        f(int(sys.argv[2]))  # port
    else:
        f()


if __name__ == '__main__':
    test()
