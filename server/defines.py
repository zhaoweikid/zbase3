# coding: utf-8
# 错误码定

OK  = 0
ERR = -1
ERR_PARAM  = -2
ERR_METHOD = -3
ERR_PERM   = -4
ERR_DB     = -5
ERR_EXCEPT = -6
ERR_INTERNAL = -7
ERR_AUTH   = -8

errmsg = {
    OK: '操作成功',
    ERR: '操作失败({})'.format(ERR),
    ERR_PARAM: '参数错误({})'.format(ERR_PARAM),
    ERR_METHOD: '方法错误({})'.format(ERR_METHOD),
    ERR_PERM: '权限拒绝({})'.format(ERR_PERM),
    ERR_DB: '数据库错误({})'.format(ERR_DB),
    ERR_EXCEPT: '内部异常({})'.format(ERR_EXCEPT),
    ERR_INTERNAL: '内部服务器错误({})'.format(ERR_INTERNAL),
    ERR_AUTH: '认证失败({})'.format(ERR_AUTH),
}

