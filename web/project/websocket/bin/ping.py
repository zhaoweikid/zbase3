import logging

from zbase3.web import core

log = logging.getLogger()


class Ping(core.Handler):
    def GET(self):
        self.write('ok')
