# coding:utf-8
import os, sys
HOME = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(HOME)), 'conf'))
import json
import urllib
import urllib.request
import pprint
from zbase3.base import dbpool, logger
from zbase3.utils import createid
import config_debug
import datetime, time
import urllib
import urllib.parse
from urllib.parse import urlparse

log = logger.install('stdout')
dbpool.install(config_debug.DATABASE)

class MyRequest (urllib.request.Request):
    method = 'GET'
    def get_method(self):
        return self.method


class HTTPClient:
    def __init__(self, baseurl='http://127.0.0.1'):
        self.baseurl = baseurl
        self.cookie = ''

    def open(self, urlpath, method='GET', values=None):
        print('\33[0;33m' + '='*30 + '\33[0m')
        print('>>>>')

        url = self.baseurl.rstrip('/') + '/' + urlpath.lstrip('/')
        print(method, url)
        if values:
            print('values:', values)

        netloc = urlparse(url).netloc

        data = None
        if values:
            data = urllib.parse.urlencode(values).encode('utf-8')
        headers = {
            'User-Agent': 'testclient',
            #'Cookie': 'sid=%d'
        }
        if self.cookie:
            headers['Cookie'] = self.cookie

        #req = MyRequest(url, data, headers)
        req = MyRequest(url, data, headers=headers)
        req.method = method
        print('<<<<')

        ret = {}
        try:
            resp = urllib.request.urlopen(req)
        except Exception as e:
            #print(e.code)
            print(e)
            raise
        else:
            print(resp.code)
            #print resp.headers
            c = resp.headers.get('Set-Cookie')
            if c:
                self.cookie = c.split(';')[0]
                print('cookie:', self.cookie)

            s = resp.read()
            print('rawdata:', s)
            ret = json.loads(s)
            #pprint.pprint(ret)
            print(json.dumps(ret, indent=2))

            return ret

    def _make_args(self, urlpath, **args):
        params = []

        print('args:', args)
        for k,v in args.items():
            if isinstance(v, bytes):
                params.append('%s=%s' % (k, v))
            elif isinstance(v, str):
                if ',' in v and '__' not in k:
                    params.append('%s__in=%s' % (k, urllib.parse.quote(v.encode('utf-8'))))
                else:
                    params.append('%s=%s' % (k, urllib.parse.quote(v.encode('utf-8'))))
            else:
                params.append('%s=%s' % (k, str(v)))
        if params:
            urlpath = urlpath + '?' + '&'.join(params)

        return urlpath


if __name__ == '__main__':
    c = HTTPClient()
    c.ping()



