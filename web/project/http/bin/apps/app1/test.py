# vim: set ts=4 et sw=4 sts=4 fileencoding=utf-8 :

import os
import sys
from zbase3.web import core

class TestApp(core.Handler):
    def GET(self):
        self.write('test app')
