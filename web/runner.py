# coding: utf-8
import os, sys
import logging

log = logging.getLogger()

def run_werkzeug(app, host='127.0.0.1', port=8000, thread=0, proc=1):
    from werkzeug import script
    action_runserver = None
    if thread > 0:
        action_runserver = script.make_runserver(lambda: app, hostname=host, port=port, threaded=thread)
    else:
        action_runserver = script.make_runserver(lambda: app, hostname=host, port=port, processes=proc)
    log.info("Server running on port %s:%d" % (host, port))
    action_shell = script.make_shell(lambda: {})
    script.run(args=['runserver'])

def run_flup(app, *args, **kwargs):
    from flup.server import fcgi
    fcgi.WSGIServer(app).run()

def run_tornado(app, port=8000, proc=1, maxproc=100, *args, **kwargs):
    from tornado.httpserver import HTTPServer
    import tornado.ioloop
    import tornado.web
    import tornado.wsgi
    import tornado.process

    sock = tornado.netutil.bind_sockets(port)
    log.info("Server running on port %d" % (port))
    tornado.process.fork_processes(proc, maxproc)
    container = tornado.wsgi.WSGIContainer(app)
    server = tornado.httpserver.HTTPServer(container)
    server.add_sockets(sock)
    tornado.ioloop.IOLoop.instance().start()

def run_gevent(app, host='127.0.0.1', port=8000, *args, **kwargs):
    from gevent.pywsgi import WSGIServer

    server = WSGIServer((host, port), app)
    server.backlog = 1024
    try:
        log.info("Server running on port %s:%d" % (host, port))
        server.serve_forever()
    except KeyboardInterrupt:
        server.stop()

def run_cherrypy(app, host='127.0.0.1', port=8000, *args, **kwargs):
    from cherrypy import wsgiserver
    server = wsgiserver.CherryPyWSGIServer((host, port), app)
    log.info("Server running on port %s:%d" % (host, port))
    server.start()

def run_twisted(app, port=8000, *args, **kwargs):
    from twisted.web.wsgi import WSGIResource
    from twisted.internet import reactor
    from twisted.web import wsgi, server

    resource = WSGIResource(reactor, reactor.getThreadPool(), app)
    reactor.listenTCP(port, server.Site(resource))
    log.info("Server running on port %d" % (port))
    reactor.run()

def run_simple(app, port=8000, *args, **kwargs):
    from wsgiref.simple_server import WSGIRequestHandler, WSGIServer
    from wsgiref.simple_server import make_server
    from socketserver import ThreadingMixIn

    class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
        pass

    class FixedHandler(WSGIRequestHandler):
        def address_string(self): # Prevent reverse DNS lookups please.
            return self.client_address[0]

    server = make_server('', port, app, ThreadingWSGIServer, FixedHandler)
    server.set_app(app)
    log.info("Server running on port %d" % (port))
    server.serve_forever()



def run(name, app, **kwargs):
    func = globals()['run_'+name]
    func(app, **kwargs)

