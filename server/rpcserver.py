# coding: utf-8
#if __name__ == '__main__':
#    from gevent import monkey; monkey.patch_all()
import os, sys
import struct
import time, random
import datetime
import traceback
import socket
import ssl
import logging
import json
import gevent
from gevent.server import StreamServer, DatagramServer
from zbase3.server import balance
from zbase3.server.defines import *
from zbase3.base import logger
from zbase3.server.rpc import *

log = logging.getLogger()


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


class TCPServerHandler:
    def __init__(self, handlercls):
        self._handlercls = handlercls
        self.reqs = 0
        self.max_req = 0

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
            if self.max_req > 0 and self.reqs > self.max_req:
                log.warn('request max, quit %d>%d', self.reqs, self.max_req)
                if hasattr(self, 'stop'):
                    self.stop()
                #os._exit(0)
                break

            headstr = read_data(8)
            #log.debug('read head:%s', headstr)
            if not headstr:
                log.debug('client conn close, break')
                break
            bodylen = int(headstr)
            data = read_data(bodylen)
            #log.debug('read body:%s', data)
            if not data or len(data) != bodylen:
                log.info('read rpc body error, body=%d read=%d', bodylen, len(data))
                break
            self.reqs += 1
            
            p1 = ReqProto.loads(data)
            p2 = RespProto(p1.msgid)
            p2.msgtype = TYPE_REPLY
 
            start = time.time()
            try:
                log.debug('call %s %s reqs:%d', p1.name, p1.params, self.reqs)
                handler = self._handlercls(addr)
                if hasattr(handler, "_initial"):
                    handler._initial()
                f = getattr(handler, p1.name, None)
                if not f:
                    log.warn('not found method: '+p1.name)
                    p2.msgtype = TYPE_REPLY_EXCEPT
                    p2.retcode = ERR_METHOD
                    p2.result = "error, not found method " + p1.name
                else:
                    if isinstance(p1.params, dict):
                        p2.retcode,p2.result = f(**p1.params)
                    else:
                        p2.retcode,p2.result = f(*p1.params)
                if hasattr(handler, "_finish"):
                    handler._finish()

            except Exception as e:
                p2.msgtype = TYPE_REPLY_EXCEPT
                p2.retcode = ERR_EXCEPT
                p2.result  = str(e)
                log.info(traceback.format_exc())
            finally:
                if p1.msgtype != TYPE_CALL_NOREPLY:
                    write_data(p2.dumps())
                end = time.time()
                log.info('f=%s|remote=%s:%d|id=%d|t=%d|arg=%s|mt=%d|ret=%d|data=%s', 
                    p1.name, addr[0], addr[1], p1.msgid, int((end-start)*1000000), 
                    p1.params, p2.msgtype, p2.retcode, p2.result)


class TCPServer (StreamServer, TCPServerHandler):
    def __init__(self, addr, handlercls, spawn='default'):
        StreamServer.__init__(self, addr, spawn=spawn)
        TCPServerHandler.__init__(self, handlercls)



class UDPServerHandler:
    def __init__(self, handlecls):
        self._handlecls = handlecls
        self.reqs = 0
        self.max_req = 0

    def handle(self, data, address):
        if self.max_req > 0 and self.reqs > self.max_req:
            log.warn('request max, quit %d>%d', self.reqs, self.max_req)
            if hasattr(self, 'stop'):
                self.stop()
            else:
                os._exit(0)
            return

        self.reqs += 1

        start = time.time()
        try:
            p1 = ReqProto.loads(data[8:])
            p2 = RespProto(p1.msgid)

            obj = self._handlecls(address)
            if hasattr(obj, "_initial"):
                obj._initial()

            f = getattr(obj, p1.name, None)
            if not f:
                log.warn('not found method '+p1.name)
                p2.msgtype = TYPE_REPLY_EXCEPT
                p2.retcode = ERR_METHOD
                p2.result = "not found method " + p1.name
                if p1.msgtype != TYPE_CALL_NOREPLY:
                    self.socket.sendto(p2.dumps(), address)
                return

            if isinstance(p1.params, dict):
                p2.retcode,p2.result = f(**p1.params)
            else:
                p2.retcode,p2.result = f(*p1.params)

            if hasattr(obj, "_finish"):
                obj._finish()
            if p1.msgtype != TYPE_CALL_NOREPLY:
                self.socket.sendto(p2.dumps(), address)
        except Exception as e:
            log.warn(traceback.format_exc())
            p2.msgtype = TYPE_REPLY_EXCEPT
            p2.retcode = ERR_EXCEPT
            p2.result  = str(e)
            if p1.msgtype != TYPE_CALL_NOREPLY:
                self.socket.sendto(p2.dumps(), address)
        finally:
            end = time.time()
            log.info('f=%s|remote=%s:%d|id=%d|t=%d|arg=%s|mt=%d|ret=%d|data=%s', 
                p1.name, address[0], address[1], p1.msgid, int((end-start)*1000000), 
                p1.params, p2.msgtype, p2.retcode, p2.result)

class UDPServer (DatagramServer, UDPServerHandler):
    def __init__(self, addr, handlercls):
        DatagramServer.__init__(self, addr)
        UDPServerHandler.__init__(self, handlercls)


class BaseHandler:
    def __init__(self, addr):
        self.addr = addr


class Server:
    def __init__(self, port, handlercls, proto='tcp'):
        self.port = port
        self.handlercls = handlercls
        self.proto = proto
        self.server = []

        server_map = {
            'tcp': TCPServer, 
            'udp': UDPServer,
        }
        ps = proto.split(',')
        if len(ps) == 2:
            for p in ps:
                self.server.append(server_map[p](('0.0.0.0', port), self.handlercls))
                log.info('%s server started at:%d', p, port)
        else: 
            self.server.append(server_map[ps[0]](('0.0.0.0', port), self.handlercls))
            log.warn('server started at:%d', port)

    def start(self):
        if len(self.server) == 2:
            gevent.spawn(self.server[0].serve_forever)
            self.server[1].serve_forever()
            log.warn("server stopped")
        else:
            self.server[0].serve_forever()
            log.warn("server stopped")

      

class RPCError (Exception):
    pass

class RPCConnError (Exception):
    pass

class RPCConnection:
    def __init__(self, addr, timeout=1000, keyfile=None, certfile=None):
        self.addr = addr
        self.timeout = timeout
        self.keyfile = keyfile
        self.certfile = certfile

        self.conn = None

        self.connect()


    def __del__(self):
        self.close()

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    def check_connection(self):
        if not self.conn:
            self.connect()

    def connect(self):
        t = time.time()
        ret = 0
        msg = ''
        try:
            self.conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.conn.setsockopt(socket.SOL_TCP, socket.TCP_NODELAY, 1)
            if self.keyfile:
                self.conn = ssl.wrap_socket(self.conn, keyfile=self.keyfile, certfile=self.certfile)

            if self.timeout:
                self.conn.settimeout(self.timeout/1000.0)
            log.debug('connect to %s', self.addr)
            self.conn.connect(self.addr)
        except Exception as e:
            log.error(traceback.format_exc())
            self.close()
            ret = -1
            msg = str(e)
            raise
        finally:
            log.info('server=rpc|f=connect|addr=%s:%d|t=%d|ret=%d|msg=%s', 
                    self.addr[0], self.addr[1], (time.time()-t)*1000000, ret, msg)


    def peek(self):
        return self.conn.recv(1, socket.MSG_PEEK)

    def recvall(self):
        head = self.conn.recv(8)
        if not head:
            raise RPCConnError('connection closed')
        bodylen = int(head.decode('utf-8'))
        #log.debug('recv head:%s %d', repr(head), bodylen)
        s = recvall(self.conn, bodylen)
        log.debug('recv:%s', s)
        return s

    def sendall(self, s):
        log.debug('send:%s', s[8:])
        return self.conn.sendall(s)


class RPCClientBase:
    def __init__(self, server):
        self._c = None
        self._seqid = random.randint(0, 100000)

        self._server = server
        self._serverlist = None

        if isinstance(server, dict): # 只有一个server
            self._serverlist = balance.ServerList([server,], 'random')
        elif isinstance(server, list) or isinstance(server, tuple):
            self._serverlist = balance.ServerList(server, 'random')
        else: # 直接是ServerList
            self._serverlist = server

    def _close(self):
        if self._c:
            log.info('close conn')
            self._c.close()
            self._c = None

    def __del__(self):
        self._close()

    def select_server(self):
        self._server = self._serverlist.next()
        if not self._server:
            self._check_restore()
            self._server = self._serverlist.next()
            if not self._server:
                raise RPCError('no server')

        return self._server

    def _check_restore(self):
        pass

class RPCClientTCP (RPCClientBase):
    def __init__(self, server, keyfile=None, certfile=None):
        RPCClientBase.__init__(self, server)

        self._keyfile = keyfile
        self._certfile = certfile
        self._last_time = 0

        self._connect()


    def _connect(self):
        while True:
            serv = self.select_server()
           
            timeout = 100
            if 'conn_timeout' in serv:
                timeout = int(serv.get('conn_timeout'))
            elif 'timeout' in serv:
                timeout = int(serv.get('timeout'))
           
            try:
                self._c = RPCConnection(serv['addr'], timeout, self._keyfile, self._certfile)
            except socket.error:
                log.error('connect error: ' + traceback.format_exc())
                self._serverlist.fail(serv)
                if self._c:
                    self._c.close()
                continue
            except Exception as e:
                log.error(traceback.format_exc())
            break


    def _check_restore(self):
        fails = self._serverlist.get_fails()
        log.debug('restore invalid server:%s', fails)
        for server in fails:
            addr = server['addr']
            c = None
            try:
                log.debug('try restore %s', addr)
                c = RPCConnection(addr, 10, self._keyfile, self._certfile)
            except:
                log.error('restore except: ' + traceback.format_exc())
                log.debug("restore fail: %s", addr)
                continue
            finally:
                if c:
                    c.close()
            log.info('restore ok %s', addr)
            self._serverlist.restore(server)


    def _call(self, name, args, kwargs):
        log.debug('call %s %s %s', name, args, kwargs)
        t1 = time.time()
        retcode = -1
        try:
            p = ReqProto()
            p.name = name
            if args:
                p.params = args
            else:
                p.params = kwargs
            p.msgid = self._seqid
            self._seqid += 1
            s = p.dumps()

            for i in (1,2):
                try:
                    self._c.check_connection()
                    self._c.sendall(s) 
                    data = self._c.recvall()
                    break
                except (socket.error, RPCConnError):
                    if i != 2:
                        log.info('socket error: ' + traceback.format_exc() + '\n, retry...')
                    self._c.close()
                    if i == 2:
                        raise
                    continue 
                except:
                    raise

            p2 = RespProto.loads(data)
            if p2.msgid != p.msgid:
                raise RPCError('seqid error: %d,%d' % (p.msgid, p2.msgid))
            retcode = p2.retcode
            return p2.retcode, p2.result
        except:
            log.info('raise:' + traceback.format_exc())
            raise
        finally:
            t2 = time.time()
            self._last_time = t2
            log.info('server=rpc|remote=%s:%d|f=%s|id=%d|arg=%s|t=%d|ret=%d', 
                self._c.addr[0], self._c.addr[1], name, p.msgid, p.params, (t2-t1)*1000000, retcode)


    def __getattr__(self, name):
        def _(*args, **kwargs):
            return self._call(name, args, kwargs)
        return _

RPCClient = RPCClientTCP

class RPCClientUDP (RPCClientBase):
    def __init__(self, server):
        RPCClientBase.__init__(self, server)

        self._addr = None
        self._timeout = 1000 # 毫秒

        self._conn = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def set_timeout(self, addr):
        if 'conn_timeout' in addr:
            self._timeout = int(addr.get('conn_timeout'))
        elif 'timeout' in addr:
            self._timeout = int(addr.get('timeout'))
        self._conn.settimeout(self._timeout/1000.0)

    def _call(self, name, args, kwargs):
        #log.debug('call name:%s args:%s', name, args)
        t1 = time.time()
        retcode = -1
        addr = None
        try:
            p = ReqProto()
            p.name = name
            if args:
                p.params = args
            else:
                p.params = kwargs

            p.msgid = self._seqid
            self._seqid += 1
            s = p.dumps()

            addr = self._server['addr']
            self.set_timeout(addr)
            log.debug('send:%s', s)
            self._conn.sendto(s, addr)
            data, newaddr = self._conn.recvfrom(1000)
            log.debug('recv:%s', data)
            if not data:
                return ERR, 'no data'
            data = data[8:]

            p2 = RespProto.loads(data)
            if p2.msgid != p.msgid:
                raise RPCError('seqid error: %d,%d' % (p.msgid, p2.msgid))
            retcode = p2.retcode
            return p2.retcode, p2.result
        except:
            log.info(traceback.format_exc())
            raise
        finally:
            t2 = time.time()
            log.info('server=rpc|remote=%s:%d|f=%s|id=%d|arg=%s|t=%d|ret=%d', 
                addr[0], addr[1], name, p.msgid, p.params, (t2-t1)*1000000, retcode)

    def _check_restore(self):
        fails = self._serverlist.get_fails()
        log.debug('restore invalid server:%s', fails)
        c = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            for server in fails:
                addr = server['addr']
                c = None
                try:
                    log.debug('try restore %s', addr)

                    p = ReqProto()
                    p.name = 'ping'
                    p.params = {}
                    p.msgid = random.randint(1,10000)
                    s = p.dumps()

                    c.sendto(s, addr)
                    ret = c.recvfrom(1000)
                    p2 = RespProto.loads(ret)
                    if p2.code != 0:
                        continue
                except:
                    log.error(traceback.format_exc())
                    log.debug("restore fail: %s", addr)
                    continue
                finally:
                    if c:
                        c.close()
                log.debug('restore ok %s', addr)
                self._serverlist.restore(server)
        finally:
            c.close()

    def __getattr__(self, name):
        def _(*args, **kwargs):
            return self._call(name, args, kwargs)
        return _


def test_server(port=7000):
    global log
    log = logger.install('stdout')
    class MyHandler (BaseHandler):
        def ping(self):
            log.debug('ping')
            return 0, 'pong'

    server = Server(port, MyHandler, proto='tcp,udp')
    server.start()

def test_client(port=7000):
    global log
    log = logger.install('stdout')

    addr = {'addr':('127.0.0.1', port), 'timeout':1000}
    p = RPCClient(addr)
    p.ping()
    p.interface()

def test_client_udp(port=7000):
    global log
    log = logger.install('stdout')

    addr = {'addr':('127.0.0.1', port), 'timeout':1000}
    p = RPCClientUDP(addr)
    p.ping()

def test_client_restore(port=7000):
    global log
    log = logger.install('stdout')

    addr = {'addr':('127.0.0.1', port), 'timeout':1000}
    p = RPCClient(addr)

    for i in range(0, 100):
        try:
            p.ping()
        except:
            log.info('ignore:'+traceback.format_exc())
        finally:
            time.sleep(2)

def test_client_perf(port=7000):
    global log
    log = logger.install('stdout')

    addr = {'addr':('127.0.0.1', port), 'timeout':1000}
    n = 1
    start = time.time()
    for i in range(0, n):
        try:
            p = RPCClient(addr)
            p.ping()
        except KeyboardInterrupt:
            os._exit(0)
        except:
            log.info(traceback.format_exc())
            #time.sleep(0.1)
    end = time.time()

    print('n:', n, 'avg:', int(((end-start)/n)*1000000))

def test_client_perf_long(port=7000):
    global log
    log = logger.install('stdout')

    addr = {'addr':('127.0.0.1', port), 'timeout':1000}
    p = RPCClient(addr)
    n = 12
    start = time.time()
    for i in range(0, n):
        p.ping()
    end = time.time()

    print('n:', n, 'avg:', int(((end-start)/n)*1000000))


def test():
    f = globals()[sys.argv[1]]
    #print(len(sys.argv))
    if len(sys.argv) == 3:
        f(int(sys.argv[2])) # port
    else:
        f()

def test2(n=1000000):
    for i in range(n):
        test_client_perf(7200)
        #test_client_perf_long(7200)
        #time.sleep(.1)
 
if __name__ == '__main__':
    test()



