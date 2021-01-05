# coding: utf-8
import sys, os
import re
import datetime, time
import traceback
import logging

log = logging.getLogger()

allow_ops = set(['=','>','>=','<','<=','!=','in','bt','match'])

allow_types = set([ 
    int,
    float,
    bytes,
    str,
    list,
    tuple,
    datetime.datetime,
    datetime.date,
])


class RuleExp:
    '''
    规则表达式
    eg:
        exp ('a', '>', 10)
    '''
    def __init__(self, exp, funcs):
        self.key = exp[0]
        self.op  = exp[1]
        self.value = exp[2]
        self.vtype = type(self.value)
        self.funcs = funcs

        global allow_types, allow_ops
        if self.op not in allow_ops:
            raise ValueError('op error: %s' % self.key)

        if self.vtype not in allow_types:
            raise TypeError('value type error: %s' % self.key)


    def __str__(self):
        return '%s %s %s' % (self.key, self.op, self.value)


    def check(self, data):
        v1 = None
        if self.key.endswith('()'):
            fname = self.key[:-2]
            v1 = self.funcs[fname](data)
        else:
            v1 = data
            keys = self.key.split('.')
            try:
                for k in keys:
                    v1 = v1[k]
            except:
                v1 = None
        if v1 is None:
            return False
        
        #log.debug('key:%s v1:%s', self.key, v1)
        if self.op == '>':
            return v1 > self.value
        elif self.op == '>=':
            return v1 >= self.value
        elif self.op == '<':
            return v1 < self.value
        elif self.op == '<=':
            return v1 <= self.value
        elif self.op == '=':
            return v1 == self.value
        elif self.op == '!=':
            return v1 != self.value
        elif self.op == 'in':
            return v1 in self.value
        elif self.op == 'bt':
            return self.value[0] < v1 <= self.value[1]
        elif self.op == 'match':
            return re.match(self.value, v1) != None


class RuleItem:
    '''
    一条规则。是规则表达式的集合。所有规则表达式之间是and的关系
    '''
    def __init__(self, rid, exps, result=None, funcs=None):
        '''
        eg:
          exps [('a', '>', 10), ('b', '!=', 11)]
          result {'a':10, '$b.name':'1111', '$c':3333}
        '''
        self.rid = rid
        self.exps = []
        self.result = result

        for e in exps:
            self.exps.append(RuleExp(e, funcs))

    def __str__(self):
        s = []
        for x in self.exps:
            s.append(str(x))
        return ','.join(s)

    def check(self, data):
        for e in self.exps:
            x = e.check(data)
            if not x:
                return False, None

        return True, self._gen_result(data)
        
    def _gen_result(self, data):
        result = {}
        for k,v in self.result.items():
            if v[0] == '$':
                keys = v[1:].split('.')
                v1 = data
                try:
                    for k1 in keys:
                        v1 = v1[k1]
                except:
                    v1 = None
                result[k] = v1
            else:
                result[k] = v
        return result 

class Ruler:
    '''
    规则
    ruleitems:
        [{'id':111, 'rule':[]}]
    '''
    def __init__(self, ruleitems):
        self.ruleitems = []
        self.funcs = {}

        for x in ruleitems:
            self.ruleitems.append(RuleItem(x['id'], x['rule'], x.get('result'), self.funcs))

    def __str__(self):
        s = [ str(x) for x in self.ruleitems ]
        return ','.join(s)

    def add_func(self, name, func):
        self.funcs[name] = func

    def check(self, data, match=1):
        '''
        match 
            1 第一次True就返回
            2 第一次False就返回
            3 所有都必须检查，返回所有True的
        '''
        ret = []
        for rt in self.ruleitems:
            #log.debug('rule item: %s', rt)
            try:
                x, result = rt.check(data)
            except:
                log.warn('rule exception rule:%s data:%s', rt, data)
                log.info(traceback.format_exc())
                continue

            if match == 1 and x:
                return [(x, rt.rid, result)]
            if match == 2 and not x:
                #return (x, rt.rid, result)
                break
            ret.append((x, rt.rid, result))


        if not ret and (match == 1 or match == 2):
            return None

        return [ x for x in ret if x[0] ] 



def test():
    from zbase3.base import logger
    global log
    log = logger.install('stdout')

    data = [
        {'name':'zh', 'age':100, 'time':'2018-01-01 12:22:10', 'info':{'m1':100, 'm2':'hehe'}},
        {'name':'zh2', 'age':100, 'time':'2018-01-01 12:22:10', 'info':{'m1':100, 'm2':'hehe'}},
        {'name':'zh', 'age':80, 'time':'2018-01-01 12:22:10', 'info':{'m1':100, 'm2':'hehe'}},
        {'name':'zh', 'age':110, 'time':'2018-01-01 12:22:10', 'info':{'m1':101, 'm2':'haha'}},
        {'name':'zh', 'age':99, 'info':{'m1':101, 'm2':'haha'}},
    ]
    rules = [
        {'id':1, 
         'rule':[('name','=','zh'), ('age','>',90), ('time','bt',('2018-01-01','2018-01-02')), ('info.m2','in',('hehe', 'haha'))], 
         'result':{'age':'$age', 'm1':'$info.m1', 'my':'me'}},

        {'id':2, 
         'rule':[('age','>',100), ('info.m2','in',('hehe', 'haha'))], 
         'result':{'age':'$age', 'm1':'$info.m1', 'name':'$name'}},

        {'id':3, 
         'rule':[('test1()','>',500), ('info.m2','in',('hehe', 'haha'))], 
         'result':{'age':'$age', 'm1':'$info.m1', 'name':'$name'}},
    ]

    def test1(data):
        return data['age']*10

    rule = Ruler(rules)
    rule.add_func('test1', test1)

    log.debug('rule:%s', rule)
    for x in data:
        log.debug('-'*80)
        log.debug('data:%s', x)
        log.debug('result:%s', rule.check(x, 3))

if __name__ == '__main__':
    test()



