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
import ssl
import logging
import json
from gevent.server import StreamServer
from defines import *

'''
package format:
    | package len(8B hex) | json |

json:
    request: [verion, options, msgid, name, params]
    response: [version, options, msgid, code, result]

options:
    for extension

'''

log = logging.getLogger()

VERSION = '1'


def _json_default_trans(obj):
    '''json对处理不了的格式的处理方法'''
    if isinstance(obj, datetime.datetime):
        return obj.strftime('%Y-%m-%d %H:%M:%S')
    if isinstance(obj, datetime.date):
        return obj.strftime('%Y-%m-%d')
    raise TypeError('%r is not JSON serializable' % obj)


def install(handle, p='json'):
    global serial, server_handler
    server_handler = handle
    serial = __import__(p)
    if p == 'json':
        serial.dumps = partial(serial.dumps, default=_json_default_trans, separators=(',', ':'))

class Protocol (object):
    def __init__(self, body=''):
        global VERSION
        self.body = body

        self.version = VERSION
        self.msgid = 0
        self.name  = ''
        self.params = []
        self.options = ''

        # for response
        self.retcode = None
        self.result = None

        if body:
            self.loads(body)

    def loads(self, body):
        self.version, self.options, self.msgid, self.name, self.params = serial.loads(body)
        
        if isinstance(self.name, int): #response
            self.retcode = self.name
            self.result = self.params

            self.name = ''
            self.params = []

    def dumps(self, head=True):
        if self.msgid == 0:
            self.msgid = random.randint(1, 100000000)
        if self.retcode is None:
            obj = [self.version, self.options, self.msgid, self.name, self.params]
        else:
            obj = [self.version, self.options, self.msgid, self.retcode, self.result]
        s = serial.dumps(obj)
        if head:
            return self.dumphead(len(s)) + s
        return s


    def dumphead(self, length):
        lenstr = hex(length)[2:]
        return  '0'*(8-lenstr) + lenstr



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


class ServerHandler:
    def __init__(self, server, sock, addr):
        self.server = server
        self.sock = sock
        self.addr = addr

    def run(self):
        while True:
            try:
                headstr = sock.recv(8)
                if not headstr:
                    break
                bodylen = int(headstr, 16)
                #log.debug('head len:%d', bodylen)
                data = recvall(sock, bodylen)
                p = Protocol(data)
                p2 = Protocol()
                p2.msgid = p.msgid
     
                start = time.time()
                f = getattr(self.handler, p.name, None)
                if not f:
                    p2.retcode = ERR_METHOD
                    p2.result = "not found method " + p.name
                    sock.sendall(p2.dumps())
                    continue
               
                try:
                    if isinstance(p.params, dict):
                        retcode,result = f(**p.params)
                    else:
                        retcode,result = f(*p.params)

                    p2.retcode = retcode
                    p2.result  = result
                except Exception as e:
                    p2.retcode = RET_EXCEPT
                    p2.result  = str(e)
                end = time.time()
                log.info('func=%s|id=%d|time=%d|params=%s|code=%d|ret=%s', p.name, p.msgid, int((end-start)*1000000), p2.retcode, p2.result)

                sock.sendall(p2.dumps())
            except:
                log.info(traceback.format_exc())
                sock.close()
                break

def gevent_server(port, handler):
    ServerHandler.handler = handler
    srv = StreamServer(('0.0.0.0', port), ServerHandler)
    log.info('server started at:%d', port)
    srv.serve_forever()
    log.warn("stopped")




class RPCError (Exception):
    pass


class RPCClient:
    def __init__(self, addr, timeout=0, keyfile=None, certfile=None):
        self._addr = addr
        self._seqid = random.randint(0, 1000000)
        self._conn = None
        self._timeout = timeout # 毫秒
        self._keyfile = keyfile
        self._certfile = certfile

    def _connect(self):
        log.debug('connect to %s', self._addr)
        self._conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._conn.setsockopt(socket.SOL_TCP, socket.TCP_NODELAY, 1)

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
            prot = Protocol()
            prot.name = name
            prot.params = args
            prot.msgid = self._seqid
            self._seqid += 1

            s = prot.dumps()
            log.debug('send:%s', repr(s))

            if not self._conn:
                self._connect()

            self._conn.sendall(s)
            data = self._recv()

            log.debug('recv:%s', repr(data))
            prot2 = Protocol()
            prot2.loads(data)
            if prot2.seqid != prot.seqid:
                raise RPCError('seqid error: %d,%d' % (prot.seqid, prot2.seqid))
            return prot2.retcode, prot2.result
        except:
            raise
        finally:
            log.info('server=rpc|func=%s|time=%d|ret=%d', name, (time.time()-t)*1000000, retcode)

    def _recv(self):
        head = self._conn.recv(8)
        if not head:
            raise RPCError, 'connection closed'
        bodylen = int(head, 16)
        log.debug('recv head:%s %d', repr(head), bodylen)
        return recvall(self._conn, bodylen)


    def __getattr__(self, name):
        def _(*args):
            return self._call(name, args)
        return _



def test_server():
    gevent_server(8080)


