#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @yushijun


import os
import email
import logging
import types
import urllib
import urllib.request
import http
import time
import io


log = logging.getLogger()

client = None
conn_pool = None

def timeit(func):
    def _(self, *args, **kwargs):
        starttm = time.time()
        code = 0
        content = ''
        err = ''
        try:
            retval = func(self, *args, **kwargs)
            code = self.code
            if '\0' in self.content:
                content = '[binary data %d]' % len(self.content)
            else:
                content = self.content[:4000]
            return retval
        except Exception as e:
            err = str(e)
            raise
        finally:
            endtm = time.time()
            log.info('server=HTTPClient|name=%s|func=%s|code=%s|time=%d|args=%s|kwargs=%s|err=%s|content=%s',
                     self.name,func.__name__,str(code),
                     int((endtm-starttm)*1000000),
                     str(args),str(kwargs),
                     err,content)
    return _

def install(name, **kwargs):
    global client
    x = globals()
    for k in x.keys():
        v = x[k]
        if type(v) == types.ClassType and v != HTTPClient and issubclass(v, HTTPClient):
            if v.name == name:
                client = v(**kwargs)
                return client

def utf8urlencode(data):
    #tmp = {}
    #for k,v in data.items():
    #    tmp[k.encode('utf-8') if isinstance(k, unicode) else str(k)] = \
    #        v.encode('utf-8') if isinstance(v, unicode) else str(v)
    #return urllib.parse.urlencode(tmp)
    return urllib.parse.urlencode(data)

def dict2xml(root, sep='', cdata=True, encoding='utf-8'):
    '''sep 可以为 \n'''
    xml = ''
    for key in sorted(root.keys()):
        #if isinstance(key, unicode):
        #    u_key = key.encode(encoding)
        #else:
        #    u_key = str(key)
        u_key = key
        if isinstance(root[key], dict):
            xml = '%s<%s>%s%s</%s>%s' % (xml, u_key, sep, dict2xml(root[key], sep), u_key, sep)
        elif isinstance(root[key], list):
            xml = '%s<%s>' % (xml, u_key)
            for item in root[key]:
                xml = '%s%s' % (xml, dict2xml(item,sep))
            xml = '%s</%s>' % (xml, u_key)
        else:
            value = root[key]
            #if isinstance(value, unicode):
            #    value = value.encode(encoding)

            if cdata:
                xml = '%s<%s><![CDATA[%s]]></%s>%s' % (xml, u_key, value, u_key, sep)
            else:
                xml = '%s<%s>%s</%s>%s' % (xml, u_key, value, u_key, sep)
    return xml


class HTTPClient:
    code = 0
    content = ''
    headers = {}
    charset = 'utf-8'

    def __init__(self, verify_ssl_certs=False, timeout=10, conn_pool=False, allow_redirect=False):
        self._verify_ssl_certs = verify_ssl_certs
        self._timeout = timeout
        self._conn_pool = conn_pool
        self._allow_redirect = allow_redirect

    @timeit
    def get(self, url, params={}, **kwargs):
        if params:
            if '?' in url:
                url = url + '&' + utf8urlencode(params)
            else:
                url = url + '?' + utf8urlencode(params)

        header = {}
        if 'headers' in kwargs:
            header.update(kwargs.pop('headers'))

        content, code, headers = self.request('get', url, header, **kwargs)

        return content

    @timeit
    def put(self, url, params={}, **kwargs):
        header = {
            'Content-Type':'application/x-www-form-urlencoded'
        }
        if 'headers' in kwargs:
            header.update(kwargs.pop('headers'))

        put_data = utf8urlencode(params)
        content, code, headers = self.request('put', url, header, put_data, **kwargs)

        return content

    @timeit
    def post(self, url, params={}, **kwargs):
        header = {
            'Content-Type':'application/x-www-form-urlencoded'
        }
        if 'headers' in kwargs:
            header.update(kwargs.pop('headers'))

        post_data = utf8urlencode(params)
        content, code, headers = self.request('post', url, header, post_data, **kwargs)

        return content

    @timeit
    def post_json(self, url, json_dict={}, escape = True, **kwargs):
        import json

        header = {
            'Content-Type':'application/json'
        }
        if 'headers' in kwargs:
            header.update(kwargs.pop('headers'))

        if isinstance(json_dict, dict):
            post_data = json.dumps(json_dict, ensure_ascii = escape)
        else:
            post_data = json_dict

        #if isinstance(post_data, unicode):
        #    post_data = post_data.encode('utf-8')

        log.debug('post_data=%s', post_data)

        content, code, headers = self.request('post', url, header, post_data, **kwargs)

        return content

    @timeit
    def post_xml(self, url, xml={}, **kwargs):

        header = {
            'Content-Type':'application/xml',
        }
        if 'headers' in kwargs:
            header.update(kwargs.pop('headers'))

        if isinstance(xml, dict):
            xml = dict2xml(xml)
        #if isinstance(xml, unicode):
        #    xml = xml.encode('utf-8')

        log.debug('post_data=%s', xml)

        content, code, headers = self.request('post', url, header, xml, **kwargs)

        return content

    @timeit
    def delete(self, url, params={}, **kwargs):
        header = {
            'Content-Type':'application/x-www-form-urlencoded'
        }
        if 'headers' in kwargs:
            header.update(kwargs.pop('headers'))

        post_data = utf8urlencode(params)
        content, code, headers = self.request('delete', url, header, post_data, **kwargs)

        return content


    def request(self, method, url, headers, post_data=None, **kwargs):
        raise NotImplementedError(
            'HTTPClient subclasses must implement `request`')

class Urllib3Client(HTTPClient):
    name = 'urllib3'

    def request(self, method, url, headers, post_data=None,  **kwargs):
        import urllib3
        urllib3.disable_warnings()

        pool_kwargs = {}
        if self._verify_ssl_certs:
            pool_kwargs['cert_reqs'] = 'CERT_REQUIRED'
            pool_kwargs['ca_certs'] = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data/ca-certificates.crt')

        if self._allow_redirect:
            kwargs['redirect'] = True
        else:
            kwargs['redirect'] = False

        # 如果是长连接模式
        if self._conn_pool:
            global conn_pool
            if not conn_pool:
                conn_pool = urllib3.PoolManager(num_pools=max(100, self._conn_pool), maxsize=max(100, self._conn_pool), **pool_kwargs)
            conn = conn_pool
        else:
            conn = urllib3.PoolManager(**pool_kwargs)

        result = conn.request(method=method, url=url, body=post_data, headers=headers, timeout=self._timeout, retries=False, **kwargs)

        self.content, self.code, self.headers = result.data.decode(self.charset), result.status, result.headers

        return self.content, self.code, self.headers

class RequestsClient(HTTPClient):
    name = 'requests'
    

    @timeit
    def post_file(self, url, data={}, files={}, **kwargs):
        '''
        requests发文件方便一些  就不实现协议报文了
        '''
        header = {
        }
        if 'headers' in kwargs:
            header.update(kwargs.pop('headers'))

        content, code, headers = self.request('post', url, header, post_data=data, files=files, **kwargs)

        return content

    def request(self, method, url, headers, post_data=None,  **kwargs):

        # 如果是长连接模式
        if self._conn_pool:
            global conn_pool
            if not conn_pool:
                import requests
                conn_pool = requests.Session()
            requests = conn_pool
        else:
            import requests


        if self._verify_ssl_certs:
            kwargs['verify'] = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data/ca-certificates.crt')
        else:
            kwargs['verify'] = False

        if self._allow_redirect:
            kwargs['allow_redirects'] = True
        else:
            kwargs['allow_redirects'] = False

        result = requests.request(method,
                                  url,
                                  headers=headers,
                                  data=post_data,
                                  timeout=self._timeout,
                                  **kwargs)

        self.content, self.code, self.headers = result.content.decode(self.charset), result.status_code, result.headers

        return self.content, self.code, self.headers

class PycurlClient(HTTPClient):
    name = 'pycurl'
    charset = 'utf-8'

    def _curl_debug_log(self, debug_type, debug_msg):
        debug_types = ('I', '<', '>', '<', '>')
        if debug_type == 0:
            log.debug('%s', debug_msg.strip())
        elif debug_type in (1, 2):
            for line in debug_msg.splitlines():
                log.debug('%s %s', debug_types[debug_type], line)
        elif debug_type == 4:
            log.debug('%s %r', debug_types[debug_type], debug_msg)

    def parse_headers(self, data):
        if '\r\n' not in data:
            return {}
        raw_headers = data.split('\r\n', 1)[1]
        headers = email.message_from_string(raw_headers)
        return dict((k.title(), v) for k, v in dict(headers).items())

    def request(self, method, url, headers, post_data=None, **kwargs):
        import pycurl

        #s = io.StringIO()
        s = io.BytesIO()
        #rheaders = io.StringIO()
        rheaders = io.BytesIO()
        curl = pycurl.Curl()

        # 详细log
        curl.setopt(pycurl.VERBOSE, 1)
        curl.setopt(pycurl.DEBUGFUNCTION, self._curl_debug_log)

        #if type(url) == types.UnicodeType:
        #    url = url.encode('utf-8')

        if method == 'get':
            curl.setopt(pycurl.HTTPGET, 1)
        elif method == 'post':
            curl.setopt(pycurl.POST, 1)
            curl.setopt(pycurl.POSTFIELDS, post_data)
        else:
            curl.setopt(pycurl.CUSTOMREQUEST, method.upper())

        curl.setopt(pycurl.URL, url)
        curl.setopt(pycurl.WRITEFUNCTION, s.write)
        curl.setopt(pycurl.HEADERFUNCTION, rheaders.write)
        curl.setopt(pycurl.NOSIGNAL, 1)
        curl.setopt(pycurl.CONNECTTIMEOUT, 30)
        curl.setopt(pycurl.TIMEOUT, self._timeout)
        curl.setopt(pycurl.HTTPHEADER, ['%s: %s' % (k, v)
                    for k, v in headers.items()])
        if self._verify_ssl_certs:
            curl.setopt(pycurl.CAINFO, os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data/ca-certificates.crt'))
        else:
            curl.setopt(pycurl.SSL_VERIFYHOST, False)

        #特殊参数
        if 'ext' in kwargs:
            for k,v in kwargs['ext']:
                curl.setopt(k,v)

        curl.perform()

        # 记录时间啦
        http_code = curl.getinfo(pycurl.HTTP_CODE)
        http_conn_time =  curl.getinfo(pycurl.CONNECT_TIME)
        http_dns_time = curl.getinfo(pycurl.NAMELOOKUP_TIME)
        http_pre_tran =  curl.getinfo(pycurl.PRETRANSFER_TIME)
        http_start_tran =  curl.getinfo(pycurl.STARTTRANSFER_TIME)
        http_total_time = curl.getinfo(pycurl.TOTAL_TIME)
        http_size = curl.getinfo(pycurl.SIZE_DOWNLOAD)
        log.info('func=pycurl_time|http_code=%d|http_size=%d|dns_time=%d|conn_time=%d|pre_tran=%d|start_tran=%d|total_time=%d'%(
                http_code,http_size,int(http_dns_time*1000000),int(http_conn_time*1000000),
                int(http_pre_tran*1000000),int(http_start_tran*1000000),int(http_total_time*1000000)))

        rbody = s.getvalue()
        rcode = curl.getinfo(pycurl.RESPONSE_CODE)

        self.content, self.code, self.headers = rbody.decode(self.charset), rcode, self.parse_headers(rheaders.getvalue().decode(self.charset))

        return self.content, self.code, self.headers


class UrllibClient(HTTPClient):
    name = 'urllib'

    def request(self, method, url, headers, post_data=None, handlers=[], **kwargs):
        import ssl

        req = urllib.request.Request(url, post_data, headers)

        if method not in ('get', 'post'):
            req.get_method = lambda: method.upper()
        try:
            if not self._verify_ssl_certs and hasattr(ssl, 'SSLContext'):
                # python 2.7.9 之前没有完善的ssl支持 开启验证也不会验证
                # 这里 verify_ssl_certs=False 仅用于调试
                response = urllib.request.urlopen(req, timeout=self._timeout, context=ssl._create_unverified_context(), **kwargs)
            else:
                opener = urllib.request.build_opener(*handlers)
                response = opener.open(req,timeout=self._timeout, **kwargs)

            rbody = response.read()
            rcode = response.code
            headers = dict((k.title(),v) for k,v in dict(response.info()).items())
        except urllib.request.HTTPError as e:
            log.info('response from %s', e.fp.fp._sock.fp._sock.getpeername())
            rbody = e.read()
            rcode = e.code
            headers = dict((k.title(),v) for k,v in dict(e.info()).items())

        self.content, self.code, self.headers = rbody.decode(self.charset), rcode, headers

        return self.content, self.code, self.headers

# 为了兼容
Urllib2Client = UrllibClient

#---------------------------
#   一些工具函数
#---------------------------

class HTTPSClientAuthHandler (urllib.request.HTTPSHandler):
    '''
    https 双向验证handler  用于urllib
    Urllib2Client().post('https://api.mch.weixin.qq.com/secapi/pay/refund', handlers=[HTTPSClientAuthHandler('apiclient_key.pem', 'apiclient_cert.pem')])
    '''
    def __init__(self, key, cert):
        urllib.request.HTTPSHandler.__init__(self)
        self.key = key
        self.cert = cert

    def https_open(self, req):
        return self.do_open(self.getConnection, req)

    def getConnection(self, host, timeout=300):
        return http.client.HTTPSConnection(host, key_file=self.key, cert_file=self.cert)

    def __str__(self):
        return '<HTTPSClientAuthHandler key=%s cert=%s>' % ( self.key, self.cert )
    __repr__ = __str__



#----------TEST------------------

def test_get():
    PycurlClient().get('http://httpbin.org/ip')
    RequestsClient().get('http://httpbin.org/ip')
    Urllib2Client().get('http://httpbin.org/ip')
    Urllib3Client().get('http://httpbin.org/ip')

def test_post():
    PycurlClient().post('http://baidu.com',{'a':'1'})
    RequestsClient().post('http://baidu.com',{'a':'1'})
    Urllib2Client().post('http://baidu.com',{'a':'1'})
    Urllib3Client().post('http://baidu.com',{'a':'1'})

def test_post_json():
    PycurlClient().post_json('http://baidu.com',{'a':'1'})
    RequestsClient().post_json('http://baidu.com',{'a':'1'})
    Urllib2Client().post_json('http://baidu.com',{'a':'1'})
    Urllib3Client().post_json('http://baidu.com',{'a':'1'})

def test_post_xml():
    PycurlClient().post_xml('http://baidu.com',{'a':'1'})
    RequestsClient().post_xml('http://baidu.com',{'a':'1'})
    Urllib2Client().post_xml('http://baidu.com',{'a':'1'})
    Urllib3Client().post_xml('http://baidu.com',{'a':'1'})

def test_install():
    c = install('urllib2')
    c.get('http://baidu.com')
    c.get('http://baidu.com')
    c.get('http://baidu.com')

def test_long_conn():
    for i in range(5):
        RequestsClient(allow_redirect=True,conn_pool = True,verify_ssl_certs = True).get('https://httpbin.org/headers')
    global conn_pool
    conn_pool = None
    for i in range(5):
        Urllib3Client(allow_redirect=True,conn_pool = True,verify_ssl_certs = True).get('https://httpbin.org/headers')

def test_headers():
    for client in [PycurlClient, RequestsClient, Urllib2Client, Urllib3Client]:
        c = client()
        c.get('http://baidu.com',headers={'X-testtest': 'test'})
        print(c.headers)

def test_urlencode():
    a = {
        '你好':u'你hhhh好',
        u'你':u'你hhhh好',
    }
    print(utf8urlencode(a))
    b = {
        't':'test',
        'g':'gogo',
    }
    print(utf8urlencode(b))

def test_binary():
    Urllib2Client().get('https://www.baidu.com/img/bd_logo1.png')
    Urllib2Client().get('http://baidu.com')

def test_post_file():
    RequestsClient().post_file('http://httpbin.org/post', {'key1':'value1'}, files={'file1': open('__init__.py', 'rb')})

def test_urllib3():
    Urllib3Client().post_xml('http://127.0.0.1:9020/a/b/c',{'a':'1'})
    Urllib3Client(conn_pool=True).post_xml('http://127.0.0.1:9020/a/b/c',{'a':'1'})

if __name__ == '__main__':
    import logger
    logger.install('stdout')

    test_get()
    # test_post()
    # test_post_json()
    #test_post_xml()
    # test_install()
    # test_long_conn()
    # test_headers()
    # test_urlencode()
    # test_binary()
    # test_post_file()
    # test_urllib3()

