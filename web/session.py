# coding: utf-8
import base64
import datetime
import json
import logging
import os
import random
import time
import uuid
from collections import UserDict

log = logging.getLogger()

# session refresh record. {date: {sid:time}}
session_refresh = {}


class SessionError(Exception):
    pass


class Session(UserDict):
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
        self.sid = 'ses' + base64.b32encode(uuid.uuid4().bytes).decode('utf-8').strip('=')

    def _load(self):
        pass

    def _check_refresh(self):
        '''本地缓存session的刷新时间，减少对session存储的更新'''
        global session_refresh
        now = datetime.datetime.now()
        ts = int(now.timestamp())
        k1 = '%d%02d%02d' % (now.year, now.month, now.day)
        yestoday = now - datetime.timedelta(days=1)
        k0 = '%d%02d%02d' % (yestoday.year, yestoday.month, yestoday.day)

        # 只要24小时内的，再早的不要
        if k0 in session_refresh:
            session_refresh.pop(k0)

        # 缓存中没有今天的数据，要刷新
        v = session_refresh.get(k1)
        if not v:
            session_refresh[k1] = {self.sid: ts}
            return True

        # 缓存中没有此sid，要刷新
        t = v.get(self.sid)
        if not t:
            v[self.sid] = ts
            return True
        # 缓存中有数据，但是超时了要刷新
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
        '''根据是否有数据修改自动保存'''
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

    REDIS_POOLS = {}


    def get_redis_conn(redis_conf):
        global REDIS_POOLS
        key = '::'.join('{}={}'.format(k, v) for k, v in sorted(redis_conf.items()))
        if key not in REDIS_POOLS:
            REDIS_POOLS[key] = redis.Redis(**redis_conf)
        return REDIS_POOLS[key]


    class SessionRedis(Session):
        def __init__(self, sid=None, expire=3600, config=None):
            self.redis_conf = config.get('redis_conf')
            # self.db = config['db']
            # self.conn = redis.Redis(host=addr[0], port=addr[1], socket_timeout=timeout, db=db)
            self.conn = None
            refresh_time = config.get('refresh_time', 300)
            self.session_expire = expire
            Session.__init__(self, sid, refresh_time=refresh_time)

        def _check_conn(self):
            if not self.conn:
                self.conn = get_redis_conn(self.redis_conf)

        def _load(self):
            self._check_conn()
            v = self.conn.get(self.sid)
            # if not v:
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


    class SessionUser(Session):
        def __init__(self, sid=None, expire=3600, config=None):
            self.redis_conf = config.get('redis_conf')
            self.sid = sid
            self.user_key = config.get('user_key', 'userid')
            self.expire = expire
            self.conn = None
            self.userid = 0
            Session.__init__(self, sid, expire)

        def _load(self):
            v = self.db().get(self.sid)
            if v:
                self.data.update(json.loads(v.decode('utf-8')))
                self.userid = self.data.get(self.user_key, 0)

        def is_login(self):
            return self.userid > 0

        def zkey(self, userid=None):
            return 'zses.%s.%s' % (self.user_key, userid or self.data.get(self.user_key, ''))

        def save(self):
            if not self.data or self.user_key not in self.data:
                return

            self.db().set(self.sid, json.dumps(self.data), self.expire)

            now = time.time()
            self.db().zadd(self.zkey(), {self.sid: now + self.expire})
            self.db().zremrangebyscore(self.zkey(), '-inf', now)
            self.db().expire(self.zkey(), self.expire * 2)

        def db(self):
            if not self.conn:
                self.conn = get_redis_conn(self.redis_conf)
            return self.conn

        def refresh(self):
            self.db().expire(self.zkey(), self.expire * 2)
            self.db().expire(self.sid, self.expire)

        def remove(self):
            self.db().delete(self.sid)
            self.db().zrem(self.zkey(), self.sid)

        def kickoff(self, userid=None, keep_length=0):
            keys = self.db().zrange(self.zkey(userid), 0, -keep_length - 1)
            if keys:
                self.db().delete(*keys)
                self.db().zrem(self.zkey(userid), *keys)


except:
    pass


def bkdrhash(a):
    seed = 131
    s = 0
    b = a.encode('utf-8')
    for i in range(0, len(b)):
        s = s * seed + b[i]
    return s % 100000000


class SessionFile(Session):
    def __init__(self, sid=None, expire=3600, config=None):
        path = config.get['path']
        self.dirname = path
        self.filename = None

        Session.__init__(self, sid)

        if not self.filename:
            self.filename = '%s/ses%02d/%s' % (self.dirname, bkdrhash(self.sid) % 100, self.sid)

    def _load(self):
        if not self.filename:
            self.filename = '%s/ses%02d/%s' % (self.dirname, bkdrhash(self.sid) % 100, self.sid)

        if os.path.isfile(self.filename):
            self.data = json.loads(open(self.filename).read())
            # log.debug('open data file:%s, %s', self.filename, self.data)

    def save(self):
        if not self.data:
            return
        v = json.dumps(self.data)
        filepath = os.path.dirname(self.filename)
        if not os.path.isdir(filepath):
            os.makedirs(filepath)

        with open(self.filename, 'wb') as f:
            # log.debug('save ses: %s', self.filename)
            f.write(v.encode('utf-8'))

    def remove(self):
        if os.path.isfile(self.filename):
            # log.debug('remove ses: %s', self.filename)
            os.remove(self.filename)


class SessionMemory(Session):
    def __init__(self, expire=3600):
        Session.__init__(self, sid)


def create(conf, sid=None):
    classname = conf['store']
    cls = globals()[classname]
    return cls(sid, conf['expire'], conf['config'])


def test1():
    cf = {'host': '127.0.0.1', 'port': 6379}
    s = SessionRedis(server=cf)
    print('data:', s.data)
    s['name'] = 'zhaowei'
    s['time'] = time.time()
    s.save()
    print(s)
    print('data:', s.data)

    sid = s.sid

    print('-' * 60)

    print('sid:' + sid)
    s2 = SessionRedis(server=cf, sid=sid)
    print(s2)


def test2():
    cf = {'dir': './tmp/'}
    s = SessionFile(config=cf)
    s['name'] = 'zhaowei'
    s['time'] = time.time()
    s.save()
    print(s)

    sid = s.sid

    print('-' * 60)

    print('sid:', sid)
    s2 = SessionFile(sid, config=cf)
    print(s2)


def test3():
    cf1 = {
        'store': 'SessionRedis',
        'expire': 3600, 'db': 0,
        'redis': {'host': '127.0.0.1', 'port': 6379},
    }
    x1 = create(cf1, None)
    print(x1.sid)
    print('x1:', x1.__class__)

    cf2 = {'store': 'SessionFile', 'expire': 3600, 'path': '/tmp'}
    x2 = create(cf2, None)
    print(x2.sid)
    print('x2:', x2.__class__)


def test4():
    global session_refresh, log
    from zbase3.base import logger
    log = logger.install('stdout')

    cf1 = {
        'store': 'SessionRedis',
        'expire': 3600, 'db': 0,
        'redis': {'host': '127.0.0.1', 'port': 6379},
    }

    sids = []
    for i in range(0, 5):
        x1 = create(cf1, None)
        x1['name'] = 'zhaowei'
        x1['value'] = random.randint(0, 100)
        x1.save()
        sids.append(x1.sid)

        log.debug('refresh cache: %s', session_refresh)

    print('-' * 30)

    for sid in sids:
        log.debug('check %s', sid)
        x1 = create(cf1, sid)
        x1._refresh_time = 2
        x1.refresh()

        log.debug('refresh cache: %s', session_refresh)
        time.sleep(1)


def test5():
    REDIS_CONF = {'host': '127.0.0.1', 'port': '6379'}
    ses = SessionUser(redis=REDIS_CONF)
    ses['userid'] = '123'
    ses['name'] = 'yyk'
    ses.save()

    ses = SessionUser(sid=ses.sid, redis=REDIS_CONF)
    print(ses.data)

    ses.kickoff(ses.userid, 1)


def test6():
    """device"""
    cf = {'redis_conf': {'host': '127.0.0.1', 'port': 6379, 'db': 0}, 'user_key': 'device_id'}
    ses = SessionUser(config=cf)
    ses['device_id'] = 123
    ses['yyk'] = 123
    ses.save()
    print(ses.sid)

    ses1 = SessionUser(sid=ses.sid, config=cf)
    print(ses1.data)
    ses1.kickoff(ses1.userid)

    ses2 = SessionUser(sid=ses.sid, config=cf)
    print(ses2.data)


if __name__ == '__main__':
    # test4()
    # test5()
    test6()
