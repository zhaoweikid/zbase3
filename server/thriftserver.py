# coding: utf-8
if __name__ == '__main__':
    from gevent import monkey; monkey.patch_all()
import os
import sys
import traceback
import struct
import logging
import time
import socket
import signal
import functools
import thrift
import thrift.protocol

from thrift.Thrift import TException, TMessageType
from thrift.protocol import TBinaryProtocol
from thrift.transport import TTransport, TSocket
from thrift.server.TServer import TServer

import gevent
from gevent.server import StreamServer
from gevent.pool import Pool

from zbase3.server import baseserver
from zbase3.server.baseserver import BaseGeventServer


log = logging.getLogger()

class SocketTransport (TTransport.TTransportBase):
    def __init__(self, obj):
        self.socket = obj

    def isOpen(self):
        return True

    def close(self):
        self.socket.close()

    def read(self, sz):
        return self.socket.recv(sz)

    def write(self, buf):
        self.socket.sendall(buf)

    def flush(self):
        pass


class ThriftHandler:
    def __init__(self, module, handlercls, framed=True):
        self.module = module 
        self.handler = handlercls()
        self.framed = framed

    def handle(self, client, addr):
        fd = client.fileno()
        log.info('func=open|client=%s:%d', addr[0], addr[1])
        if not self.module:
            raise TException('thrift module not initial')

        def read_frame(trans):
            frame_header = trans.readAll(4)
            sz, = struct.unpack('!i', frame_header)
            if sz < 0:
                raise TException('client must use TFramedTransport')
            frame_data = trans.readAll(sz)
            return frame_data

        def unpack_name(s):
            sz, = struct.unpack('!i', s[4:8])
            return s[8:8+sz]

        tstart = time.time()
        trans = TSocket.TSocket(addr[0], addr[1])
        trans.setHandle(client)
        try:
            #frame_data = read_frame(trans)
            #log.debug('data:%s %s', repr(frame_data), unpack_name(frame_data))
            #itran = TTransport.TMemoryBuffer(frame_data)

            if self.framed:
                itran = TTransport.TFramedTransport(trans)
                otran = TTransport.TFramedTransport(trans)
            else:
                itran = TTransport.TBufferedTransport(trans)
                otran = TTransport.TBufferedTransport(trans)
            iprot = TBinaryProtocol.TBinaryProtocol(itran, False, True)
            oprot = TBinaryProtocol.TBinaryProtocol(otran, False, True)

            self.handler.remote = addr
            p = self.module.Processor(self.handler)
            while True:
                p.process(iprot, oprot)
                #log.info('func=call|name=%s|time=%d', unpack_name(frame_data), (time.time()-tstart)*1000000)

            #itran.close()
            #otran.close()
        except TTransport.TTransportException as tx:
            if tx.type == TTransport.TTransportException.END_OF_FILE:
                pass
            else:
                log.error(traceback.format_exc())
        except EOFError:
            #log.error(traceback.format_exc())
            #log.info('func=close|time=%d', addr[0], addr[1], (timt.time()-tstart)*1000)
            pass
        except Exception as e:
            log.error(traceback.format_exc())
        finally:
            log.info('func=close|time=%d', (time.time()-tstart)*1000000)
            client.close()



class TCPThriftServer (StreamServer, ThriftHandler):
    def __init__(self, addr, module, handlercls, framed, spawn):
        StreamServer.__init__(self, addr, spawn=spawn)
        ThriftHandler.__init__(self, module, handlercls, framed=framed)

class ThriftServer (BaseGeventServer):
    def __init__(self, addr, module, handler_class, framed=True, max_proc=1, max_conn=1000, max_req=0):
        self.module = module
        self.framed = framed
        
        BaseGeventServer.__init__(self, addr, handler_class, max_proc, max_conn, max_req)

    def make_server(self):
        return TCPThriftServer(self.addr, self.module, self.handlercls, self.framed, self.pool)
    
def test_gevent():
    from zbase3.base import logger
    logger.install('stdout')
    from thriftclient3.session import Session
    import gevent

    class TestHandler:
        def ping(self):
            log.debug('pong')
                 
    server = ThriftServer(('127.0.0.1', 10000), Session, TestHandler, max_proc=2)
    server.forever()


def test():
    f = globals()[sys.argv[1]]
    f()
 
if __name__ == '__main__':
    test()


