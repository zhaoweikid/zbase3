# coding: utf-8
import os, sys
import time
import socket
import random
import logging
from zbase3.server.rpc import *
from zbase3.server.defines import *
from zbase3.web import cache

log = logging.getLogger()

client = None

class NameClient:
    def __init__(self, cache_file=None, mode='random', cache_time=60):
        if not cache_file:
            cache_file = '/tmp/nc-%s' % os.envrion.get('MYNAME', str(os.getpid()))
        self.c = None
        server = os.environ['NAMECENTER']
        self.servers = []
        self.mode = mode
        self.cache_time = cache_time
        self.cache_file = cache_file
        self.cache_data = {}
        self._last_mod_time  = 0
        self._last_dump_time = 0
        self.timeout = 0.5
        
        ret = self.load_cache_file()
        if ret:
            self.cache_data = ret

        def func(key, value, info, name):
            return self._query(name)

        self._query_cache = cache.Cache(func, cache_time)
        
        if isinstance(server, str):
            addrs = [ x.strip().split(':') for x in server.split(',')]
            for addr in addrs:
                addr[1] = int(addr[1])
                self.servers.append(tuple(addr))

        log.debug('nameservers: %s', self.servers)
        
        self.c = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.c.settimeout(self.timeout)
        self.msgid = random.randint(0, 100000)
        self.pos = 0

    def __del__(self):
        self.close()

    def close(self):
        if self.c:
            self.c.close()
            self.c = None

    def set_cache_data(self, key, data):
        ex = self.cache_data.get(key)
        if ex and len(ex) == len(data):
            s1 = set([ x['server'] for x in ex ])
            s2 = set([ x['server'] for x in data ])
            if s1 == s2:
                return
        
        self.cache_data[key] = data
        self._last_mod_time = time.time()

        self.dump_cache_file()

    def load_cache_file(self):
        if not os.path.isdir(os.path.dirname(self.cache_file)):
            raise ValueError('not found dir:%s' % os.path.dirname(self.cache_file))
        if not os.path.isfile(self.cache_file):
            return
        if os.path.getsize(self.cache_file) == 0:
            return

        ret = None
        with open(self.cache_file, 'r+') as f:
            s = f.read()
            ret = json.loads(s)
        return ret

    def dump_cache_file(self):
        if not self.cache_data:
            return

        if self._last_mod_time - self._last_dump_time <= 0:
            return

        s = json.dumps(self.cache_data)
        with open(self.cache_file, 'w+') as f:
            f.write(s)
        self._last_dump_time = self._last_mod_time

    def report(self, name, addr, proto='rpc', mode=None):
        p = ReqProto()
        p.msgtype = TYPE_CALL_NOREPLY
        p.name = 'report'
        p.params = {
            'name':name, 
            'server':addr, 
            'proto':proto,
            'weight':1, 
            'rtime':int(time.time())
        }
        p.msgid = self.msgid
        self.msgid += 1
        s = p.dumps()
   
        if not mode:
            mode = self.mode
        if mode == 'all':
            for addr in self.servers:
                self.c.sendto(s, addr)
                log.info('server=nc|addr=%s:%d|f=report|name=%s|proto=%s|mode=%s|content=%s', addr[0], addr[1], name, proto, mode, s)
        elif mode == 'rr':
            addr = self.servers[self.pos%len(self.servers)]
            self.pos += 1
            self.c.sendto(s, addr)
            log.info('server=nc|addr=%s:%d|f=report|name=%s|proto=%s|mode=%s|content=%s', addr[0], addr[1], name, proto, mode, s)
        elif mode == 'random':
            addr = self.servers[random.randint(0, 100)%len(self.servers)]
            self.c.sendto(s, addr)
            log.info('server=nc|addr=%s:%d|f=report|name=%s|proto=%s|mode=%s|content=%s', addr[0], addr[1], name, proto, mode, s)

    def _query(self, name):
        params = {'name':name}
        retcode, result = self._req('query', params)
        if retcode == OK:
            ret = result[name]
            if ret:
                self.set_cache_data(name, ret)
            return ret
        if retcode == ERR:
            return self.cache_data.get(name)
        return

    def query(self, name, cache=True):
        return self._query_cache(name, not cache, name)

    def remove(self, name, addr):
        params = {'name':name, 'addr':addr}
        retcode, result = self._req('remove', params)
        return retcode

    def _req(self, func, params):
        p1 = ReqProto()
        p1.name = func
        p1.params = params
        p1.msgid = self.msgid
        self.msgid += 1
        s = p1.dumps()

        data = None
        random.shuffle(self.servers)
        for addr in self.servers:
            try:
                t1 = time.time()
                self.c.sendto(s, addr)
                data, newaddr = self.c.recvfrom(1000)
                log.info('server=nc|addr=%s:%d|f=%s|name=%s|t=%d|send=%s|recv=%s', addr[0], addr[1], func, params['name'], int((time.time()-t1)*1000000), s, data)
                #log.debug('recv data:%s', data)
            except:
                log.warning(traceback.format_exc())
                continue
            break
        if not data:
            return ERR, 'no response'
        p2 = RespProto.loads(data[8:])
        if p1.msgid != p2.msgid:
            return ERR, 'msgid error'
        return p2.retcode, p2.result


    def getall(self, key):
        p1 = ReqProto()
        p1.name = 'getall'
        p1.params = {}
        p1.msgid = self.msgid
        self.msgid += 1
        s = p1.dumps()
            
        # use tcp
        conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
        conn.settimeout(2)
        try:
            for addr in self.servers:
                log.debug('connect to %s', addr)
                try:
                    conn.connect(addr)
                    break
                except:
                    continue

            conn.send(s)
            head = conn.recv(8)
            bodylen = int(head.decode('utf-8'))
            body = conn.recv(bodylen)
            
            p2 = RespProto.loads(body)
            if p1.msgid != p2.msgid:
                return
            if p2.retcode != OK:
                return
            return p2.result
     
        except:
            log.info(traceback.format_exc())
        finally:
            conn.close()


def test():
    log = logger.install('stdout')
    name = 'testapp'
    addr1 = '127.0.0.1:8001'
    addr2 = '127.0.0.1:8002'

    c = NameClient('./namecache.dat', mode='random')
    ret = c.query(name, False)
     
    print('-'*12)
    c.report(name, addr1)

    ret = c.query(name, False)
    log.debug('query %s: %s', name, ret)
    time.sleep(0.2)
    ret = c.query(name, False)
    log.debug('query %s: %s', name, ret)
    
    print('-'*12)
    c.report(name, addr2)

    ret = c.query(name)
    log.debug('query %s: %s', name, ret)
    ret = c.query(name)
    log.debug('query %s: %s', name, ret)
 
    time.sleep(1.1)

    ret = c.query(name)
    log.debug('query %s: %s', name, ret)
 
    #log.debug('remove %s %s %d', name, addr, c.remove(name, addr))
    #log.debug('query %s: %s', name, c.query(name))
    
    #log.debug('getall: %s', c.getall())

if __name__ == '__main__':
    test()




