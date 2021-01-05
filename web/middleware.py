#!/usr/bin/env python
# -*- coding: utf-8 -*-
import traceback
import logging
import types
import time
import random

log = logging.getLogger()

class JSONPMiddleware:
    def before(self, viewobj, *args, **kwargs):
        return

    def after(self, viewobj, *args, **kwargs):
        input = viewobj.req.inputjson()
        if input.get('format', '') == 'jsonp':
            if viewobj.req.method.upper() == 'GET':
                viewobj.resp.headers['Content-Type'] = 'application/javascript; charset=UTF-8'
                callback = input.get('callback','callback')
                viewobj.resp.content = '%s(%s)' % (callback, viewobj.resp.content)

        elif input.get('format', '') == 'cors':
            origin = viewobj.req.environ.get('HTTP_ORIGIN','')
            if origin:
                viewobj.resp.headers['Access-Control-Allow-Origin'] = origin
                viewobj.resp.headers['Access-Control-Allow-Credentials'] = 'true'

        return viewobj.resp
JSONP = JSONPMiddleware

class DEBUGMiddleware:
    def before(self, viewobj, *args, **kwargs):
        return

    def after(self, viewobj, *args, **kwargs):
        #REQUEST
        #method
        log.debug('>> %s %s', viewobj.req.method, viewobj.req.path)
        #headers
        for k,v in viewobj.req.headers().items():
            log.debug('>> %s:%s',k,v)
        #body
        if viewobj.req.storage is not None:
            log.debug('=> %s',viewobj.req.storage.value)

        #RESPONSE
        log.debug('<< %s', viewobj.resp.status)
        for k,v in viewobj.resp.headers.items():
            log.debug('<< %s:%s',k,v)
        log.debug('<< Content-Length:%d',len(viewobj.resp.content))
        for c in viewobj.resp.cookies.values():
            log.debug('<< Set-Cookie:%s', c.OutputString())
        log.debug('<= %s', viewobj.resp.content)

        return viewobj.resp
DEBUG = DEBUGMiddleware

global_envs = []
global_envs_last_update = 0
class GRAY:
    def smart_type(self, value, value_type):
        '''
        value_type 是一个值
        将value转换成一样的类型
        '''
        if type(value_type) in (types.IntType, types.LongType):
            return int(value)
        elif type(value_type) == types.FloatType:
            return float(value)
        elif type(value_type) == types.UnicodeType and type(value) == types.StringType:
            return unicode(value, 'utf-8')
        elif type(value_type) == types.StringType:
            return str(value)
        else:
            return value

    def env_weight(self, env):
        '''
        过期时间应该设置短一些
        {
            'type': 'weight',
            'cookie': 'G',
            'expire': 3,
            'weight': 50,   # max 100
        }
        '''
        tmp = random.randint(1,100)
        return tmp < env['weight']

    def env_input(self, env):
        '''
        {
            'type': 'input',
            'cookie': 'G',
            'expire': 3,
            'rules': [
                ['a','>',10],
                ['req.path','=','/ping'],
            ],
        }
        '''
        from qfcommon.base.ruler import RuleSet


        input = self.viewobj.req.input().copy()
        input['req.host'] = self.viewobj.req.host
        input['req.method'] = self.viewobj.req.method
        input['req.path'] = self.viewobj.req.path
        input['req.query_string'] = self.viewobj.req.query_string
        input['req.clientip'] = self.viewobj.req.clientip()
        input['req.postdata'] = self.viewobj.req.postdata()

        rules = env['rules']

        # 保证规则都存在
        all_keys = input.keys()
        rule_keys = [i[0] for i in rules]
        if not set(rule_keys).issubset(set(all_keys)):
            log.debug('env set not match')
            return False


        # 对应转换类型
        for rule in rules:
            if rule[0] in input:
                input[rule[0]] = self.smart_type(input[rule[0]], rule[2])

        return RuleSet(rules).match(input)

    def before(self, viewobj, *args, **kwargs):
        return

    def after(self, viewobj, *args, **kwargs):
        try:
            from qfcommon.base import getconf
            global global_envs,global_envs_last_update
            self.viewobj = viewobj

            # 60秒更新一次
            if global_envs_last_update + 60 < int(time.time()):
                global_envs_last_update = int(time.time())
                global_envs = getconf.get_env()

            # 匹配规则并设置cookie
            for env in global_envs:
                func = getattr(self, 'env_%s' % env['type'], None)
                if func and func(env):
                    log.info('set env cookie: %s expire:%d', env['cookie'], env['expire'])
                    viewobj.resp.set_cookie('env',env['cookie'], max_age = env['expire'])
                    break
        except:
            log.error(traceback.format_exc())
        return viewobj.resp
