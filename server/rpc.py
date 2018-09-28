# coding: utf-8
import os, sys
import struct
import time, random
import traceback
from functools import partial
import tornado
from tornado import ioloop
from tornado.tcpserver import TCPServer
from tornado.tcpclient import TCPClient
import socket
import zlib
import ssl
import logging
import json
from gevent.server import StreamServer

log = logging.getLogger()

rpc_funcs = {}
protocol = 'msgpack'
serial = __import__(protocol)

VERSION = '1'

RET_OK  = 0
RET_ERR = -1

# === flag标记 ===
# -------------------------------------------------------------
# | 请求方向 | 包结束标记 | 数据压缩 | 应答模式 | 处理模式 |
# -------------------------------------------------------------
# 版本 1-9 A-Z a-z 最大61个版本
FLAG_VER    = 0
# 请求方向 0.请求 1.应答
FLAG_DI     = 1
FLAG_DI_REQ   = '0'
FLAG_DI_RESP  = '1'
# 包结束   0.结束 1.未结束
FLAG_STATE  = 2
FLAG_STATE_END = '0'
FLAG_STATE_GO  = '1'
# 数据压缩 0.无压缩 1.zlib压缩 2.quicklz压缩
FLAG_COMP   = 3
FLAG_COMP_NO    = '0'
FLAG_COMP_ZLIB  = '1'
FLAG_COMP_QLZ   = '2'
# 应答模式 1.处理完后应答  2.接收到后应答 3.无应答
FLAG_WAIT   = 4
FLAG_WAIT_ACOM     = '1'
FLAG_WAIT_RECV     = '2'
FLAG_WAIT_NO       = '3'
# 处理模式 1.同步 2.异步
FLAG_MODE  = 5
FLAG_MODE_SYNC  = '1'
FLAG_MODE_ASYNC = '2'

# 结束
FLAG_MAX = 6


def _json_default_trans(obj):
    '''json对处理不了的格式的处理方法'''
    if isinstance(obj, datetime.datetime):
        return obj.strftime('%Y-%m-%d %H:%M:%S')
    if isinstance(obj, datetime.date):
        return obj.strftime('%Y-%m-%d')
    raise TypeError('%r is not JSON serializable' % obj)


def install(p, funcs=None):
    global protocol, serial, rpc_funcs
    if funcs:
        rpc_funcs.update(funcs)
    protocol = p
    serial = __import__(protocol)
    if protocol == 'json':
        serial.dumps = partial(serial.dumps, default=_json_default_trans, separators=(',', ':'))

def recvall(sock, count):
    buf = ''
    while count:
        newbuf = sock.recv(count)
        if not newbuf: return buf
        buf += newbuf
        count -= len(newbuf)
    return buf

def flag_init(di=FLAG_DI_REQ, state=FLAG_STATE_END, comp=FLAG_COMP_NO,
              wait=FLAG_WAIT_ACOM, mode=FLAG_MODE_SYNC):

    return [VERSION[0], di[0], state[0], comp[0], wait[0], mode[0]]


class Protocol (object):
    def __init__(self, body=''):
        self.body = body
        self.head = ''
        self.data = None

        self.msgid = 0
        self.name  = ''
        self.flag  = ['*'] * FLAG_MAX
        self.retcode = None

        if body:
            self.loads(body)

    def loads(self, body):
        self.body = body
        self.flag, self.msgid, self.name, self.data = serial.loads(body)
        self.flag = [ x for x in self.flag ]
        if self.flag[FLAG_COMP] == FLAG_COMP_ZLIB:
            self.data = serial.loads(zlib.decompress(self.data))

        if isinstance(self.name, int):
            self.retcode = self.name
            self.name = ''
            return self.flag, self.msgid, self.retcode, self.data
        else:
            return self.flag, self.msgid, self.name, self.data

    def dumps(self):
        args = self.data
        if self.flag[FLAG_COMP] == FLAG_COMP_ZLIB:
            args = zlib.compress(serial.dumps(self.data))
        obj = [''.join(self.flag), self.msgid, self.name, args]
        return serial.dumps(obj)



# request to server
class ReqProtocol (Protocol):
    # flag, seqid, name, args
    def __init__(self, body=None):
        super(ReqProtocol, self).__init__(body)

        if not body:
            self.flag = flag_init(di=FLAG_DI_REQ,
                    state=FLAG_STATE_END,
                    comp=FLAG_COMP_NO,
                    wait=FLAG_WAIT_ACOM,
                    mode=FLAG_MODE_SYNC)

    def make_resp(self, retdata, retcode=0):
        resp = RespProtocol()
        resp.retcode = retcode
        resp.data  = retdata
        resp.msgid = self.msgid

        resp.flag  = flag_init(FLAG_DI_RESP,
                self.flag[FLAG_STATE],
                self.flag[FLAG_COMP],
                self.flag[FLAG_WAIT],
                self.flag[FLAG_MODE])

        return resp


# response from server
class RespProtocol (Protocol):
    # flag, seqid, retcode, retmsg
    def __init__(self, body=None):
        super(RespProtocol, self).__init__(body)

        if not body:
            self.flag = flag_init(di=FLAG_DI_RESP,
                    state=FLAG_STATE_END,
                    comp=FLAG_COMP_NO,
                    wait=FLAG_WAIT_ACOM,
                    mode=FLAG_MODE_SYNC)


    def dumps(self):
        args = self.data
        if self.flag[FLAG_COMP] == FLAG_COMP_ZLIB:
            args = zlib.compress(serial.dumps(self.data))
        obj = [''.join(self.flag), self.msgid, self.retcode, self.data]
        return serial.dumps(obj)


class ServerApply:
    pre_check = lambda self,data,client: 0

    def __init__(self, client):
        self.client = client

    def find_func(self, name):
        global rpc_funcs

        if isinstance(rpc_funcs, dict):
            return rpc_funcs[name]
        else: # module
            m = rpc_funcs
            p = name.split('.')

            for k in p:
                m = getattr(m, k, None)
                if not m:
                    return None
            return m

    def server_call(self, data, sendfunc):
        tstart = time.time()
        #log.debug('recv: %s', repr(data))

        try:
            prot = ReqProtocol(data)
            flag, msgid, name, args = prot.flag, prot.msgid, prot.name, prot.data
        except:
            log.warn('parse data error:%s', repr(data))
            raise

        self.pre_check(prot, self.client)

        retcode = 0
        retmsg  = ''
        senddata = True
        try:
            if flag[FLAG_WAIT] == FLAG_WAIT_RECV:
                retmsg = prot.make_resp('').dumps()
                sendfunc(retmsg)
                senddata = False
            elif flag[FLAG_WAIT] == FLAG_WAIT_NO:
                senddata = False


            func = self.find_func(prot.name)
            if not func:
                retmsg = 'not found func:%s' % prot.name
                log.debug(retmsg)
                if senddata:
                    retmsg = prot.make_resp(retmsg, RET_ERR).dumps()
                    return retmsg
            ret = None
            try:
                if isinstance(args, list) or isinstance(args, tuple):
                    ret = func(*args)
                elif isinstance(args, dict):
                    ret = func(**args)
                else:
                    ret = func(args)
                #ret = self.post_apply(data, ret, self.client)
                log.debug('return:%s', ret)
            except Exception, e:
                retcode = -1
                ret = 'error: ' + str(e)
                log.info(traceback.format_exc())

            if senddata:
                retmsg = prot.make_resp(ret, retcode).dumps()
                return retmsg
        except Exception, e:
            ret = str(e)
            retcode = -1
            log.info(traceback.format_exc())
            if senddata:
                retmsg = prot.make_resp(ret, retcode).dumps()
                return retmsg
        finally:
            log.info('func=%s|msgid=%d|flag=%s|ret=%d|time=%d|args=%s',
                    name, msgid, ''.join(flag), retcode, (time.time()-tstart)*1000, json.dumps(args))



class TornadoRPCServerConn:
    clients = 0
    max_body = 1048576
    def __init__(self, stream, addr):
        self.stream = stream
        self.addr   = addr

        self.stream.read_bytes(4, self.on_head)
        self.stream.set_close_callback(self.on_close)

        self.server_apply = ServerApply(addr)

        TornadoRPCServerConn.clients += 1

    def on_close(self):
        self.stream = None
        TornadoRPCServerConn.clients -= 1
        log.info('func=close|remote=%s:%d', self.addr[0], self.addr[1])

    def on_head(self, data):
        #log.info('func=recv_head|remote=%s:%d|data=%s', self.addr[0], self.addr[1], repr(data))
        try:
            bodylen = struct.unpack('I', data)[0]
            if bodylen > 0:
                self.stream.read_bytes(bodylen, self.on_body)
            elif bodylen > self.max_body:
                log.warn('body too long. %d', bodylen)
                self.stream.close()
            else:
                log.warn('recv head body error:%d', bodylen)
                self.stream.close()
        except:
            log.info(traceback.format_exc())
            self.stream.close()

    def on_body(self, data):
        #log.info('func=recv_body|remote=%s:%d|len=%d|data=%s', self.addr[0], self.addr[1], len(data), repr(data[:32]))
        self.stream.read_bytes(4, self.on_head)
        try:
            ret = self.server_apply.server_call(data, sendfunc=self.send_resp)
            #log.info('ret=%s', ret)
            if isinstance(ret, str):
                #self.stream.write(struct.pack('I', len(ret)) + ret)
                self.send_resp(ret)
        except:
            log.info('server call error, close conn')
            log.info(traceback.format_exc())
            self.stream.close()

    def send_resp(self, data):
        self.stream.write(struct.pack('I', len(data)) + data)




class TornadoRPCServer (TCPServer):
    def handle_stream(self, stream, addr):
        try:
            log.info('func=conn|remote=%s:%d|clients=%d', addr[0], addr[1], TornadoRPCServerConn.clients)
            TornadoRPCServerConn(stream, addr)
        except:
            log.info(traceback.format_exc())
            stream.close()

def tornado_server(port):
    io_loop = ioloop.IOLoop.instance()
    server = TornadoRPCServer(io_loop, max_buffer_size=32768)
    server.bind(port)
    server.start(1)
    log.info('server started at:%d', port)
    io_loop.start()
    log.warn("stopped")



def gevent_rpc_server(sock, address):
    def send_resp(data):
        sock.send(struct.pack('I', len(data)) + data)

    server_apply = ServerApply(address)
    while True:
        try:
            headstr = sock.recv(4)
            if not headstr:
                break
            bodylen = struct.unpack('I', headstr)[0]
            #log.debug('head len:%d', bodylen)
            data = recvall(sock, bodylen)
            ret = server_apply.server_call(data, sendfunc=send_resp)
            if isinstance(ret, str):
                send_resp(ret)
                #sock.send(struct.pack('I', len(ret)) + ret)
        except:
            log.info(traceback.format_exc())
            sock.close()
            break

def gevent_server(port):
    srv = StreamServer(('0.0.0.0', port), gevent_rpc_server)
    log.info('server started at:%d', port)
    srv.serve_forever()
    log.warn("stopped")




class RPCError (Exception):
    pass


def tornado_websocket_server(port, path='/'):
    from tornado import websocket
    class WebSocketRPCHandler (websocket.WebSocketHandler):
        def initial(self):
            self.q = {}

        def open(self, *args, **kwargs):
            log.debug('conn open: %s %s', args, kwargs)

        def on_message(self, message):
            try:
                ret = server_call(message, self.write_message)
                log.info('ret=%s', ret)
                if isinstance(ret, str):
                    self.write_message(ret)
            except:
                log.info(traceback.format_exc())

        def on_close(self):
            log.debug('conn close: %s %s', self.close_code, self.close_reason)

        def check_origin(self, origin):
            return True


    application = tornado.web.Application([(path, WebSocketRPCHandler),])
    application.listen(port)
    log.info('server started at:%d', port)
    tornado.ioloop.IOLoop.instance().start()
    log.warn("stopped")


def gevent_websocket_server(port, path='/'):
    from geventwebsocket import WebSocketServer, WebSocketApplication, Resource

    class WebSocketRPCApplication(WebSocketApplication):
        def on_open(self):
            log.debug('conn open: %s %s', args, kwargs)

        def on_message(self, message):
            try:
                ret = server_call(message, self.ws.send)
                log.info('ret=%s', ret)
                if isinstance(ret, str):
                    self.ws.send(ret)
            except:
                log.info(traceback.format_exc())


        def on_close(self, reason):
            log.debug('conn close: %s', reason)



    srv = WebSocketServer(('0.0.0.0', port), Resource({path: MyApplication}))
    log.info('server started at:%d', port)
    srv.serve_forever()
    log.warn("stopped")


server = gevent_server
websocket_server = gevent_websocket_server




class RPCClient:
    def __init__(self, addr, timeout=0, keyfile=None, certfile=None):
        self._addr = addr
        self._seqid = random.randint(0, 1000000)
        self._conn = None
        self._timeout = timeout # 毫秒
        self.flag = flag_init()
        self._keyfile = keyfile
        self._certfile = certfile

    def _connect(self):
        log.debug('connect to %s', self._addr)
        self._conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if self._keyfile:
            self._conn = ssl.wrap_socket(self._conn, keyfile=self._keyfile, certfile=self._certfile)
        if self._timeout > 0:
            self._conn.settimeout(self._timeout/1000.0)
        self._conn.connect(self._addr)
        #self._conn.settimeout(None)

    def _call(self, name, args):
        t = time.time()
        retcode = -1
        retmsg = ''
        try:
            send_seqid = self._seqid
            prot = ReqProtocol()
            prot.name = name
            prot.data = args
            prot.msgid = send_seqid
            prot.flag = self.flag
            s = prot.dumps()
            log.debug('send:%s', repr(s))
            #s = self.pre_apply(s)
            #s = client_pack(send_seqid, name, args)
            s = struct.pack('I', len(s)) + s
            self._seqid += 1

            if not self._conn:
                self._connect()

            self._conn.sendall(s)
            if prot.flag[FLAG_WAIT] != FLAG_WAIT_NO:
                data = self._recv()
                #data = self.post_apply(data)
                log.debug('recv:%s', repr(data))
                prot2 = ReqProtocol()
                flag, seqid, retcode, retmsg = prot2.loads(data)
                if seqid != send_seqid:
                    raise RPCError, 'seqid error: %d,%d' % (send_seqid, seqid)
                if retcode != 0:
                    raise RPCError, 'retcode error:%d %s' % (retcode, retmsg)
                return retmsg
        except:
            raise
        finally:
            log.info('server=rpc|func=%s|time=%d|ret=%d', name, (time.time()-t)*1000000, retcode)

    def _recv(self):
        head = self._conn.recv(4)
        if not head:
            raise RPCError, 'connection closed'
        #log.debug('recv head:%s', repr(head))
        bodylen = struct.unpack('I', head)[0]
        return recvall(self._conn, bodylen)


    def __getattr__(self, name):
        def _(*args):
            return self._call(name, args)
        return _





