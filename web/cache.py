# coding: utf-8
import traceback
import time
from collections import UserDict
import threading, logging

log = logging.getLogger()
caches = None

class CacheDict (UserDict):
    def __init__(self, update_func, timeout=60):
        UserDict.__init__(self)
        self._cache_info = {}
        self._update_func = update_func
        self._timeout = timeout

    def __getitem__(self, key):
        data = self.data.get(key)
        info = self._cache_info.get(key)
        now = time.time()
        if not data or not info or now-info['last'] >= self._timeout:
            data = self._update_func(key, data)
            self._cache_info[key] = {'last':now}
            self.data[key] = data
        return data
 

def test5():
    
    def func(key, data):
        return 'name-%.3f' % time.time()

    c = CacheDict(func, 0.5)
    for i in range(0, 10):
        print(c['name'])
        time.sleep(.2)

if __name__ == '__main__':
    test5()



