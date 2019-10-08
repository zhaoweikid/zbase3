# coding: utf-8
#from gevent import monkey; monkey.patch_socket()
import os, sys
import struct
import time, random
import datetime
import traceback
import tornado
from tornado import ioloop
from tornado.tcpserver import TCPServer
from tornado.tcpclient import TCPClient
import socket
import ssl
import logging
import json
import gevent
from gevent.server import StreamServer, DatagramServer
from zbase3.server import selector
from zbase3.server.defines import *
from zbase3.base import logger

'''
package format:
    | package len(8B) | json |

json:
    request: [verion, type, msgid, name, params]
    response: [version, type, msgid, code, result]

'''

log = logging.getLogger()

VERSION = 1

TYPE_CALL  = 100
TYPE_CALL_NOREPLY = 101
TYPE_REPLY = 200
TYPE_REPLY_EXCEPT = 201

class Protocol (object):
    def __init__(self):
        global VERSION
        self.version = VERSION
        self.msgid = 0
        self.msgtype = 0

    def __str__(self):
        return '<Protocol version:%d msgtype:%d msgid:%d>' % \
            (self.version, self.msgtype, self.msgid)

class ReqProto (Protocol):
    def __init__(self):
        Protocol.__init__(self)
        
        self.name  = ''
        self.params = []
        self.options = ''
        self.msgtype = TYPE_CALL

    def __str__(self):
        return '<ReqProto ver:%d msgid:%d name:%s param:%s>' % \
            (self.version, self.msgid, self.name, self.params)

    @staticmethod
    def loads(body):
        if isinstance(body, bytes):
            body = body.decode('utf-8')
        version, msgtype, msgid, name, params = json.loads(body)

        p = ReqProto()
        p.version = version
        p.msgtype = msgtype
        p.msgid   = msgid
        p.name    = name
        p.params  = params

        return p

        
    def dumps(self, head=True):
        if self.msgid == 0:
            self.msgid = random.randint(1, 100000000)
        obj = [self.version, self.msgtype, self.msgid, self.name, self.params]
        s = json.dumps(obj)
        if head:
            s = '%08d' % (len(s)) + s
        return s.encode('utf-8')


class RespProto (Protocol):
    def __init__(self, msgid):
        Protocol.__init__(self)

        self.msgid   = msgid
        self.retcode = None
        self.result  = None
        self.msgtype = TYPE_REPLY

    def __str__(self):
        return '<RespProto ver:%d msgid:%d code:%s result:%s>' % \
            (self.version, self.msgid, str(self.retcode), str(self.result))

    @staticmethod
    def loads(body):
        if isinstance(body, bytes):
            body = body.decode('utf-8')
        version, msgtype, msgid, code, result = json.loads(body)

        p = RespProto(msgid)
        p.version = version
        p.msgtype = msgtype
        p.retcode = code
        p.result  = result

        return p
        
    def dumps(self, head=True):
        if self.msgid == 0:
            self.msgid = random.randint(1, 100000000)
        obj = [self.version, self.msgtype, self.msgid, self.retcode, self.result]
        s = json.dumps(obj)
        if head:
            s = '%08d' % (len(s)) + s
        return s.encode('utf-8')




def recvall(sock, count):
    buf = []
    while count:
        newbuf = sock.recv(count)
        if not newbuf: 
            return ''.join(buf)
        count -= len(newbuf)
        if count == 0 and not buf:
            return newbuf
        buf.append(newbuf)
    return ''.join(buf)


class TCPServerHandler (object):
    def __init__(self, sock, addr, handler):
        self.sock = sock
        self.addr = addr
        self._handler = handler

    def read_data(self, n):
        ret = recvall(self.sock, n)
        if isinstance(ret, bytes):
            return ret.decode('utf-8')
        return ret

    def write_data(self, data):
        if isinstance(data, str):
            data = data.encode('utf-8')
        return self.sock.sendall(data)

    def handle(self):
        try:
            while True:
                headstr = self.read_data(8)
                #log.debug('read head:%s', headstr)
                if not headstr:
                    log.debug('read head return 0, break')
                    break
                bodylen = int(headstr)
                data = self.read_data(bodylen)
                #log.debug('read body:%s', data)
                if not data or len(data) != bodylen:
                    log.info('read body error')
                    break

                p1 = ReqProto.loads(data)
                p2 = RespProto(p1.msgid)
     
                start = time.time()
                try:
                    log.debug('call %s %s', p1.name, p1.params)
                    f = getattr(self._handler, p1.name, None)
                    if not f:
                        log.warn('not found method '+p1.name)
                        p2.retcode = ERR_METHOD
                        p2.result = "not found method " + p1.name
                        self.write_data(p2.dumps())
                        continue

                    if isinstance(p1.params, dict):
                        p2.retcode,p2.result = f(**p1.params)
                    else:
                        p2.retcode,p2.result = f(*p1.params)
                except Exception as e:
                    p2.retcode = ERR_EXCEPT
                    p2.result  = str(e)
                    log.info(traceback.format_exc())

                self.write_data(p2.dumps())
                end = time.time()
                log.info('func=%s|remote=%s:%d|id=%d|time=%d|params=%s|ret=%d|data=%s', 
                    p1.name, self.addr[0], self.addr[1], p1.msgid, int((end-start)*1000000), 
                    p1.params, p2.retcode, p2.result)
        except: 
            log.info(traceback.format_exc())


class RPCServerTCP(StreamServer):
    def __init__(self, addr, handlecls):
        StreamServer.__init__(self, addr)
        self._handlecls = handlecls

    def handle(self, sock, addr):
        #log.debug('conn %s %s', sock, addr)
        serv = TCPServerHandler(sock, addr, self._handlecls(addr))
        return serv.handle()


class RPCServerUDP(DatagramServer):
    def __init__(self, addr, handlecls):
        DatagramServer.__init__(self, addr)
        self._handlecls = handlecls

    def handle(self, data, address):
        p1 = ReqProto.loads(data[8:])
        p2 = RespProto(p1.msgid)

        start = time.time()
        try:
            obj = self._handlecls(address)
            f = getattr(obj, p1.name, None)
            if not f:
                log.warn('not found method '+p1.name)
                p2.retcode = ERR_METHOD
                p2.result = "not found method " + p1.name
                return

            if isinstance(p1.params, dict):
                p2.retcode,p2.result = f(**p1.params)
            else:
                p2.retcode,p2.result = f(*p1.params)
            self.socket.sendto(p2.dumps(), address)
        except Exception as e:
            log.warn(traceback.format_exc())
            p2.retcode = ERR_EXCEPT
            p2.result  = str(e)
        finally:
            end = time.time()
            log.info('func=%s|remote=%s:%d|id=%d|time=%d|params=%s|ret=%d|data=%s', 
                p1.name, address[0], address[1], p1.msgid, int((end-start)*1000000), 
                p1.params, p2.retcode, p2.result)


class Handler:
    def __init__(self, addr):
        self.addr = addr


def gevent_server(port, handler, proto='tcp'):
    servers = {'tcp':RPCServerTCP, 'udp':RPCServerUDP}
    ps = proto.split(',')

    if len(ps) == 2:
        srvs = []
        for p in ps:
            srvs.append(servers[p](('0.0.0.0', port), handler))
            log.info('%s server started at:%d', p, port)

        gevent.spawn(srvs[0].serve_forever)
        srvs[1].serve_forever()
        log.warn("server stopped")
    else: 
        srv = servers[ps[0]](('0.0.0.0', port), handler)
        log.warn('server started at:%d', port)
        srv.serve_forever()
        log.warn("server stopped")



class RPCError (Exception):
    pass


class RPCClient:
    def __init__(self, server, keyfile=None, certfile=None, proto='tcp'):
        self._server = None
        self._server_sel = None
        self._seqid = random.randint(0, 1000000)
        self._conn = None
        self._addr = None
        self._timeout = 10000 # 毫秒
        self._keyfile = keyfile
        self._certfile = certfile
        self._proto = proto

        if isinstance(server, dict): # 只有一个server
            self._server_sel = selector.Selector([server,], 'random')
        elif isinstance(server, list) or isinstance(server, tuple): # server列表，需要创建selector，策略为随机
            self._server_sel = selector.Selector(server, 'random')
        else: # 直接是selector
            self._server_sel = server

        self._connect()


    def __del__(self):
        self._close()

    def _close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    def _connect(self):
        while True:
            self._server = self._server_sel.next()
            if not self._server:
                self._restore()
                self._server = self._server_sel.next()
                if not self._server:
                    raise RPCError('no server')

            serv = self._server['server']
            
            if 'conn_timeout' in serv:
                timeout = serv.get('conn_timeout')
            elif 'timeout' in serv:
                timeout = serv.get('timeout')
            else:
                timeout = self._timeout
           
            ret = 0
            try:
                t = time.time()

                if self._proto == 'tcp':
                    self._conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    self._conn.setsockopt(socket.SOL_TCP, socket.TCP_NODELAY, 1)
                    if self._keyfile:
                        self._conn = ssl.wrap_socket(self._conn, keyfile=self._keyfile, certfile=self._certfile)

                    self._conn.settimeout(timeout/1000.0)
                    #log.debug('connect %s', serv['addr'])
                    self._addr = serv['addr']
                    self._conn.connect(serv['addr'])
                    if 'timeout' in serv:
                        self._conn.settimeout(serv['timeout'])
                elif self._proto == 'udp':
                    self._conn = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    self._conn.settimeout(timeout/1000.0)
                else:
                    raise RPCError('protocol error')
            except Exception as e:
                log.error(traceback.format_exc())
                self._server['valid'] = False
                ret = -1
                self._conn.close()
                self._conn = None
                continue
            finally:
                if self._proto == 'tcp':
                    log.info('server=rpc|func=connect|addr=%s:%d|time=%d|ret=%d', 
                        serv['addr'][0], serv['addr'][1], (time.time()-t)*1000000, ret)

            break


    def _restore(self):
        invalid = self._server_sel.not_valid()
        log.debug('restore invalid server:%s', invalid)
        for server in invalid:
            conn = None
            try:
                log.debug('try restore %s', server['server']['addr'])
                addr = server['server']['addr']

                conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                conn.setsockopt(socket.SOL_TCP, socket.TCP_NODELAY, 1)
                if self._keyfile:
                    conn = ssl.wrap_socket(conn, keyfile=self._keyfile, certfile=self._certfile)
                conn.settimeout(1)
                conn.connect(addr)
            except:
                log.error(traceback.format_exc())
                log.debug("restore fail: %s", server['server']['addr'])
                continue
            finally:
                if conn:
                    conn.close()
            log.debug('restore ok %s', server['server']['addr'])
            server['valid'] = True


    def _call(self, name, args):
        #log.debug('call name:%s args:%s', name, args)
        t = time.time()
        retcode = -1
        addr = None
        try:
            p = ReqProto()
            p.name = name
            p.params = args
            p.msgid = self._seqid
            self._seqid += 1
            s = p.dumps()

            #log.debug('send:%s', s[8:])

            if self._proto == 'tcp':
                addr = self._addr
                log.debug('send:%s', s)
                self._conn.sendall(s)
                data = self._recvall()
                log.debug('recv:%s', data)
            else:
                addr = self._server['server']['addr']
                log.debug('send:%s', s)
                #self._conn.sendall(s)
                self._conn.sendto(s, addr)
                data, newaddr = self._conn.recvfrom(1000)
                log.debug('recv:%s', data)
                if not data:
                    return ERR, 'no data'
                data = data[8:]

            #log.debug('recv:%s', data)

            p2 = RespProto.loads(data)
            if p2.msgid != p.msgid:
                raise RPCError('seqid error: %d,%d' % (p.msgid, p2.msgid))
            retcode = p2.retcode
            return p2.retcode, p2.result
        except:
            raise
        finally:
            log.info('server=rpc|remote=%s:%d|func=%s|msgid=%d|args=%s|time=%d|ret=%d', 
                addr[0], addr[1], name, p.msgid, args, (time.time()-t)*1000000, retcode)

    def _recvall(self):
        head = self._conn.recv(8)
        if not head:
            raise RPCError('connection closed')
        bodylen = int(head.decode('utf-8'))
        #log.debug('recv head:%s %d', repr(head), bodylen)
        return recvall(self._conn, bodylen)


    def __getattr__(self, name):
        def _(**kwargs):
            return self._call(name, kwargs)
        return _


def test_server():
    global log
    log = logger.install('stdout')
    class MyHandler (Handler):
        def ping(self, name):
            log.debug('ping ' + name)
            return 0, 'ping '+name

    gevent_server(7000, MyHandler, proto='tcp,udp')


def test_client():
    global log
    log = logger.install('stdout')

    addr = {'addr':('127.0.0.1', 7000), 'timeout':1000}
    p = RPCClient(addr, proto='tcp')
    p.ping(name='nana')

def test_client_perf():
    global log
    log = logger.install('stdout')

    addr = {'addr':('127.0.0.1', 7000), 'timeout':1000}
    p = RPCClient(addr, proto='udp')
    n = 1000
    start = time.time()
    for i in range(0, n):
        p.ping('nana')
    end = time.time()

    print('n:', n, 'avg:', int(((end-start)/n)*1000000))


def test():
    f = globals()[sys.argv[1]]
    f()
 
if __name__ == '__main__':
    test()



