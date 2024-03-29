# coding: utf-8
import os, sys
import datetime, time
from zbase3.base import logger
from zbase3.server import rpcserver
from zbase3.server.baseserver import BaseGeventServer, BaseThreadServer, MyTask
from zbase3.server.rpcserver import Handler
from zbase3.base import dbpool
from multiprocessing import Process
import pprint
import types
import gevent
import logging

log = logging.getLogger()

class RPCHandler (Handler):
    def test(self):
        '''测试'''
        return 0, 'testme'

    def interface(self):
        '''获取服务提供的所有接口信息'''

        def get_method(obj):
            m = dir(obj)
            ifs = [ x for x in m if x[0] != '_' ] 
            
            its = {}
            for k in ifs:
                f = getattr(obj, k)
                if type(f) != types.MethodType:
                    if isinstance(f, Handler):
                        subfs = get_method(f)
                        for subk, subv in subfs.items():
                            its['%s.%s' % (k, subk)] = subv
                    continue
                its[k] = f.__doc__
            return its

        its = get_method(self)

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
        elif self.conf.PROTO == 'rpc-http':
            return rpcserver.HTTPServer(self.addr, self.handlercls)
        else:
            raise ValueError('config.PROTO error, must rpc-tcp/rpc-udp/rpc-http')
    
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
        if self.conf.PROTO == 'rpc-tcp':
            self.server = MyTCPServerHandler(self)
            return self.make_tcp_server()
        elif self.conf.PROTO == 'rpc-udp': 
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





