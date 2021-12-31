# rpc server error
from zbase3.server.defines import ERR_EXCEPT, ERR_PARAM


class MethodError(Exception):
    """没有此方法"""
    pass


# rpc server error
class MethodFail(Exception):
    """方法调用返回失败"""

    def __init__(self, retcode, result):
        self.retcode = retcode
        self.result = result

    def __str__(self):
        return 'MethodFail({}, {})'.format(self.retcode, self.result)


class ParamError(MethodFail):
    """参数错误"""

    def __init__(self, result=None):
        super(ParamError, self).__init__(ERR_PARAM, result)
        self.result = result
