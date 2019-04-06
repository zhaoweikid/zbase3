# coding: utf-8

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
    OK: 'success',
    ERR: 'failed',
    ERR_PARAM: 'parameter error',
    ERR_METHOD: 'method error',
    ERR_PERM: 'permission deny',
    ERR_DB: 'database error',
    ERR_EXCEPT: 'exception found',
    ERR_INTERNAL: 'internal error',
    ERR_AUTH: 'auth error',
}

