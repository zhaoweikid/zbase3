# coding: utf-8
if __name__ == '__main__':
    from gevent import monkey; monkey.patch_all()
import os, sys
import struct
import time, random
import datetime
import traceback
import socket
import ssl
import logging
import json
import requests
import gevent
from zbase3.server import balance
from zbase3.server.defines import *
from zbase3.base import logger
from zbase3.server.rpc import *
from zbase3.server.rpcserver import recvall
from zbase3.server import nameclient

log = logging.getLogger()


class RPCError (Exception):
    pass

class RPCConnError (Exception):
    pass

class TcpConnection:
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

        self._timeout = 1000 # 毫秒

        self._server_name = ''
        self._nc = None
        self._server = None
        self._serverlist = None

        self._addr = None

        if isinstance(server, dict): # 只有一个server
            self._serverlist = balance.ServerList([server,], 'random')
        elif isinstance(server, list) or isinstance(server, tuple):
            self._serverlist = balance.ServerList(server, 'random')
        elif isinstance(server, str): # namecenter
            self._server_name = server
            self._nc = NameClient()
            realserver = self._nc.query(server)
            if not realserver:
                raise ValueError('namecenter query error with %s: %s' % (server, realserver))
            self._serverlist = balance.ServerList(realserver, 'random')
        else: # 直接是ServerList
            self._serverlist = server


    def _set_timeout(self, addr):
        if 'conn_timeout' in addr:
            self._timeout = int(addr.get('conn_timeout'))
        elif 'timeout' in addr:
            self._timeout = int(addr.get('timeout'))

    def _close(self):
        if self._c:
            log.info('close conn')
            self._c.close()
            self._c = None

    def __del__(self):
        self._close()

    def _select_server(self):
        if self._server_name:
            realserver = self.nc.query(server)
            if not realserver:
                raise ValueError('namecenter query error with %s: %s' % (server, realserver))
            self._serverlist = balance.ServerList(realserver, 'random')

        self._server = self._serverlist.next()
        if not self._server:
            self._check_restore()
            self._server = self._serverlist.next()
            if not self._server:
                raise RPCError('no server')

        return self._server

    def _check_restore(self):
        fails = self._serverlist.get_fails()
        log.debug('restore invalid server:%s', fails)
        for server in fails:
            addr = server['addr']
            try:
                log.debug('try restore %s', addr)

                p = ReqProto()
                p.name = 'ping'
                p.params = {}
                p.msgid = random.randint(1,10000)
                s = p.dumps()
                
                ret = self._restore_send_recv(addr, s)

                p2 = RespProto.loads(ret)
                if p2.code != 0:
                    continue
            except:
                log.error(traceback.format_exc())
                log.debug("restore fail: %s", addr)
                continue
            log.debug('restore ok %s', addr)
            self._serverlist.restore(server)

    def _restore_send_recv(self, addr, s):
        return 'data'

    def _send_recv(self, s):
        return 'addr', 'data'

    def _call(self, name, args, kwargs):
        log.debug('call %s %s %s', name, args, kwargs)
        t1 = time.time()
        retcode = -1
        addr = ('', 0)
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
                    addr, data = self._send_recv(s)
                    break
                except socket.error as e:
                    if i == 1:
                        log.info('socket error: ' + traceback.format_exc() + '\n, retry...')
                        self._c.close()
                        continue 
                    else:
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
                addr[0], addr[1], name, p.msgid, p.params, (t2-t1)*1000000, retcode)

    def __getattr__(self, name):
        def _(*args, **kwargs):
            return self._call(name, args, kwargs)
        return _



class TCPClient (RPCClientBase):
    def __init__(self, server, keyfile=None, certfile=None):
        RPCClientBase.__init__(self, server)

        self._keyfile = keyfile
        self._certfile = certfile
        self._last_time = 0

        self._connect()

    def _connect(self):
        while True:
            serv = self._select_server()
           
            self._set_timeout(serv)
            try:
                self._c = TcpConnection(serv['addr'], self._timeout, self._keyfile, self._certfile)
            except socket.error:
                log.error('connect error: ' + traceback.format_exc())
                self._serverlist.fail(serv)
                if self._c:
                    self._c.close()
                continue
            except Exception as e:
                log.error(traceback.format_exc())
            break

    def _send_recv(self, s):
        self._c.check_connection()
        self._c.sendall(s) 
        return self._c.addr, self._c.recvall()

    def _restore_send_recv(self, addr, s):
        c = None
        try:
            c = TcpConnection(addr, 500, self._keyfile, self._certfile)
            c.sendall(s)
            return c.recvall()
        except:
            if c:
                c.close()
            raise



class UDPClient (RPCClientBase):
    def __init__(self, server):
        RPCClientBase.__init__(self, server)
        self._c = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def _send_recv(self, s):
        addr = self._server['addr']
        self._set_timeout(addr)
        self._c.settimeout(self._timeout/1000)
        log.debug('send:%s', s)
        self._c.sendto(s, addr)
        data, newaddr = self._c.recvfrom(1000)
        return newaddr, data[8:]

    def _restore_send_recv(self, addr, s):
        c = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        c.settimeout(0.5)
        try:
            c.sendto(s, addr)
            return c.recvfrom(1000)
        finally:
            c.close()



class HTTPClient (RPCClientBase):
    def __init__(self, server):
        RPCClientBase.__init__(self, server)

    def _send_recv(self, s):
        server = self._select_server()
        addr = server['addr']
        log.debug('addr:%s', addr)
        url = 'http://%s:%d/' % addr
        resp = requests.post(url, data=s[8:])
        log.debug('resp:%s', resp.content)
        if resp.status_code < 300:
            return addr, resp.content 
        raise ValueError('request error! code:%d' % resp.status_code)

    def _restore_send_recv(self, addr, s):
        url = 'http://%s:%d/' % addr
        resp = requests.post(url, data=s[8:])
        if resp.status_code < 300:
            return resp.content 
        raise ValueError('request error! code:%d' % resp.status_code)


def Client(addr, proto='tcp'):
    if proto == 'udp':
        return UDPClient(addr)
    elif proto == 'http':
        return HTTPClient(addr)
    else:
        return TCPClient(addr)

def test_client(port=7000):
    global log
    log = logger.install('stdout')

    addr = {'addr':('127.0.0.1', port), 'timeout':1000}
    p = Client(addr)
    p.ping()
    p.interface()

def test_client_udp(port=7000):
    global log
    log = logger.install('stdout')

    addr = {'addr':('127.0.0.1', port), 'timeout':1000}
    p = UDPClient(addr)
    p.ping()


def test_client_http(port=7000):
    global log
    log = logger.install('stdout')

    addr = {'addr':('127.0.0.1', port), 'timeout':1000}
    p = HTTPClient(addr)
    p.ping()



def test_client_restore(port=7000):
    global log
    log = logger.install('stdout')

    addr = {'addr':('127.0.0.1', port), 'timeout':1000}
    p = Client(addr)

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
            p = Client(addr)
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
    p = Client(addr)
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



