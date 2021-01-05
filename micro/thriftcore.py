# coding: utf-8
import os, sys
from zbase3.server.thriftserver import ThriftServer
from zbase3.base import dbpool
import logging

log = logging.getLogger()

class Handler:
    def ping(self):
        pass


class MicroThriftServer (ThriftServer):
    def __init__(self, module, handler_class, config):
        self.conf = config
        ThriftServer.__init__(self, (config.HOST, config.PORT), module, handler_class, 
                max_proc=config.MAX_PROC, max_conn=config.MAX_CONN, max_req=config.MAX_REQ)

    def install(self):
        if hasattr(self.conf, 'DATABASE'):
            log.info('install db')
            dbpool.install(self.conf.DATABASE)




