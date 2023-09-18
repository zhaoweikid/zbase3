# coding: utf-8
import os, sys
import functools
import inspect
import logging
import re
import traceback

from zbase3.base.excepts import ParamError
from zbase3.web.core import HandlerFinish

log = logging.getLogger()

T_MUST = 0 # ?
T_INT = 1
T_FLOAT = 2
T_STR = 4
T_REG = 8
T_LIST = 16
T_DICT = 32
# 从这以后都是各种特殊定义正则类型
T_MAIL = 100 << 16
T_IP = 101 << 16
T_MOBILE = 102 << 16
T_DATE = 103 << 16
T_DATETIME = 104 << 16
T_TIMESTAMP = 105 << 16
T_PASSWORD = 106 << 16

TYPE_MAP = {
    T_MAIL: re.compile("^[a-zA-Z0-9_\-\'\.]+@[a-zA-Z0-9_]+(\.[a-z]+){1,2}$"),
    T_IP: re.compile("^([0-9]{1,3}\.){3}[0-9]{1,3}$"),
    T_MOBILE: re.compile("^1[0-9]{10}$"),
    T_DATE: re.compile("^[0-9]{4}(\-|/)[0-9]{1,2}(\-|/)[0-9]{1,2}$"),
    T_DATETIME: re.compile("^[0-9]{4}(\-|/)[0-9]{2}(\-|/)[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}$"),
    T_TIMESTAMP: re.compile("^[0-9]{1,10}$"),
    T_PASSWORD: re.compile(
        "^(?![0-9]+$)(?![a-zA-Z]+$)[0-9A-Za-z\:\;\<\>\,\.\?\/\~\!\@\#\$\%\^\&\*\(\)\-\_\+\=]{6,20}$"),
}

opmap = {'eq': '=',
         'lt': '<',
         'gt': '>',
         'ne': '<>',
         'le': '<=',
         'ge': '>=',
         'in': 'in',
         'bt': 'between',
         'lk': 'like',
         }

# 转换key，value为支持op的形式
def trans_keyval(key, value):
    if '__' in key:
        k_name, k_op = key.split('__')
        op = opmap.get(k_op)
        if not op:  # k_name error
            raise ValueError('{0} error'.format(key))
        if k_op in ('bt', 'in'):
            v = value.split(',')
        
        return k_name, [op, v]
    else:
        return key, ['=', value]



class Field:
    def __init__(self, name='_', valtype=T_STR, must=False, default=None, **options):
        self.name = name
        self.type = valtype  # 值类型, 默认为字符串
        self.must = must  # 是否必须有值不能为空
        #self.op = '='
        self.default = default # 缺省值

        # 扩展信息
        #self.show = ''  # 字段显示名
        #self.method = ''  # http 方法
        self.match = ''  # 正则匹配
        #self.attr = None  # 字段属性，用来过滤
        #self.error = ''  # 错误信息
        self.choice = None  # 值枚举值
        self.subs = [] # 只有T_LIST和T_DICT有用
        self.list_count = options.get('count', 0)

        self.__dict__.update(options)

        # T_MAIL 以后都是正则定义的特殊字符串类型
        if valtype >= T_MAIL:
            self.match = TYPE_MAP[valtype]

        if self.match and isinstance(self.match, str):
            self.match = re.compile(self.match)

    def __str__(self):
        match = ''
        if self.match:
            match = self.match.pattern
        return '%s type:%d match:%s must:%d op:%s default:%s' % \
               (self.name, self.type, match, self.must, self.op, self.default)

    def check(self, val, trans_type=True):
        if self.type == T_INT:
            ret = int(val)
            if not trans_type and not isinstance(val, int):
                log.debug('validator int error: %s=%s', self.name, str(val))
                raise ValidatorError(self.name) 
        elif self.type == T_FLOAT:
            ret = float(val)
            if not trans_type and not isinstance(val, float):
                log.debug('validator float error: %s=%s', self.name, str(val))
                raise ValidatorError(self.name) 
        elif self.type == T_STR:
            if self.match and not self.match.match(val):
                log.debug('validator str match error: %s=%s', self.name, str(val))
                raise ValidatorError(self.name)
            if not isinstance(val, str):
                log.debug('validator str error: %s=%s %s', self.name, str(val), type(val))
                raise ValidatorError(self.name)

            ret = val
        elif self.type == T_LIST:
            ret = []
            for x in val:
                ret.append(self.subs[0].check(x, trans_type))
            if self.list_count > 0 and len(ret) != self.list_count:
                log.debug('list %s count error, must %d', self.name, self.list_count)
                raise ValidatorError(self.name)
        elif self.type == T_DICT:
            ret = {}
            for x in self.subs:
                ret[x.name] = x.check(val[x.name], trans_type)
        else: # 非基础类型都是正则
            if not self.match.match(val):
                log.debug('validator match error: %s=%s', self.name, str(val))
                raise ValidatorError(self.name)
            ret = val

        # 枚举值校验 只处理STR FLOAT INT
        if self.type <= T_STR and self.choice:
            if ret not in self.choice:
                choice = ','.join(map(str, self.choice))
                log.debug('validator choice error: {0}={1} not in ({2})'.format(self.name, str(val), choice))
                raise ValidatorError(self.name)

        return ret



F = Field


class ValidatorError(Exception):
    pass


class Validator:
    def __init__(self, fields=None):
        # fields must have must,type,match,name
        self._fields = []
        for f in fields:
            if isinstance(f, str):
                self._fields.append(Field(name=f))
            else:
                self._fields.append(f)

        self.data = {}

    def _trans_input(self, inputdata):
        # 把输入数据中的 key__op=value 转换为 {key: [op, value]}
        _input = {}
        for k, v in inputdata.items():
            key, value = trans_keyval(k, v)
            _input[key] = value
        return _input

    # 验证字典里的字段和类型
    def verify(self, inputdata):
        result = []
        
        _input = self._trans_input(inputdata)
        log.debug('input: %s', _input)

        for f in self._fields:
            try:
                kname = f.name
                val = _input.get(kname)
                if val is None: # 没有此字段
                    if f.must:  # 要求必须有
                        result.append(kname)
                    elif not f.default is None:
                        self.data[kname] = f.default
                    continue

                op, v = val
                if isinstance(v, list):
                    self.data[kname] = (op, [ f.check(x) for x in v])
                else:
                    self.data[kname] = f.check(v)
            except ValidatorError:
                result.append(f.name)
                #log.warning(traceback.format_exc())
            except ValueError:
                result.append(f.name)
            except:
                result.append(f.name)
                log.info(traceback.format_exc())
        return result

    # 验证字典里的字段和类型
    def verify_dict(self, inputdata):
        result = []
        
        for f in self._fields:
            try:
                kname = f.name
                val = inputdata.get(kname)
                log.debug('name:{0} {1}'.format(kname, val))

                if val is None: # 没有此字段
                    if f.must:  # 要求必须有
                        result.append(kname)
                    elif not f.default is None:
                        self.data[kname] = f.default
                    continue
                self.data[kname] = f.check(val)
            except ValidatorError:
                result.append(f.name)
            except ValueError:
                result.append(f.name)
            except:
                result.append(f.name)
                log.info(traceback.format_exc())
        return result



    def report(self, result, sep=u'<br/>'):
        return u'输入错误! ' + sep.join([ str(x) for x in result if x])


def with_validator(fields):
    def f(func):
        '''validator'''
        def _(self, *args, **kwargs):
            '''validator'''
            vdt = Validator(fields)
            self.validator = vdt

            if hasattr(self, 'input'):
                ret = vdt.verify(self.input())
            else:
                ret = vdt.verify(self.req.input(True))

            self.data = self.validator.data

            if ret:
                log.info('validator fail:%s', ret)
                errfunc = getattr(self, 'input_error', None)
                if errfunc:
                    errfunc(ret)
                else:
                    self.resp.status = 400
                    self.resp.write('输入参数错误: ' + ','.join(ret))
                raise ValidatorError('input error:'+ str(ret))
                #raise HandlerFinish(400, 'validator error:' + str(ret))
            return func(self, *args, **kwargs)

        return _

    return f


def with_validator_self(names):
    def f(func):
        '''validator'''
        def _(self, *args, **kwargs):
            '''validator'''
            allfields = self.validator_fields
            myfields = [] 
            if isinstance(names, str):
                mynames = names.split(',')
            elif isinstance(names, (list,tuple)):
                mynames = names
            else:
                raise ValidatorError("输入错误，{0}的参数错误".format(func.__name__))

            for f in allfields:
                if f.name in mynames:
                    myfields.append(f)
                
            vdt = Validator(myfields)
            self.validator = vdt
            if hasattr(self, 'input'):
                ret = vdt.verify(self.input())
            else:
                ret = vdt.verify(self.req.input())
            self.data = self.validator.data
            if ret:
                log.info('validator fail: %s', ret)
                # log.debug('err:%s', errfunc(ret))
                errfunc = getattr(self, 'input_error', '')
                if errfunc:
                    errfunc(ret)
                else:
                    self.resp.status = 400
                    self.resp.write('输入参数错误')
                raise ValidatorError('input error:'+ str(ret))
                #raise HandlerFinish(400, 'validator error:' + str(ret))
            return func(self, *args, **kwargs)

        return _

    return f

def with_validator_dict(fields):
    def f(func):
        '''validator'''
        func.__httpfunc = True
        def _(self, *args, **kwargs):
            '''validator'''
            vdt = Validator(fields)
            self.validator = vdt

            if hasattr(self, 'input'):
                _indata = self.input()
            else:
                _indata = self.req.postdata()

            ret = vdt.verify_dict(_indata)
            self.data = self.validator.data

            if ret:
                log.info('validator fail:%s', ret)
                errfunc = getattr(self, 'input_error', None)
                if errfunc:
                    errfunc(ret)
                else:
                    self.resp.status = 400
                    self.resp.write('input error: ' + ','.join(ret))
                raise ValidatorError('input error:'+ str(ret))
                #raise HandlerFinish(400, 'validator error:' + str(ret))
            return func(self, *args, **kwargs)

        return _

    return f




def is_empty(v):
    return v is inspect._empty


def is_args_kw(param):
    return param.kind in (inspect._VAR_POSITIONAL, inspect._VAR_KEYWORD)


def with_anno_check(func):
    params = inspect.signature(func).parameters
    names = tuple(name for name, param in params.items() if not is_args_kw(param))

    @functools.wraps(func)
    def wrapper(*args, **kw):
        if len(args) > len(names):
            raise ParamError('params too many')

        check_fields = []
        _input = {names[i]: v for i, v in enumerate(args)}
        _input.update(kw)

        fields_map = {int: T_INT, float: T_FLOAT, str: T_STR}
        for key in params:
            param = params[key]
            anno = param.annotation
            default = None if is_empty(param.default) else param.default
            if isinstance(anno, Field):
                check_fields.append(anno)
            elif anno in fields_map:
                check_fields.append(Field(param.name, fields_map[anno], default=default))
            elif isinstance(anno, int):
                check_fields.append(Field(
                    param.name, anno, must=is_empty(param.default), default=default
                ))
            elif not is_args_kw(param) and is_empty(anno) and is_empty(param.default):
                # 这里T_MUST是什么意思呢
                check_fields.append(Field(param.name, valtype=T_STR, must=True))

        validator = Validator(check_fields)
        ret = validator.verify(_input)
        if ret:
            raise ParamError(validator.report(ret))
        _input.update(validator.data)

        self = _input.get('self', None)
        if self:
            self.data = {k: v for k, v in _input.items() if k != 'self'}
            #setattr(self, 'anno_data', {k: v for k, v in _input.items() if k != 'self'})

        return func(**_input)

    return wrapper


def test_simple():
    from zbase3.base import logger
    log = logger.install('stdout')

    fields = [Field('age', T_INT),
              Field('money', T_FLOAT),
              Field('name'),
              Field('cate', T_INT),
              Field('income', T_INT),
              Field('test', T_INT),
              ]

    input = {'name': 'aaaaa', 'age': '12', 'money': '12.44',
             'cate__in': '1,2,3', 'income__bt': '1000,5000',
             'no_tesst': '123'}

    x = Validator(fields)
    ret = x.verify(input)

    if ret:
        for q in ret:
            log.debug(q)
    else:
        log.debug('check ok')

    #for f in x._fields:
    #    log.debug('name:%s, value:%s, valuetype:%s, op:%s' % (f.name, f.value, type(f.value), f.op))


def test_class():
    from zbase3.base import logger
    log = logger.install('stdout')

    class Request:
        def input(self):
            return {'name': 'aaaaa', 'age': '12', 'money': '12.44'}

    class Test:
        validator_fields = [
            F('age', T_INT),
            F('money', T_INT),
            F('name'),
        ]

        def __init__(self):
            self.req = Request()

        @with_validator_self("name,age")
        def GET(self):
            log.info('testfunc ...')

        def input_error(self, data):
            log.info('input error ...')

    t = Test()
    t.GET()
    log.info('after validator: %s', t.validator.data)


def test_choice():
    from zbase3.base import logger
    log = logger.install('stdout')

    fields = [
        Field('age', T_INT, must=False, default=18, choice=[1, 2, 3]),
        Field('name', T_STR, must=True, choice=['xiaom', 'xiaoz', 'xiaoh']),
        Field('money', T_FLOAT, choice=[12.123, 234.121]),
    ]
    # error aaaa 12
    input = {'name': 'aaaa', 'money': '12'}
    v = Validator(fields)
    ret = v.verify(input)
    log.debug(f'{ret} {v.data}')
    assert ret == ['name', 'money']
    print('-----')

    input = {'name': 'xiaom', 'money': '12.123'}
    v = Validator(fields)
    ret = v.verify(input)
    log.debug(f'{ret} {v.data}')
    assert ret == []
    print('-----')

    # error age
    input = {'name': 'xiaom', 'money': '12.123', 'age': '4'}
    v = Validator(fields)
    ret = v.verify(input)
    log.debug(f'{ret} {v.data}')
    assert ret == ['age']
    # print(ret)
    # print(v.data)
    input = {}
    fields = [
        Field('age', T_INT, must=False, default=18, choice=[12]),
        Field('name', T_STR, must=True, choice=['123']),
        Field('money', T_INT, choice=[123]),
        Field('title', T_REG, match='.{3,20}', choice=[123]),
    ]
    input['title'] = '1111111'
    input['money'] = '1111111'
    v = Validator(fields)
    ret = v.verify(input)
    log.debug(ret)


def test_verify():
    from zbase3.base import logger
    log = logger.install('stdout')

    fields = [
        Field('age', T_INT, must=False, default=18),
        Field('name', T_STR, must=True),
        Field('money', T_INT),
    ]
    input = {'name': 'aaaa', 'money': '12'}
    v = Validator(fields)
    ret = v.verify(input)
    # print(ret)
    # print(v.data)
    fields = [
        Field('age', T_INT, must=False, default=18),
        Field('name', T_STR, must=True),
        Field('money', T_INT),
        Field('title', T_REG, match='.{3,20}'),
    ]
    input['title'] = '1111111'
    v = Validator(fields)
    ret = v.verify(input)
    # print(ret)
    # print(v.data)


def test_withval():
    from zbase3.base import logger
    log = logger.install('stdout')
    from zbase3.web.httpcore import Response

    class Req:
        def __init__(self, data):
            self.data = data

        def input(self, flag):
            return self.data

    class Test:
        def __init__(self):
            self.req = Req({'name': 'aaaaa', 'age': '12', 'money': '12.44'})
            self.resp = Response()

        @with_validator([F('age', T_INT), F('money', T_INT), F('name'), ])
        def testfunc(self):
            log.info('testfunc ...')

        @with_validator([F('age', T_INT), F('money', T_FLOAT), F('name'), ])
        def testfunc2(self):
            log.info('testfunc2 ...')

        @with_validator([F('age', T_INT), F('money', T_FLOAT), F('name', T_STR), ])
        def testfunc3(self):
            log.info('testfunc3 ...')

    t = Test()
    try:
        t.testfunc()
    except ValidatorError:
        pass
    log.info('after validator: %s', t.validator.data)
    try:
        t.testfunc2()
    except ValidatorError:
        pass
    log.info('after validator: %s', t.validator.data)

    try:
        t.testfunc3()
    except ValidatorError:
        pass

    log.info('after validator: %s', t.validator.data)


def test_anno():
    from zbase3.base import logger
    log = logger.install('stdout')
    
    class Test:
        def __init__(self):
            self.id = 1

        @with_anno_check
        def test_fn(
                self,
                nickname,
                sex: Field('sex', T_STR, must=True, choice=['1', '2']),
                likes: list,
                age: int = 123,
                score: float = 1.0,
                mail: T_MAIL = 'yyk@qq.com',
                mobile: T_MOBILE = '18513504945',
                userid: int = 123,
                **kw
        ):
            print('self.id', self.id)
            print(f'sex: {sex}')
            print('nickname', type(nickname), nickname)
            print('age', type(age), age)
            print('score', type(score), score)
            print('mail', type(mail), mail)
            print('mobile', type(mobile), mobile)
            print('userid', type(userid), userid)
            print('kw', type(kw), kw)
            print(f'likes: {likes} {type(likes)}')

        def fn1(self, a, b, c, d=1, **kw):
            print(self.data)

    t = Test()
    t.test_fn("123", '1', [1, 2, 3], "123")
    log.info('anno_data: %s', t.data)

    t.test_fn("1", "1", [1, 2, 3])
    log.info('anno_data: %s', t.data)

    with_anno_check(t.fn1.__func__)(t, 'a', 'b', 'c')

    # test_fn2('nickname', 'age', '1.0', 2.0, 3.0, 4.0, 5.0)

def test_dict():
    from zbase3.base import logger
    log = logger.install('stdout')

    class Req:
        def input(self, flag):
            return {
                'name': 'aaaaa', 
                'age': 12, 
                'money': 12.44, 
                'friends':['hanmeimei', 'lilei'],
                'toys':{
                    'car':['volvo','xpeng'],
                    'like':{
                        'size': [20, 30],
                        'count':10,
                    }
                },
                'notnot':['aaaa', 'bbbb'],
            }

    class Test:
        def __init__(self):
            self.req = Req()

        @with_validator_dict([
            F('name', T_STR, must=True),
            F('age', T_INT),
            F('money', T_FLOAT),
            F('friends', T_LIST, subs=[
                F('_', T_STR)
            ]),
            F('toys', T_DICT, subs=[
                F('car', T_LIST, subs=[
                    F('_', T_STR)
                ]),
                F('like', T_DICT, subs=[
                    F('size', T_LIST, subs=[
                        F('_', T_INT)
                    ]),
                    F('count', T_INT),
                ]),
            ]),
        ])
        def GET(self):
            log.info('testfunc ...')

        def input_error(self, data):
            log.info('input error ...')

    t = Test()
    t.GET()
    log.info('after validator: %s', t.validator.data)
    
    print(dir(Test.GET))
    print(dir(t.GET))
    print('name:', Test.GET.__name__, Test.GET.__doc__)
    print('name:', Test.input_error.__name__)
    print(hasattr(Test.GET, '__wrapped__'))
    print(hasattr(t.GET, '__wrapped__'))



if __name__ == '__main__':
    if len(sys.argv) > 1:
        globals()[sys.argv[1]]()
    else:
        fs = list(globals().keys())
        for k in fs:
            if k.startswith('test_'):
                print('-'*6, k, '-'*6)
                globals()[k]()

