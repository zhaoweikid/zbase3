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


# session refresh record. {date: {sid:time}}
session_refresh = {}


class SessionError (Exception):
    pass


class Session (UserDict):
    def __init__(self, sid=None, expire=3600, refresh_time=300):
        UserDict.__init__(self)
        self.sid = sid
        self._changed = False
        self._refresh_time = refresh_time
        if sid:
            self._load()
        else:
            self._create_sid()

    def __setitem__(self, key, item):
        self._changed = True
        self.data[key] = item

    def __delitem__(self, key): 
        self._changed = True
        del self.data[key]

    def pop(self, key):
        self._changed = True
        return self.data.pop(key)

    def popitem(self):
        self._changed = True
        return self.data.popitem()

    def clear(self):
        self._changed = True
        return self.data.clear()

    def _create_sid(self):
        self.sid = 'ses'+base64.b32encode(uuid.uuid4().bytes).decode('utf-8').strip('=')

    def _load(self):
        pass

    def _check_refresh(self):
        global session_refresh
        now = datetime.datetime.now()
        ts = int(now.timestamp())
        k1 = '%d%02d%02d' % (now.year, now.month, now.day)
        yestoday = now - datetime.timedelta(days=1)
        k0 = '%d%02d%02d' % (yestoday.year, yestoday.month, yestoday.day)

        if k0 in session_refresh:
            session_refresh.pop(k0)

        v = session_refresh.get(k1)
        if not v:
            session_refresh[k1] = {self.sid: ts}
            return True

        t = v.get(self.sid) 
        if not t:
            v[self.sid] = ts
            return True

        if ts - t > self._refresh_time:
            v[self.sid] = ts
            return True

        # no need refresh
        return False

    def _update_refresh_cache(self):
        global session_refresh
        now = datetime.datetime.now()
        ts = int(now.timestamp())
        k1 = '%d%02d%02d' % (now.year, now.month, now.day)

        v = session_refresh.get(k1)
        if not v:
            session_refresh[k1] = {self.sid: ts}
        else:
            v[self.sid] = ts

        log.debug('update refresh cache: %s %s %d', k1, self.sid, ts)


    def save(self):
        pass

    def auto_save(self):
        if not self.data:
            if self._changed:
                self.remove()
            # not have session
            return False

        if self._changed:
            self.save()
        else:
            self.refresh()
        # have session
        return True

    def remove(self):
        pass

    def refresh(self):
        pass

try:
    import redis
    class SessionRedis (Session):
        def __init__(self, sid=None, server=None, expire=3600, db=0, refresh_time=300):
            self.addr = server[0]['addr']
            self.timeout = server[0]['timeout']
            self.db = db
            #self.conn = redis.Redis(host=addr[0], port=addr[1], socket_timeout=timeout, db=db)
            self.conn = None
            self.session_expire = expire
            Session.__init__(self, sid, refresh_time=refresh_time)

        def _check_conn(self):
            if not self.conn:
                self.conn = redis.Redis(host=self.addr[0], port=self.addr[1], socket_timeout=self.timeout, db=self.db)
            
        def _load(self):
            self._check_conn()
            v = self.conn.get(self.sid) 
            #if not v:
            #    raise SessionError('sid %s not have value' % self.sid)
            if v:
                self.data.update(json.loads(v.decode('utf-8')))

        def save(self):
            if not self.data:
                return
            v = json.dumps(self.data)

            self._check_conn()
            self.conn.set(self.sid, v, self.session_expire)

            self._update_refresh_cache()

        def remove(self):
            self._check_conn()
            self.conn.delete(self.sid)

        def refresh(self):
            if self._check_refresh():
                log.debug('refresh expire %s', self.sid)
                self._check_conn()
                self.conn.expire(self.sid, self.session_expire)
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


def test4():
    global session_refresh, log
    from zbase3.base import logger
    log = logger.install('stdout')

    cf1 = {'store':'SessionRedis', 'expire':3600, 'db':0, 'server':[{'addr':('127.0.0.1', 6379), 'timeout':1000}]}

    sids = []
    for i in range(0, 5):
        x1 = create(cf1, None)
        x1['name'] = 'zhaowei'
        x1['value'] = random.randint(0, 100)
        x1.save()
        sids.append(x1.sid)

        log.debug('refresh cache: %s', session_refresh)

    print('-'*30)

    for sid in sids:
        log.debug('check %s', sid)
        x1 = create(cf1, sid)
        x1._refresh_time = 2
        x1.refresh()

        log.debug('refresh cache: %s', session_refresh)
        time.sleep(1)


if __name__ == '__main__':
    test4()

