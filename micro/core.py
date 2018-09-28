# coding: utf-8
import os, sys
from zbase3.server import thriftserver

class Handler:
    def ping(self):
        pass

def test():
    from zbase3.base import logger
    logger.install('stdout')
    from zbase3.thriftclient.payprocessor import PayProcessor

    class TestHandler (Handler):
        def trade(self, jsonstr):
            log.debug('recv:', jsonstr)
            
    server = thriftserver.ThriftServer(PayProcessor, TestHandler, ('127.0.0.1', 10000), 3)
    server.forever()


if __name__ == '__main__':
    test()


