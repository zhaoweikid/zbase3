# coding: utf-8
import os, sys
import time
import traceback
import types
import logging

log = logging.getLogger()

class Cache (object):
    def __init__(self):
        # key: {func:, timeout:, last:, data:}
        self._cache = {}

    def add(self, key, update_func, timeout):
        item = {'key':key, 'func':update_func, 'timeout':timeout, 'last':0, 'data':None}
        self._cache[key] = item

    def exist(self, key):
        return key in self._cache

    def remove(self, key):
        if key in self._cache:
            self._cache.pop(key)

    def __call__(self, _key, _refresh=False, *args, **kwargs):
        item = self._cache.get(_key)
        if not item:
            return None

        data = item['data']
        last = item['last']
        timeout = item['timeout']
        now = time.time()
        if _refresh or now-last >= timeout:
            data = item['func'](data, {'key':_key,'last':last,'timeout':timeout}, *args, **kwargs)
            item['last'] = now
            item['data'] = data
        return data


caches = Cache()

# 给类方法用的
def with_cache(timeout):
    def f(func):
        fpath = os.path.abspath(__file__)
        funcname = func.__name__
        def cache_wrap(data, info, *args, **kwargs):
            return func(*args, **kwargs)
             
        def _(*args, **kwargs):
            classname = args[0].__class__.__name__
            key = 'c_%s_%s_%s' % (fpath, classname, funcname)
            
            if not caches.exist(key):
                caches.add(key, cache_wrap, timeout)

            return caches(key, False, *args, **kwargs)
        return _
    return f

# 只能给独立的function使用
def with_cache_func(timeout):
    def f(func):
        fpath = os.path.abspath(__file__)
        funcname = func.__name__
        def cache_wrap(data, info, *args, **kwargs):
            return func(*args, **kwargs)
             
        def _(*args, **kwargs):
            key = 'c_%s_%s' % (fpath, funcname)
            if not caches.exist(key):
                caches.add(key, cache_wrap, timeout)
            return caches(key, False, *args, **kwargs)
        return _
    return f




def test_base():
    #import inspect
    #print('-'*6, inspect.stack()[0].function, '-'*6)
    
    def func1(data, info):
        return 'name-%.3f' % time.time()

    def func2(data, info):
        return 'count-%.3f' % time.time()
    
    global caches
    #caches = Cache()
    caches.add('name', func1, 0.3)
    caches.add('count', func2, 0.3)

    for i in range(0, 3):
        print(caches('name'))
        print(caches('count'))
        time.sleep(.2)

    time.sleep(.1)
    print("refresh:", caches('name', True))
    time.sleep(.1)
    print("refresh:", caches('name', True))
    time.sleep(.1)
    print("refresh:", caches('name', True))
    time.sleep(.1)

    print(caches('name'))


def test_decorator_class():
    #import inspect
    #print('-'*6, inspect.stack()[0].function, '-'*6)

    class Test1 (object):
        def test(self, name):
            return 'test1-%s-%f' % (name, time.time())

    class Test2 (object):
        @with_cache(0.2)
        def test(self, name):
            return 'test2-%s-%f' % (name, time.time())

    t1 = Test1()
    t2 = Test2()

    for i in range(0, 3):
        print('Test1:', t1.test(str(i)))
        print('Test2:', t2.test(str(i)))
        print('Test2:', t2.test(name=str(i)))
        time.sleep(0.1)



def test_decorator_func():
    #import inspect
    #print('-'*6, inspect.stack()[0].function, '-'*6)

    def test1(name):
        return 'test1-%s-%f' % (name, time.time())

    @with_cache_func(0.2)
    def test2(name):
        return 'test2-%s-%f' % (name, time.time())

    for i in range(0, 3):
        print('Test1:', test1(str(i)))
        print('Test2:', test2(str(i)))
        print('Test2:', test2(name=str(i)))
        time.sleep(0.1)

 

if __name__ == '__main__':
    fs = list(globals().keys())
    for k in fs:
        if k.startswith('test_'):
            print('-'*6, k, '-'*6)
            globals()[k]()




