# coding: utf-8
import os, sys
from zbase3.micro.rpcore import RPCHandler
from zbase3.server.rpcserver import Handler


class MyUser (Handler):
    def login(self):
        '''用户登录'''
        return 0, 'ok'

class MainHandler (RPCHandler):
    def __init__(self, addr, data):
        self.user = MyUser(addr, data)
        RPCHandler.__init__(self, addr, data)

    def haha(self):
        '''哈哈'''
        return 0, 'haha'

