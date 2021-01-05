# coding: utf-8
import os, sys
import datetime, time
from zbase3.base import logger
from zbase3.server import rpcserver
from zbase3.server.baseserver import BaseGeventServer, BaseThreadServer, Handler, MyTask
from zbase3.base import dbpool
from multiprocessing import Process
import types
import gevent
import logging

log = logging.getLogger()

class RPCHandler (Handler):
    def ping(self):
        '''检测服务存活'''
        return 0, 'pong'

    def interface(self):
        '''查询服务对外提供的所有接口及描述'''
        m = dir(self)
        ifs = [ x for x in m if x[0:2] != '__' ] 
        
        its = {}
        for k in ifs:
            f = getattr(self, k)
            log.debug('k:%s %s %s', k, type(k), type(f))
            if type(f) != types.MethodType:
                continue
            its[k] = f.__doc__
        return 0, {'interfaces':its}


class GeventServer (BaseGeventServer):
    def __init__(self, conf, handlercls):
        self.conf = conf

        if conf.MAX_PROC < 0 or conf.MAX_PROC > 100:
            log.error('processor num error, config.MAX_PROC=%d, must >0 and <100', conf.MAX_PROC)
            raise ValueError('process num error')

        BaseGeventServer.__init__(self, (conf.HOST, conf.PORT), handlercls, 
                conf.MAX_PROC, conf.MAX_CONN, conf.MAX_REQ)
        log.info('start geventserver ...')

    def make_server(self):
        if self.conf.PROTO == 'rpc-tcp':
            return rpcserver.TCPServer(self.addr, self.handlercls, spawn=self.pool)
        elif self.conf.PROTO == 'rpc-udp':
            return rpcserver.UDPServer(self.addr, self.handlercls)
        else:
            raise ValueError('config.PROTO error, must rpc-tcp/rpc-udp')
    
    def install(self):
        if hasattr(self.conf, 'DATABASE'):
            log.info('install db')
            dbpool.install(self.conf.DATABASE)


class MyTCPServerHandler (rpcserver.TCPServerHandler):
    def __init__(self, thserver):
        self.thserver = thserver
        self.max_req = thserver.max_req
        rpcserver.TCPServerHandler.__init__(self, thserver.handlercls)

    def stop(self):
        self.thserver.stop_worker()

class MyUDPServerHandler (rpcserver.UDPServerHandler):
    def __init__(self, thserver):
        self.thserver = thserver
        self.max_req = thserver.max_req
        rpcserver.UDPServerHandler.__init__(self, thserver.handlercls)

    def stop(self):
        self.thserver.stop_worker()


class ThreadServer (BaseThreadServer):
    def __init__(self, conf, handlercls):
        self.conf = conf

        if conf.MAX_PROC < 0 or conf.MAX_PROC > 100:
            log.error('processor num error, config.MAX_PROC=%d, must >0 and <100', conf.MAX_PROC)
            raise ValueError('process num error')

        BaseThreadServer.__init__(self, (conf.HOST, conf.PORT), handlercls, 
                conf.MAX_PROC, conf.MAX_CONN, conf.MAX_REQ)
        log.info('start threadserver ...')

    def make_server(self):
        if self.conf.PROTO == 'tcp':
            self.server = MyTCPServerHandler(self)
            return self.make_tcp_server()
        elif self.conf.PROTO == 'udp': 
            self.server = MyUDPServerHandler(self)
            return self.make_udp_server()
        else:
            raise ValueError('config.PROTO error: %s', self.conf.PROTO)

    def make_task(self, client, addr):
        return MyTask(self.server.handle, client, addr)
    
    def install(self):
        if hasattr(self.conf, 'DATABASE'):
            log.info('install db')
            dbpool.install(self.conf.DATABASE)





