# coding: utf-8
import re
import types
import logging
import traceback

log = logging.getLogger()

T_INT       = 1
T_FLOAT     = 2
T_STR       = 4
T_REG       = 8
T_MAIL      = 16
T_IP        = 32
T_MOBILE    = 64
T_DATE      = 128
T_DATETIME  = 256
T_TIMESTAMP = 512

TYPE_MAP = {
    T_MAIL: re.compile("^[a-zA-Z0-9_\-\'\.]+@[a-zA-Z0-9_]+(\.[a-z]+){1,2}$"),
    T_IP: re.compile("^([0-9]{1,3}\.){3}[0-9]{1,3}$"),
    T_MOBILE: re.compile("^1[3578][0-9]{9}$"),
    T_DATE: re.compile("^2[0-9]{3}(\-|/)[0-9]{2}(\-|/)[0-9]{2}$"),
    T_DATETIME: re.compile("^2[0-9]{3}(\-|/)[0-9]{2}(\-|/)[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}$"),
    T_TIMESTAMP: re.compile("^[0-9]{1,10}$")
}

opmap = {'eq':'=',
         'lt':'<',
         'gt':'>',
         'ne':'<>',
         'le':'<=',
         'ge':'>=',
         'in':'in',
         'bt':'between',
         'lk':'like',
         }

class Field:
    def __init__(self, name, valtype=T_STR, must=False, default=None, **options):
        self.name   = name
        self.type   = valtype # 值类型, 默认为字符串
        self.must = must # 是否必须有值不能为空
        self.op     = '='
        self.default= default

        # 扩展信息
        self.show   = '' # 字段显示名
        self.method = '' # http 方法
        self.match  = '' # 正则匹配
        self.attr   = None # 字段属性，用来过滤
        self.error  = ''   # 错误信息
        self.choice = None # 值枚举值
        self.value  = None

        self.__dict__.update(options)

        if valtype >= T_MAIL: 
            self.match = TYPE_MAP[valtype]

        if self.match and type(self.match) == str:
            self.match = re.compile(self.match)

    def __str__(self):
        match = ''
        if self.match:
            match = self.match.pattern
        return 'name:%s type:%d match:%s must:%d op:%s default:%s' % \
                (self.name, self.type, match, self.must, self.op, self.default)

F = Field


class ValidatorError (Exception):
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

    def _check_item(self, field, val):
        if field.type & T_INT:
            return int(val)
        elif field.type & T_FLOAT:
            return float(val)
        elif field.type & T_STR:
            if field.match:
                if not field.match.match(val):
                    log.debug('validator match error: %s, %s=%s', field.match.pattern, field.name, str(val))
                    raise ValidatorError(field.name)
            return val
        else:
            if not field.match.match(val):
                log.debug('validator match error: %s, %s=%s', field.match.pattern, field.name, str(val))
                raise ValidatorError(field.name)
            return val

        raise ValidatorError('%s type error' % field.name)


    def verify(self, inputdata):
        result = [] # 没验证通过的字段名

        # check input format and transfer to {key: [op, value]}
        _input = {}
        for k,v in inputdata.items():
            if '__' in k:
                k_name,k_op = k.split('__')
                op = opmap.get(k_op)
                if not op: # k_name error
                    result.append(k_name)
                    continue
                _input[k_name] = [op, v]
            else:
                _input[k] = ['=', v]

        if result:
            return result

        # check field and transfer type
        for f in self._fields:
            try:
                val = _input.get(f.name)
                if not val: # field defined not exist
                    if f.must: # null is not allowed, error
                        result.append(f.name)
                    elif not f.default is None:
                        f.value = f.default
                        self.data[f.name] = f.default
                    continue

                f.op = val[0]
                v = val[1]  
                if val[0] != '=' and ',' in v: # , transfer to list
                    val = v.split(',')
                    f.value = [self._check_item(f,cv) for cv in val]
                    if not f.value:
                        result.append(f.name)
                else:
                    f.value = self._check_item(f, v)
                    if f.value is None:
                        result.append(f.name)
                self.data[f.name] = f.value
            except ValidatorError:
                result.append(f.name)
                log.warn(traceback.format_exc())
            except ValueError:
                result.append(f.name)
            except:
                result.append(f.name)
                log.info(traceback.format_exc())
        return result

    def report(self, result, sep=u'<br/>'):
        ret = []
        for x in result:
            if x:
                ret.append(u'"%s"错误!' % x)
        return sep.join(ret)


def with_validator(fields):
    def f(func):
        def _(self, *args, **kwargs):
            vdt = Validator(fields)
            self.validator = vdt
            
            if hasattr(self, 'input'):
                ret = vdt.verify(self.input())
            else:
                ret = vdt.verify(self.req.input())
            
            self.data = self.validator.data
            
            log.debug('validator check fail:%s', ret)
            if ret:
                errfunc = getattr(self, 'error', None)
                if errfunc:
                    return errfunc(ret)
                else:
                    self.resp.status = 400
                    raise ValidatorError('input error:'+ str(ret))
                    #return 'input error'
            return func(self, *args, **kwargs)
        return _
    return f


def with_validator_self(func):
    def _(self, *args, **kwargs):
        vdt = Validator(getattr(self, '%s_fields'% func.__name__))
        self.validator = vdt
        if hasattr(self, 'input'):
            ret = vdt.verify(self.input())
        else:
            ret = vdt.verify(self.req.input())
        self.data = self.validator.data
        log.debug('validator check:%s', ret)
        if ret:
            #log.debug('err:%s', errfunc(ret))
            errfunc = getattr(self, 'error')
            if not errfunc: 
                errfunc = getattr(self, '%s_error'% func.__name__, None)
            if errfunc:
                return errfunc(ret)
            else:
                self.resp.status = 400
                #return 'input error'
                raise ValidatorError('input error:'+ str(ret))
        return func(self, *args, **kwargs)
    return _




def test1():
    from qfcommon3.base import logger
    log = logger.install('stdout')
 
    fields = [Field('age', T_INT),
              Field('money', T_FLOAT),
              Field('name'),
              Field('cate', T_INT),
              Field('income',T_INT),
              Field('test',T_INT),
              ]

    input = {'name':'aaaaa', 'age':'12', 'money':'12.44',
             'cate__in':'1,2,3', 'income__bt':'1000,5000',
             'no_tesst':'123'}

    x = Validator(fields)
    ret = x.verify(input)

    if ret:
        for q in ret:
            log.debug(q)
    else:
        log.debug('check ok')

    for f in x._fields:
        log.debug('name:%s, value:%s, valuetype:%s, op:%s'%(f.name, f.value, type(f.value), f.op))

def test2():
    from qfcommon3.base import logger
    log = logger.install('stdout')
 
    fields = [Field('age', T_INT),
              Field('money', T_INT),
              Field('name'),
              ]


    Validator(fields)

    class Request:
        def input(self):
            return {'name':'aaaaa', 'age':'12', 'money':'12.44'}


    class Test:
        GET_fields = [Field('age', T_INT),
              Field('money', T_INT),
              Field('name'),
              ]


        def __init__(self):
            self.req = Request()

        @with_validator_self
        def GET(self):
            log.info('testfunc ...')

        def GET_error(self, data):
            log.info('error ...')

    t = Test()
    t.GET()
    log.info('after validator: %s', t.validator.data)

def test3():
    from qfcommon3.base import logger
    log = logger.install('stdout')
 
    fields = [
        Field('age', T_INT, must=False, default = 18),
        Field('name', T_STR, must=True),
        Field('money', T_INT),
    ]
    input = {'name': 'aaaa', 'money': '12'}
    v = Validator(fields)
    ret = v.verify(input)
    #print(ret)
    #print(v.data)
    fields = [
        Field('age', T_INT, must=False, default = 18),
        Field('name', T_STR, must=True),
        Field('money', T_INT),
        Field('title', T_REG, match = '.{3,20}'),
    ]
    input['title'] = '1111111'
    v = Validator(fields)
    ret = v.verify(input)
    #print(ret)
    #print(v.data)


def test4():
    from qfcommon3.base import logger
    log = logger.install('stdout')
    from qfcommon3.web.httpcore import Request, Response
    
    class Req: 
        def __init__(self, data):
            self.data = data

        def input(self):
            return self.data

    class Test:
        def __init__(self):
            self.req = Req({'name':'aaaaa', 'age':'12', 'money':'12.44'})
            self.resp = Response()

        @with_validator([Field('age', T_INT), Field('money', T_INT), Field('name'),])
        def testfunc(self):
            log.info('testfunc ...')

        @with_validator([Field('age', T_INT), Field('money', T_FLOAT), Field('name'),])
        def testfunc2(self):
            log.info('testfunc2 ...')

        @with_validator([Field('age', T_INT), Field('money', T_FLOAT), Field('name', T_STR),])
        def testfunc3(self):
            log.info('testfunc3 ...')


    t = Test()
    t.testfunc()
    log.info('after validator: %s', t.validator.data)
    
    t.testfunc2()
    log.info('after validator: %s', t.validator.data)

    t.testfunc3()
    log.info('after validator: %s', t.validator.data)





if __name__ == '__main__':
    test1()
    test2()
    test3()
    test4()


