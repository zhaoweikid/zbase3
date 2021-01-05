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
    request: [version, type, msgid, name, params]
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





def test():
    f = globals()[sys.argv[1]]
    #print(len(sys.argv))
    if len(sys.argv) == 3:
        f(int(sys.argv[2])) # port
    else:
        f()

if __name__ == '__main__':
    test()



