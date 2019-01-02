# coding: utf-8
import os, sys
from zbase3.server.thriftserver import ThriftServer, ThriftThreadServer
from zbase3.base import dbpool
import logging

log = logging.getLogger()

class Handler:
    def ping(self):
        pass


class MicroThriftServer (ThriftServer):
    def __init__(self, module, handler_class, config):
        self.conf = config
        ThriftServer.__init__(self, module, handler_class, 
                (config.HOST, config.PORT), config.PROCS, config.MAX_CONN)

    def install(self):
        if hasattr(self.conf, 'DATABASE'):
            log.info('install db')
            dbpool.install(self.conf.DATABASE)


class MicroThriftThreadServer (ThriftThreadServer):
    def __init__(self, module, handler_class, config):
        self.conf = config
        ThriftServer.__init__(self, module, handler_class, 
                (config.HOST, config.PORT), config.PROCS, config.MAX_CONN)

    def install(self):
        if hasattr(self.conf, 'DATABASE'):
            log.info('install db')
            dbpool.install(self.conf.DATABASE)





