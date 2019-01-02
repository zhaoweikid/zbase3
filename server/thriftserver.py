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



def handle(client, addr, framed=True):
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

        if framed:
            itran = TTransport.TFramedTransport(trans)
            otran = TTransport.TFramedTransport(trans)
        else:
            itran = TTransport.TBufferedTransport(trans)
            otran = TTransport.TBufferedTransport(trans)
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


class ThriftBaseServer (object):
    def __init__(self, module, handler_class, addr, max_process=1, max_conn=1000):
        pass

    def install(self):
        pass

    def forever(self):
        try:
            while self.running or len(self.workers) > 0:
                time.sleep(10)
        except Exception as e:
            log.warn('master exception: %s', str(e))
        finally:
            log.warn('master exit ...')
            self.running = False
            time.sleep(1)
            for p in self.workers:
                try:
                    p.terminate()
                except:
                    pass

            for p in self.workers:
                p.join()

        log.warn('master exited')


    def stop(self):
        self.running = False



class ThriftServer (ThriftBaseServer):
    def __init__(self, module, handler_class, addr, max_process=1, max_conn=1000):
        module.handler = handler_class()
        global service
        service = module
        self.addr = addr

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
       
        def signal_child_handler(signum, frame):
            time.sleep(1)

            log.warn("master recv worker exit")
            try:
                pinfo = os.waitpid(-1, 0)
                pid = pinfo[0]

                index = -1
                for i in range(0, len(self.workers)):
                    p = self.workers[i]
                    if p.pid == pid:
                        index = i
                        break
            except OSError:
                log.info('waitpid error:', traceback.format_exc())

            if self.running:
                log.warn("master fork one")
                if index >= 0:
                    self.workers[index] = _start_process(index)
            else:
                log.warn("master del worker %d", pid)
                if index >= 0:
                    self.workers.pop(index)

        def server_start():
            signal.signal(signal.SIGTERM, signal_worker_handler)
            log.warn('server started addr=%s:%d pid=%d', self.addr[0], self.addr[1], os.getpid())
            self.install()
            if hasattr(service.handler, '_initial'):
                service.handler._initial()
            self.server.serve_forever()

        def _start_process(index):
            server_name = 'proc-%02d' % index
            p = multiprocessing.Process(target=server_start, name=server_name)
            p.start()
            return p
     
       
        if max_process == 1:
            signal.signal(signal.SIGTERM, signal_worker_handler)
            #gevent.spawn(self.forever)
            server_start()
        else:
            for i in range(0, max_process):
                self.workers.append(_start_process(i))

            signal.signal(signal.SIGTERM, signal_master_handler)
            signal.signal(signal.SIGCHLD, signal_child_handler)



from zbase3.server.threadpool import ThreadPool, Task

class ThriftThreadServer (ThriftBaseServer):
    def __init__(self, module, handler_class, addr, max_process=1, max_conn=50, framed=True):
        module.handler = handler_class()
        global service
        service = module
        self.framed = framed
        self.addr = addr

        self.workers = []
        self.running = True

        def signal_master_handler(signum, frame):
            log.warn("signal %d catched in master %d, wait for kill all worker", signum, os.getpid())
            self.running = False
            for p in self.workers:
                p.terminate()
        
        def signal_worker_handler(signum, frame):
            log.warn("worker %d will exit after all request handled", os.getpid())
            self.running = False
            self.sock.close()

        def signal_child_handler(signum, frame):
            time.sleep(1)

            log.warn("master recv worker exit")
            try:
                pinfo = os.waitpid(-1, 0)
                pid = pinfo[0]

                index = -1
                for i in range(0, len(self.workers)):
                    p = self.workers[i]
                    if p.pid == pid:
                        index = i
                        break
            except OSError:
                log.info('waitpid error:', traceback.format_exc())
                return

            if self.running:
                log.warn("master fork one")
                if index >= 0:
                    self.workers[index] = _start_process(index)
            else:
                log.warn("master del worker %d", pid)
                if index >= 0:
                    self.workers.pop(index)

        def server_start():
            signal.signal(signal.SIGTERM, signal_worker_handler)
            log.warn('server started addr=%s:%d pid=%d', self.addr[0], self.addr[1], os.getpid())
            if hasattr(service.handler, '_initial'):
                service.handler._initial()

            class MyTask (Task):
                def run(self):
                    return self._func(*self._args, **self._kwargs)

            self.tp = ThreadPool(max_conn, max_conn*5) 
            self.tp.start()

            while self.running:
                try:
                    client, addr = self.sock.accept()
                    self.tp.add(MyTask(handle, client=client, addr=addr, framed=self.framed))
                except KeyboardInterrupt:
                    break
                    #os.kill(os.getpid(), 9)
                except Exception as e:
                    log.warn('worker exception: %s', str(e))
                    log.warn(traceback.format_exc())

            self.tp.stop()


        def _start_process(index):
            server_name = 'proc-%02d' % index
            p = multiprocessing.Process(target=server_start, name=server_name)
            p.start()
            return p
        

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(addr)
        self.sock.listen(1024)

        if max_process == 1:
            signal.signal(signal.SIGTERM, signal_worker_handler)
            server_start()
        else:
            for i in range(0, max_process):
                self.workers.append(_start_process(i))

            signal.signal(signal.SIGTERM, signal_master_handler)
            signal.signal(signal.SIGCHLD, signal_child_handler)


def test_gevent():
    from zbase3.base import logger
    logger.install('stdout')
    from zbase.thriftclient.payprocessor import PayProcessor
    import gevent

    class TestHandler:
        def ping(self):
            log.debug('pong')
            gevent.sleep(3)
        
        def trade(self, jsonstr):
            log.debug('recv:', jsonstr)
                 
    server = ThriftServer(PayProcessor, TestHandler, ('127.0.0.1', 10000), 2)
    server.forever()

 

def test_thread():
    from zbase3.base import logger
    logger.install('stdout')
    from zbase.thriftclient.payprocessor import PayProcessor

    class TestHandler:
        def ping(self):
            log.debug('pong')
            time.sleep(3)
        
        def trade(self, jsonstr):
            log.debug('recv:', jsonstr)
                 
    server = ThriftThreadServer(PayProcessor, TestHandler, ('127.0.0.1', 10000), 2)
    server.forever()



if __name__ == '__main__':
    #test_gevent()
    test_thread()


