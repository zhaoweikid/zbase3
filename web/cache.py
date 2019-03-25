# coding: utf-8
import os, sys
import time
import traceback
import types
import logging

log = logging.getLogger()

# 两种缓存模式
# 1. 所有缓存key共用同一个更新函数
# 2. 缓存为每个key都设置一个更新函数
class Cache (object):
    def __init__(self, func=None, timeout=10):
        self._cache = {}
        # 以下为缓存模式1所用，只有模式1才需要
        self._func = func
        self._timeout = timeout

    def add(self, key, update_func, timeout):
        if key:
            # 以下为模式2
            item = {'key':key, 'func':update_func, 'timeout':timeout, 'last':0, 'data':None}
            self._cache[key] = item
        else:
            # 以下为模式1
            self._func = func
            self._timeout = timeout

    def exist(self, key):
        return key in self._cache

    def remove(self, key):
        if key in self._cache:
            self._cache.pop(key)

    def update(self, key, *args, **kwargs):
        item = self._cache.get(key)
        if not item:
            return

        now = time.time()
        data = item['func'](key, item['data'], item, *args, **kwargs)
        item['data'] = data
        item['last'] = now

        return data
 
    def __call__(self, key, _refresh=False, *args, **kwargs):
        item = self._cache.get(key)
        if not item:
            if not self._func:
                return
            item = {'func':self._func, 'timeout':self._timeout, 'last':0, 'data':None}
            self._cache[key] = item

        data = item['data']
        now = time.time()
        if _refresh or now-item['last'] >= item['timeout']:
            data = self.update(key, *args, **kwargs)
        return data

# 这是第2种缓存
caches = Cache()

# 给类方法用的
def with_cache(timeout):
    def f(func):
        fpath = os.path.abspath(__file__)
        funcname = func.__name__
        def cache_wrap(key, value, info, *args, **kwargs):
            return func(*args, **kwargs)
             
        def _(*args, **kwargs):
            classname = args[0].__class__.__name__
            key = 'c_%s_%s_%s' % (fpath, classname, funcname)
            global caches 
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
        def cache_wrap(key, value, info, *args, **kwargs):
            return func(*args, **kwargs)
             
        def _(*args, **kwargs):
            key = 'c_%s_%s' % (fpath, funcname)
            global caches
            if not caches.exist(key):
                caches.add(key, cache_wrap, timeout)
            return caches(key, False, *args, **kwargs)
        return _
    return f




def test_2():
    #import inspect
    #print('-'*6, inspect.stack()[0].function, '-'*6)
    
    def func1(key, value, info):
        return 'name-%.3f' % time.time()

    def func2(key, value, info):
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

def test_1():
    #import inspect
    #print('-'*6, inspect.stack()[0].function, '-'*6)
    
    def func1(key, value, info):
        return '%s-%.3f' % (key, time.time())

    c = Cache(func1, 0.3)

    for i in range(0, 3):
        print(c('haha1'))
        print(c('haha2'))
        time.sleep(.2)

    time.sleep(.1)

    v1 = c('haha1', True)
    print("refresh:", v1)
    time.sleep(.1)

    v2 = c('haha1', True)
    print("refresh:", v2)
    time.sleep(.1)

    assert v1 != v2

    v3 = c('haha1', True)
    print("refresh:", v3)
    time.sleep(.1)

    assert v3 != v2

    print(c('haha1'))


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

    last_v1 = 0
    last_v2 = 0
    last_v21 = 0

    for i in range(0, 3):
        v1 = t1.test(str(i))
        v2 = t2.test(str(i))
        v21 = t2.test(name=str(i))

        print('Test1:', v1)
        print('Test2:', v2)
        print('Test2:', v21)
        
        assert v2 == v21
        
        if i == 1:
            assert v2 == last_v2
            assert v21 == last_v21

        if i == 2:
            assert v2 != last_v2
            assert v21 != last_v21

        last_v1 = v1
        last_v2 = v2
        last_v21 = v21

        time.sleep(0.1)

 

def test_decorator_func():
    #import inspect
    #print('-'*6, inspect.stack()[0].function, '-'*6)

    def test1(name):
        return 'test1-%s-%f' % (name, time.time())

    @with_cache_func(0.2)
    def test2(name):
        return 'test2-%s-%f' % (name, time.time())
    
    last_v1 = 0
    last_v2 = 0
    last_v21 = 0

    for i in range(0, 3):
        v1 = test1(str(i))
        v2 = test2(str(i))
        v21 = test2(name=str(i))

        print('Test1:', v1)
        print('Test2:', v2)
        print('Test2:', v21)
        
        assert v2 == v21
        
        if i == 1:
            assert v2 == last_v2
            assert v21 == last_v21

        if i == 2:
            assert v2 != last_v2
            assert v21 != last_v21

        last_v1 = v1
        last_v2 = v2
        last_v21 = v21

        time.sleep(0.1)

 

if __name__ == '__main__':
    fs = list(globals().keys())
    for k in fs:
        if k.startswith('test_'):
            print('-'*6, k, '-'*6)
            globals()[k]()




