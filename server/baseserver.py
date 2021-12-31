# coding: utf-8
if __name__ == '__main__':
    from gevent import monkey; monkey.patch_all()
import os
import sys
import traceback
import multiprocessing
import select
import logging
import time
import socket
import signal
import fcntl
import gevent
import functools
from gevent.server import StreamServer
from gevent.pool import Pool
from zbase3.server.threadpool import ThreadPool, Task

log = logging.getLogger()

proctitle = ''
try:
    import setproctitle
    proctitle = setproctitle.getproctitle()
except:
    log.info('setproctitle error')    


class Handler:
    def __init__(self, addr):
        self.addr = addr


class BaseServer (object):
    SIG_QUEUE = []
    def __init__(self, addr, handler_class, max_proc=1, max_conn=1000, max_req=0):
        self.reqs = 0
        self.max_req  = max_req
        self.max_conn = max_conn
        self.max_proc = max_proc

        self.create_pipe()

        self.handlercls = handler_class
        self.addr = addr

        self.workers = set() # pid
        self.running = True
        self.reqs = 0
        self.server_pid = os.getpid()

    def create_pipe(self):
        '''给信号处理用的管道'''
        self.rfd, self.wfd = os.pipe()
        
        flags = fcntl.fcntl(self.rfd, fcntl.F_GETFL)
        flags |= os.O_NONBLOCK
        fcntl.fcntl(self.rfd, fcntl.F_SETFL, flags)

        #flags = fcntl.fcntl(self.wfd, fcntl.F_GETFL)
        #flags |= os.O_NONBLOCK
        #fcntl.fcntl(self.wfd, fcntl.F_SETFL, flags)

    def install(self):
        '''每个进程保证只会执行一次,在多进程中只会在子进程中执行'''
        pass

    def make_server(self):
        '''创建主业务处理对象'''
        pass


    def start_worker(self):
        '''运行子进程逻辑'''
        pass


    def create_worker(self):
        '''创建子进程'''
        log.info('master %d fork one', os.getpid())
        pid = os.fork()
        if pid < 0:
            log.warn('fork error: %d', pid)
            return

        if pid == 0: # child
            try:
                if proctitle:
                    setproctitle.setproctitle(proctitle)
                self.start_worker()
            except:
                log.info('worker exit !!!' + traceback.format_exc())
            os._exit(0)
        else:
            self.workers.add(pid)

    def start_master(self):
        '''运行管理进程逻辑'''
        def signal_master_handler(signum, frame):
            log.warn("signal %d in master %d, wait for kill all worker", signum, os.getpid())
            self.SIG_QUEUE.append(signum)
            os.write(self.wfd, b'.')

        def signal_master_usr1_handler(signum, frame):
            log.warn("signal %d in master %d, wait for kill all worker", signum, os.getpid())
            self.SIG_QUEUE.append(signum)
            os.write(self.wfd, b'.')
        
        def signal_child_handler(signum, frame):
            log.warn("master recv worker exit signum:%d", signum)
            self.SIG_QUEUE.append(signum)
            os.write(self.wfd, b'.')
    
        signal.signal(signal.SIGTERM, signal_master_handler)
        signal.signal(signal.SIGUSR1, signal_master_usr1_handler)
        signal.signal(signal.SIGCHLD, signal_child_handler)

    def wait_child(self, option=0):
        '''回收结束的子进程'''
        try:
            pinfo = os.waitpid(-1, option)
            pid = pinfo[0]
            if pid != 0:
                log.warn('worker %d exited, fork one', pid)
                self.workers.remove(pid)
                if self.running:
                    self.create_worker()
        except:
            log.info(traceback.format_exc())


    def apply_signal(self):
        '''处理排队的信号'''
        while len(self.SIG_QUEUE) > 0:
            sig = self.SIG_QUEUE.pop(0)
            log.info('apply sig %d', sig)
            if sig == signal.SIGTERM:
                self.stop()
                for pid in self.workers:
                    log.info('send SIGTERM to %d', pid)
                    try:
                        os.kill(pid, signal.SIGTERM)
                    except:
                        log.info(traceback.format_exc())
            elif sig == signal.SIGUSR1:
                self.create_worker()
            elif sig == signal.SIGCHLD:
                self.wait_child()


    def forever(self):
        '''主循环'''
        myid = os.getpid()
        if proctitle:
            setproctitle.setproctitle(proctitle + ' [Master]')
        
        try:
            while self.running:
                if os.getpid() != myid:
                    log.warn('pid error, worker ?????????')
                    time.sleep(1)
                    continue

                try:
                    ready = select.select([self.rfd], [], [], 1)
                    if ready[0]:
                        try:
                            while os.read(self.rfd, 1): pass
                        except BlockingIOError:
                            pass
                        self.apply_signal()
                    else:
                        self.wait_child(os.WNOHANG)
                except KeyboardInterrupt:
                    log.info(traceback.format_exc())
                    break
                except ChildProcessError as e:
                    log.info('wait no child: %s', str(e))
                except:
                    log.info(traceback.format_exc())
        except Exception as e:
            log.warn('master exception: %s', str(e))
            log.warn(traceback.format_exc())
        finally:
            log.warn('master exit ...')
            self.running = False
            time.sleep(1)
            for pid in self.workers:
                try:
                    log.info('master terminate %d', pid)
                    os.kill(pid, signal.SIGTERM)
                except:
                    pass
                    #log.info(traceback.format_exc())
        log.warn('master exited')

    def stop(self):
        '''停止所有服务'''
        self.running = False

    def stop_worker(self):
        '''停止子进程'''
        pass


class BaseGeventServer (BaseServer):
    def __init__(self, addr, handler_class, max_proc=1, max_conn=1000, max_req=0):
        BaseServer.__init__(self, addr, handler_class, max_proc, max_conn, max_req)
        
        self.pool = Pool(max_conn)

        self.server = self.make_server()
        self.server.reuse_addr = 1
        self.server.init_socket()
        self.server.max_req = max_req
        log.warn('!!! server starting ...')

        if max_proc == 1:
            self.start_worker()
        else:
            for i in range(0, max_proc):
                self.create_worker()
            self.start_master()


    def start_worker(self):
        def signal_worker_handler(signum, frame):
            log.warn("worker %d will exit after all request handled", os.getpid())
            self.server.stop()
            log.info('worker stopped')
 
        signal.signal(signal.SIGTERM, signal_worker_handler)
        #signal.signal(signal.SIGCHLD, signal.SIG_IGN)
        log.warn('server started addr=%s:%d pid=%d', self.addr[0], self.addr[1], os.getpid())
        self.install()
        log.debug('worker ready!')
        self.server.serve_forever()
        log.info('worker %d exit', os.getpid())
        os._exit(0)


    def stop_worker(self):
        log.warn('stop worker')
        self.server.stop()

    def make_server(self):
        def handler(client, addr):
            log.debug('new client:%s', addr)

        server = StreamServer(addr, handle, spawn=self.pool)
        return server


    def stop(self):
        self.stop_worker()
        self.running = False


class MyTask(Task):
    def run(self):
        try:
            return self._func(*self._args)
        finally:
            self._args[0].close()


class BaseThreadServer (BaseServer):
    def __init__(self, addr, handler_class, max_proc=1, max_conn=10, max_req=0):
        BaseServer.__init__(self, addr, handler_class, max_proc, max_conn, max_req)

        self.sock = self.make_server()

        if max_proc == 1:
            start_worker()
        else:
            for i in range(0, max_proc):
                self.create_worker()

    def make_server(self):
        return self.make_tcp_server()

    def make_tcp_server(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(self.addr)
        sock.listen(1024)
        
        return sock

    def make_udp_server(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, 0)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(self.addr)

        return sock

    def start_worker(self):
        def signal_worker_handler(signum, frame):
            log.warn("worker %d will exit after all request handled", os.getpid())
            self.running = False
            self.sock.close()
            self.sock = None

        signal.signal(signal.SIGTERM, signal_worker_handler)
        log.warn('server started addr=%s:%d pid=%d', self.addr[0], self.addr[1], os.getpid())

        self.install()
        self.tp = ThreadPool(self.max_conn, self.max_conn*5) 
        self.tp.start()

        log.debug('worker ready!')
        while self.sock:
            try:
                if self.sock.type == socket.SOCK_STREAM:
                    client, addr = self.sock.accept()
                    self.tp.add(self.make_task(client, addr))
                elif self.sock.type == socket.SOCK_DGRAM:
                    data, addr = self.sock.recvfrom(1024)
                    self.tp.add(self.make_task(data, addr))
                else:
                    raise ValueError('socket type not support: %s', self.sock.type.name)
            except KeyboardInterrupt:
                break
            except Exception as e:
                log.warn('worker exception: %s', str(e))
                log.warn(traceback.format_exc())

        self.tp.stop()

    def stop_worker(self):
        log.warn('stop worker')
        if self.sock:
            self.sock.close()
            self.sock = None

    def make_task(self, client, addr):
        def handle(client, addr):
            log.debug('new client:%s', addr)

        return MyTask(handle, client, addr)


class TestHandler (Handler):
    def ping(self):
        log.debug('pong')
    
    def trade(self, jsonstr):
        log.debug('recv:', jsonstr)

def test_handle(client, addr):
    f = client.makefile()
    for ln in f:
        log.debug(ln.strip())
        s = 'hehe ' + ln
        client.send(s.encode('utf-8'))


def test_gevent():
    from zbase3.base import logger
    logger.install('stdout')

    class TestGeventServer (BaseGeventServer):
        def make_server(self):
            server = StreamServer(self.addr, test_handle, spawn=self.pool)
            return server

    server = TestGeventServer(('127.0.0.1', 10000), TestHandler, 2)
    server.forever()
 

def test_thread():
    from zbase3.base import logger
    logger.install('stdout')

    class TestThreadServer (BaseThreadServer):
        def make_task(self, client, addr):
            return MyTask(test_handle, client, addr)

    server = TestThreadServer(('127.0.0.1', 10000), TestHandler, 2)
    server.forever()


def test():
    f = globals()[sys.argv[1]]
    f()
 
if __name__ == '__main__':
    test()


