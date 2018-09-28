# coding: utf-8
import os, sys
from zbase3.micro import core

import microtest
from microtest import Test


class TestHandler (core.Handler):
    define = Test
    def ping(self):
        return 'pong'


