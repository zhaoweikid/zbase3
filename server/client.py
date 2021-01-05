# coding: utf-8
import time, random, os, sys
import socket
import traceback
import logging
from thrift.transport import TSocket
from thrift.transport import TTransport
from thrift.protocol import TBinaryProtocol
from zbase3.server import selector
from zbase3.base.httpclient import Urllib2Client
#from qfcommon.base import getconf
#from qfcommon.web import cache

log = logging.getLogger()

class ThriftClientError(Exception):
    pass

#def load_name(key, data):
#    return getconf.get_name_base(key)
#etcd_cache = cache.CacheDict(load_name, 60)

class ThriftClient:
    def __init__(self, server, thriftmod, timeout=0, framed=False, raise_except=False):
        '''server - 为Selector对象，或者地址{'addr':('127.0.0.1',5000),'timeout':1000}'''
        global etcd_cache
        self.starttime = time.time()
        self.server_selector  = None
        self.server = None
        self.client = None
        self.thriftmod    = thriftmod
        self.frame_transport = framed
        self.raise_except = raise_except  # 是否在调用时抛出异常

        self.timeout = timeout

        if isinstance(server, dict): # 只有一个server
            self.server = [server,]
            self.server_selector = selector.Selector(self.server, 'random')
        elif isinstance(server, list): # server列表，需要创建selector，策略为随机
            self.server = server
            self.server_selector = selector.Selector(self.server, 'random')
        #elif isinstance(server, str) or isinstance(server, unicode):
        #    self.server = etcd_cache[server]
        else: # 直接是selector
            self.server_selector = server
        while True:
            if self.open() == 0:
                break

    def open(self):
        starttime = time.time()
        err = ''
        self.transport = None
        #try:
        self.server = self.server_selector.next()
        if not self.server:
            restore(self.server_selector, self.thriftmod)

            self.server = self.server_selector.next()
            if not self.server:
                log.error('server=%s|err=no server!', self.thriftmod.__name__)
                raise ThriftClientError
        addr = self.server['server']['addr']

        try:
            self.socket = TSocket.TSocket(addr[0], addr[1])
            if self.timeout > 0:
                self.socket.setTimeout(self.timeout)
            else:
                self.socket.setTimeout(self.server['server']['timeout'])
            if self.frame_transport:
                self.transport = TTransport.TFramedTransport(self.socket)
            else:
                self.transport = TTransport.TBufferedTransport(self.socket)
            protocol = TBinaryProtocol.TBinaryProtocol(self.transport)

            self.client = self.thriftmod.Client(protocol)
            self.transport.open()
        except Exception as e:
            err = str(e)
            log.error(traceback.format_exc())
            self.server['valid'] = False

            if self.transport:
                self.transport.close()
                self.transport = None
        finally:
            endtime = time.time()
            addr = self.server['server']['addr']
            tname = self.thriftmod.__name__
            pos = tname.rfind('.')
            if pos > 0:
                tname = tname[pos+1:]
            s = 'server=%s|func=open|addr=%s:%d/%d|time=%d' % \
                    (tname,
                    addr[0], addr[1],
                    self.server['server']['timeout'],
                    int((endtime-starttime)*1000000),
                    )
            if err:
                s += '|err=%s' % repr(err)
                log.info(s)
        if not err:
            return 0
        return -1

    def __del__(self):
        self.close()

    def close(self):
        if self.transport:
            self.transport.close()
            self.transport = None
            self.client = None

    def call(self, funcname, *args, **kwargs):
        def _call_log(ret, err=''):
            endtime = time.time()
            addr = self.server['server']['addr']
            tname = self.thriftmod.__name__
            pos = tname.rfind('.')
            if pos > 0:
                tname = tname[pos+1:]

            s = 'server=%s|func=%s|addr=%s:%d/%d|time=%d|framed=%s|args=%d|kwargs=%d' % \
                    (tname, funcname,
                    addr[0], addr[1],
                    self.server['server']['timeout'],
                    int((endtime-starttime)*1000000),
                    self.frame_transport,
                    len(args), len(kwargs))
            if err:
                s += '|err=%s' % (repr(err))
                log.warn(s)
            else:
                log.info(s)

        starttime = time.time()
        ret = None
        try:
            func = getattr(self.client, funcname)
            ret = func(*args, **kwargs)
        except Exception as e:
            _call_log(ret, e)
            #如果是thrift自定义的异常
            if 'thrift_spec' in dir(e):
                log.warn(traceback.format_exc())
            else:
                log.error(traceback.format_exc())
            if self.raise_except:
                raise
        else:
            _call_log(ret)
        return ret

    def __getattr__(self, name):
        def _(*args, **kwargs):
            return self.call(name, *args, **kwargs)
        return _

def restore(selector, thriftmod, framed=False):
    invalid = selector.not_valid()
    #log.debug('invalid server:%s', invalid)
    for server in invalid:
        transport = None
        try:
            log.debug('try restore %s', server['server']['addr'])
            addr = server['server']['addr']
            transport = TSocket.TSocket(addr[0], addr[1])
            transport.setTimeout(1000)
            if framed:
                transport = TTransport.TFramedTransport(transport)
            else:
                transport = TTransport.TBufferedTransport(transport)
            protocol = TBinaryProtocol.TBinaryProtocol(transport)
            client = thriftmod.Client(protocol)
            transport.open()
            client.ping()
        except socket.timeout:
            log.warn('timeout 1000')
            log.error(traceback.format_exc())
            continue
        except:
            log.error(traceback.format_exc())
            log.debug("restore fail: %s", server['server']['addr'])
            continue
        finally:
            if transport:
                transport.close()

        log.debug('restore ok %s', server['server']['addr'])
        server['valid'] = True


class HttpClientError(Exception):
    pass

def with_http_retry(func):
    def _(self, *args, **kwargs):
        while True:
            try:
                result = func(self, *args, **kwargs)
                return result
            # 不要重试的错误
            except (HttpClientError, socket.timeout):
                if self.log_except:
                    log.warn(traceback.format_exc())
                if self.raise_except:
                    raise
                else:
                    return None
            # 重试的错误
            except:
                log.error(traceback.format_exc())
                if self.server:
                    self.server['valid'] = False
    return _

class HttpClient:
    def __init__(self, server, protocol='http', timeout=0, raise_except=False, log_except=True, client_class = Urllib2Client):
        self.server_selector  = None
        self.protocol = protocol
        self.timeout = timeout
        self.client_class = client_class
        self.client = None
        self.server = None
        self.raise_except = raise_except  # 是否在调用时抛出异常
        self.log_except = log_except  # 是否打日志

        if isinstance(server, dict): # 只有一个server
            self.server = [server,]
            self.server_selector = selector.Selector(self.server, 'random')
        elif isinstance(server, list): # server列表，需要创建selector，策略为随机
            self.server = server
            self.server_selector = selector.Selector(self.server, 'random')
        #elif isinstance(server, str) or isinstance(server, unicode):
        #    self.server = etcd_cache[server]
        else: # 直接是selector
            self.server_selector = server

        #如果无可用 尝试恢复
        if len(self.server_selector.valid()) == 0:
            http_restore(self.server_selector, self.protocol)

    @with_http_retry
    def call(self, func='get', path='/', *args, **kwargs):

        self.server = self.server_selector.next()
        if not self.server:
            raise HttpClientError('no valid server')

        domain = '%s://%s:%d' % (self.protocol, self.server['server']['addr'][0], self.server['server']['addr'][1])

        if self.timeout > 0:
            timeout = self.timeout
        else:
            timeout = self.server['server']['timeout']

        self.client = self.client_class(timeout = timeout/1000.0)

        func = getattr(self.client, func)
        return func(domain + path, *args, **kwargs)

    def __getattr__(self, func):
        def _(path, *args, **kwargs):
            return self.call(func, path, *args, **kwargs)
        return _

def http_restore(selector, protocol='http', path='/ping'):
    invalid = selector.not_valid()
    for server in invalid:
        try:
            log.debug('try restore %s', server['server']['addr'])
            domain = '%s://%s:%d' % (protocol, server['server']['addr'][0], server['server']['addr'][1])
            Urllib2Client(timeout=3).get(domain + path)
        except:
            log.error(traceback.format_exc())
            log.debug("restore fail: %s", server['server']['addr'])
            continue

        log.debug('restore ok %s', server['server']['addr'])
        server['valid'] = True


def test_http():
    from zbase3.base import logger
    from zbase3.base.httpclient import RequestsClient
    logger.install('stdout')
    SERVER   = [{'addr':('127.0.0.1', 6200), 'timeout':20},{'addr':('127.0.0.1', 6201), 'timeout':2000},]
    client = HttpClient(SERVER, client_class = RequestsClient)
    while 1:
        print(client.get('/ping'))
        raw_input('go')


def test_simple():
    from thriftclient3.payprocessor import PayProcessor
    from zbase3.base import logger
    global log
    logger.install('stdout')
    log = logger.log
    log.debug('test ...')
    serverlist = [{'addr':('127.0.0.1',4300), 'timeout':1000},
                  {'addr':('127.0.0.1', 4200), 'timeout':1000},
                  ]
    sel = selector.Selector(serverlist)
    for i in range(0, 10):
        client = ThriftClient(sel, PayProcessor)
        client.ping()

    server = sel.next()
    server['valid'] = False

    #log.debug('restore ...')
    #restore(sel)
    print('-'*60)
    for i in range(0, 10):
        client = ThriftClient(sel, PayProcessor)
        client.ping()

def test_ping(port=1000):
    from thriftclient3.spring import Spring
    from zbase3.base import logger
    global log
    log = logger.install('stdout')
    
    log.debug('test ...')
    serverlist = [
        {'addr':('127.0.0.1',port), 'timeout':1000},
        #{'addr':('127.0.0.1',4201), 'timeout':1000},
    ]
    sel = selector.Selector(serverlist)
    for i in range(0, 1000):
        client = ThriftClient(sel, Spring, framed=True)
        client.ping()


def test_selector():
    from thriftclient3.notifier import Notifier
    from zbase3.base import logger
    global log
    logger.install('stdout')
    log.debug("test framed transport")
    serverlist = [
            {'addr':('172.100.101.151', 15555), 'timeout':1000},
            ]
    sel = selector.Selector(serverlist)
    client = ThriftClient(sel, Notifier, framed=True)
    notify = {
            "notify_url":"http://172.100.101.151:8989/",
            "notify_data": {
                    "orderstatus":"5",
                }
            }
    import json
    ret = client.send_notify(json.dumps(notify))
    log.debug("send notify return:%s", ret)

def test_name():
    from thriftclient3.payprocessor import PayProcessor
    from zbase3.base import logger
    global log
    log = logger.install('stdout')
    log.debug('test ...')
    server_name = 'paycore'
    for i in range(0, 10):
        client = ThriftClient(server_name, PayProcessor)
        client.ping()


def test_perf():
    for i in range(0, 1000):
        test_ping(7200)

def test():
    f = globals()[sys.argv[1]]
    f()

if __name__ == '__main__':
    test()




