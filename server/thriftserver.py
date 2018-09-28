# coding: utf-8
import os
import sys
import traceback
import multiprocessing
import struct
import logging
import time
import socket
import signal
import thrift
import thrift.protocol

from thrift.Thrift import TException, TMessageType
from thrift.protocol import TBinaryProtocol
from thrift.transport import TTransport, TSocket
from thrift.server.TServer import TServer

import gevent
from gevent.server import StreamServer
from gevent.pool import Pool


log = logging.getLogger()
service = None

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



def handle(client, addr):
    fd = client.fileno()
    log.info('func=open|client=%s:%d', addr[0], addr[1])
    global service
    if not service:
        raise TException('service not initial')

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

        itran = TTransport.TFramedTransport(trans)
        otran = TTransport.TFramedTransport(trans)
        iprot = TBinaryProtocol.TBinaryProtocol(itran, False, True)
        oprot = TBinaryProtocol.TBinaryProtocol(otran, False, True)

        service.handler.remote = addr
        p = service.Processor(service.handler)
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




class ThriftServer:
    def __init__(self, module, handler_class, addr, max_process=1, max_conn=1000):
        module.handler = handler_class()
        global service
        service = module

        self.proc = None
        self.workers = []
        self.running = True

        pool = Pool(max_conn)

        self.server = StreamServer(addr, handle, spawn=pool)
        self.server.reuse_addr = 1
        self.server.start()

        def signal_master_handler(signum, frame):
            log.warn("signal %d catched in master %d, wait for kill all worker", signum, os.getpid())
            self.running = False
            for p in self.workers:
                p.terminate()
        
        def signal_worker_handler(signum, frame):
            log.warn("worker %d will exit after all request handled", os.getpid())
            self.server.close()

        def server_start():
            signal.signal(signal.SIGTERM, signal_worker_handler)
            log.warn('server started addr=%s:%d pid=%d', addr[0], addr[1], os.getpid())
            self.server.serve_forever()

        def _start_process(index):
            server_name = 'proc-%02d' % index
            p = multiprocessing.Process(target=server_start, name=server_name)
            p.start()
            return p
        
        def signal_child_handler(signum, frame):
            time.sleep(1)
            if self.running:
                log.warn("master recv worker exit, fork one")
                try:
                    pinfo = os.waitpid(-1, 0)
                    pid = pinfo[0]

                    index = -1
                    for i in range(0, len(self.workers)):
                        p = self.workers[i]
                        if p.pid == pid:
                            index = i
                            break
                   
                    if index >= 0:
                        self.workers[index] = _start_process(index)
                except OSError:
                    log.info('waitpid error:')


       
        if max_process == 1:
            signal.signal(signal.SIGTERM, signal_worker_handler)
            gevent.spawn(self.forever)
            server_start()
        else:
            for i in range(0, max_process):
                self.workers.append(_start_process(i))

            signal.signal(signal.SIGTERM, signal_master_handler)
            signal.signal(signal.SIGCHLD, signal_child_handler)

    def forever(self):
        try:
            while self.running:
                if len(self.workers) > 0:
                    time.sleep(60)
                else:
                    gevent.sleep(60)
                log.debug('report ...')
            log.warn('master exit')
        except Exception as e:
            log.warn('master exception: %s', str(e))
        finally:
            self.running = False
            time.sleep(3)
            for p in self.workers:
                p.terminate()

    def stop(self):
        pass




def test():
    pass

if __name__ == '__main__':
    test()


