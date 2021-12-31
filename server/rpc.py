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

'''
package format:
    | package len(8B) | json 

json:
    request: [version, type, msgid, logid, name, params, extend]
    response: [version, type, msgid, logid, code, result, extend]

    extend 为可选字段，不是必须
'''

log = logging.getLogger()

# 版本
VERSION = 1

# 调用
TYPE_CALL  = 100
# 调用，不需要返回结果。调用方不等待
TYPE_CALL_NOREPLY = 101
# 应答
TYPE_REPLY = 200
# 应答，处理有异常
TYPE_REPLY_EXCEPT = 201

class ProtocolError(Exception):
    pass

class Protocol (object):
    def __init__(self):
        global VERSION
        self.version = VERSION
        self.msgid = 0
        self.msgtype = 0
        self.logid = ''
        self.extend = None

    def __str__(self):
        return '<Protocol version:%d msgtype:%d msgid:%d logid:%s>' % \
            (self.version, self.msgtype, self.msgid, self.logid)

class ReqProto (Protocol):
    def __init__(self, logid='', extend=None):
        Protocol.__init__(self)
        
        self.name  = ''
        self.params = []
        self.options = ''
        self.msgtype = TYPE_CALL
        self.extend = extend

        if not logid:
            self.logid = 'L%x'% random.randint(1000, 100000000)
        else:
            self.logid = logid

        if self.msgid == 0:
            self.msgid = random.randint(1, 100000000)

        #log.debug('req logid:%s', self.logid)

    def __str__(self):
        return '<ReqProto ver:%d msgid:%d logid:%s name:%s param:%s extend:%s>' % \
            (self.version, self.msgid, self.logid, self.name, self.params, self.extend)

    def call(self, name, params=None):
        self.name = name
        if params:
            self.params = params
        else:
            self.params = {}

    @staticmethod
    def loads(body):
        if isinstance(body, bytes):
            body = body.decode('utf-8')
        #log.debug('load:%s', body)
        p = ReqProto()
        obj = json.loads(body)
        if len(obj) == 6:
            p.version, p.msgtype, p.msgid, p.logid, p.name, p.params = obj
        elif len(obj) == 7:
            p.version, p.msgtype, p.msgid, p.logid, p.name, p.params, p.extend = obj
        else:
            raise ProtocolError('request error: {}'.format(body))

        return p

        
    def dumps(self, head=True):
        obj = [self.version, self.msgtype, self.msgid, str(self.logid), self.name, self.params]
        if self.extend:
            obj.append(self.extend)
        s = json.dumps(obj)
        if head:
            s = '%08d' % (len(s)) + s
        return s.encode('utf-8')


class RespProto (Protocol):
    def __init__(self, msgid, logid=''):
        Protocol.__init__(self)

        self.msgid   = msgid
        self.logid   = logid
        self.retcode = None
        self.result  = None
        self.msgtype = TYPE_REPLY

    def __str__(self):
        return '<RespProto ver:%d msgid:%d logid:%s code:%s result:%s extend:%s>' % \
            (self.version, self.msgid, self.logid, str(self.retcode), str(self.result), self.extend)

    def reply(self, code=0, result=None):
        self.retcode = code
        self.result = result

    @staticmethod
    def loads(body):
        if isinstance(body, bytes):
            body = body.decode('utf-8')

        p = RespProto(0)
        obj = json.loads(body)
        if len(obj) == 6:
            p.version, p.msgtype, p.msgid, p.logid, p.retcode, p.result = obj
        elif len(obj) == 7:
            p.version, p.msgtype, p.msgid, p.logid, p.retcode, p.result, p.extend = obj
        else:
            raise ProtocolError('response error: {}'.format(body))
        return p

    @staticmethod
    def fromReq(req):
        p = RespProto(req.msgid, req.logid)
        return p
       
    def dumps(self, head=True):
        if self.msgid == 0:
            self.msgid = random.randint(1, 100000000)
        obj = [self.version, self.msgtype, self.msgid, str(self.logid), self.retcode, self.result]
        if self.extend:
            obj.append(self.extend)
        s = json.dumps(obj)
        if head:
            s = '%08d' % (len(s)) + s
        return s.encode('utf-8')


def test_proto():
    req = ReqProto()
    req.call('ping', 10)
    print(req)
    p = req.dumps()
    print(p)

    req2 = ReqProto.loads(p[8:])
    print(req2.dumps())

    resp = RespProto.fromReq(req)
    resp.reply(0, 'haha')
    print(resp)
    p = resp.dumps()
    print(p)

    resp2 = RespProto.loads(p[8:])
    print(resp2.dumps())

def test():
    f = globals()[sys.argv[1]]
    #print(len(sys.argv))
    if len(sys.argv) == 3:
        f(int(sys.argv[2]))
    else:
        f()

if __name__ == '__main__':
    test()



