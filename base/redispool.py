#!/usr/bin/env python
# -*- coding: utf-8 -*-
# tool for redis
# @yushijun

import time
import logging

from contextlib import contextmanager

log = logging.getLogger()

class RedisLockException(Exception):
    pass

def patch():

    def timeit(self, *args, **kwargs):
        tstart = time.time()
        ret = self.orig_execute_command(*args, **kwargs)
        tend = time.time()
        log.info('server=redis|addr=%s:%d|db=%d|cmd=%s|ret=%s|time=%d',
                 self.connection_pool.connection_kwargs.get('host', ''),
                 self.connection_pool.connection_kwargs.get('port', 0),
                 self.connection_pool.connection_kwargs.get('db', 0),
                 args, ret, (tend-tstart)*1000000)
        return ret

    from redis import StrictRedis
    StrictRedis.orig_execute_command = StrictRedis.execute_command
    StrictRedis.execute_command = timeit

@contextmanager
def redis_lock(conn, key):
    key = 'zbase.redis_lock.%s' % key
    value = str(int(time.time()))
    ret = False
    try:
        ret = conn.setnx(key, value)
        if not ret:
            raise RedisLockException('redis lock [%s] is exist' % key)
        yield
    finally:
        if ret:
            conn.delete(key)

def test():
    patch()
    from zbase3.base import logger
    logger.install('stdout')
    import redis
    conn = redis.Redis('172.100.101.106')
    with redis_lock(conn, 'test'):
        import time
        time.sleep(10)
        print(1)

if __name__ == '__main__':
    test()
