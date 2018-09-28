# coding: utf-8
import string, os, sys, time
import shutil, random
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
        self.sid = 'sid'+str(base64.b32encode(uuid.uuid4().bytes)).strip('=')

    def _load(self):
        pass

    def save(self):
        pass

    def remove(self):
        pass

try:
    import redis
    class SessionRedis (Session):
        def __init__(self, server=None, sid=None, expire=3600):
            addr = server['addr']
            self.conn = redis.Redis(host=addr[0], port=addr[1], 
                    socket_timeout=server['timeout'], db=0)
            self.session_expire = expire
            Session.__init__(self, sid)

        def _load(self):
            v = self.conn.get(self.sid) 
            if not v:
                raise SessionError('sid %s not have value' % self.sid)
            self.data.update(json.loads(v))

        def save(self):
            if not self.data:
                return
            v = json.dumps(self.data, separators=(',', ':'))
            self.conn.set(self.sid, v, self.session_expire)

        def remove(self):
            self.conn.delete(self.sid)
except:
    pass

class SessionFile (Session):
    def __init__(self, config=None, sid=None):
        self.dirname = config['dir']
        self.filename = None
   
        Session.__init__(self, sid)
        
        if not self.filename:
            self.filename = '%s/%02d/%s' % (self.dirname, hash(self.sid)%100, self.sid)

    def _load(self):
        if not self.filename:
            self.filename = '%s/%02d/%s' % (self.dirname, hash(self.sid)%100, self.sid)
        if os.path.isfile(self.filename):
            self.data = json.loads(open(self.filename).read())

    def save(self):
        if not self.data:
            return
        v = json.dumps(self.data, separators=(',', ':'))
        filepath = os.path.dirname(self.filename)
        if not os.path.isdir(filepath):
            os.makedirs(filepath)
 
        with open(self.filename, 'wb') as f:
            f.write(v)

    def remove(self):
        if os.path.isfile(self.filename):
            os.remove(self.filename)



def create(classname, cfg, sid):
    cls = globals()[classname]
    return cls(cfg, sid)


def test1():
    cf = {'addr':('127.0.0.1', 6379), 'timeout':1000}
    s = SessionRedis(server=cf)
    s['name'] = 'zhaowei'
    s['time'] = time.time()
    s.save()
    print(s)

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
    cf = {'addr':('127.0.0.1', 6379), 'timeout':1000}
    x = create('SessionRedis', cf, '1111111')




if __name__ == '__main__':
    test1()

