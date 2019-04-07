# coding: utf-8
import os, sys
import shutil, random
import copy
import time
import datetime
import traceback, types
import logging
from collections import UserDict
import uuid, json, base64

log = logging.getLogger()




class SessionError (Exception):
    pass


class Session (UserDict):
    def __init__(self, sid=None, expire=3600):
        UserDict.__init__(self)
        self.sid = sid
        if sid:
            self._load()
        else:
            self._create_sid()

    def _create_sid(self):
        self.sid = 'ses'+base64.b32encode(uuid.uuid4().bytes).decode('utf-8').strip('=')

    def _load(self):
        pass

    def save(self):
        pass

    def remove(self):
        pass

try:
    import redis
    class SessionRedis (Session):
        def __init__(self, sid=None, server=None, expire=3600, db=0):
            addr = server[0]['addr']
            timeout = server[0]['timeout']
            self.conn = redis.Redis(host=addr[0], port=addr[1], 
                    socket_timeout=timeout, db=db)
            self.session_expire = expire
            Session.__init__(self, sid)

        def _load(self):
            v = self.conn.get(self.sid) 
            #if not v:
            #    raise SessionError('sid %s not have value' % self.sid)
            if v:
                self.data.update(json.loads(v.decode('utf-8')))

        def save(self):
            if not self.data:
                return
            v = json.dumps(self.data)
            self.conn.set(self.sid, v, self.session_expire)

        def remove(self):
            self.conn.delete(self.sid)
except:
    pass



def bkdrhash(a):
    seed = 131
    s = 0
    b = a.encode('utf-8')
    for i in range(0, len(b)):
        s = s * seed + b[i]
    return s % 100000000



class SessionFile (Session):
    def __init__(self, sid=None, path=None, expire=3600):
        self.dirname = path
        self.filename = None
   
        Session.__init__(self, sid)
        
        if not self.filename:
            self.filename = '%s/ses%02d/%s' % (self.dirname, bkdrhash(self.sid)%100, self.sid)

    def _load(self):
        if not self.filename:
            self.filename = '%s/ses%02d/%s' % (self.dirname, bkdrhash(self.sid)%100, self.sid)

        if os.path.isfile(self.filename):
            self.data = json.loads(open(self.filename).read())
            #log.debug('open data file:%s, %s', self.filename, self.data)

    def save(self):
        if not self.data:
            return
        v = json.dumps(self.data)
        filepath = os.path.dirname(self.filename)
        if not os.path.isdir(filepath):
            os.makedirs(filepath)
 
        with open(self.filename, 'wb') as f:
            #log.debug('save ses: %s', self.filename)
            f.write(v.encode('utf-8'))

    def remove(self):
        if os.path.isfile(self.filename):
            #log.debug('remove ses: %s', self.filename)
            os.remove(self.filename)



def create(cfg, sid=None):
    conf = copy.copy(cfg)
    classname = conf['store']
    conf.pop('store')
    conf['sid'] = sid
    cls = globals()[classname]
    return cls(**conf)


def test1():
    cf = [{'addr':('127.0.0.1', 6379), 'timeout':1000}]
    s = SessionRedis(server=cf)
    print('data:', s.data)
    s['name'] = 'zhaowei'
    s['time'] = time.time()
    s.save()
    print(s)
    print('data:', s.data)

    sid = s.sid
   
    print('-'*60)
    
    print('sid:' + sid)
    s2 = SessionRedis(server=cf, sid=sid)
    print(s2)


def test2():
    cf = {'dir':'./tmp/'}
    s = SessionFile(config=cf)
    s['name'] = 'zhaowei'
    s['time'] = time.time()
    s.save()
    print(s)

    sid = s.sid
   
    print('-'*60)
    
    print('sid:', sid)
    s2 = SessionFile(sid, config=cf)
    print(s2)

def test3():
    cf1 = {'store':'SessionRedis', 'expire':3600, 'db':0, 'server':[{'addr':('127.0.0.1', 6379), 'timeout':1000}]}
    x1 = create(cf1, None)
    print(x1.sid)
    print('x1:', x1.__class__)

    cf2 = {'store':'SessionFile', 'expire':3600, 'path':'/tmp'}
    x2 = create(cf2, None)
    print(x2.sid)
    print('x2:', x2.__class__)





if __name__ == '__main__':
    test3()

