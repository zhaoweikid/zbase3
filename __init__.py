# coding: utf-8
import json
import datetime
import decimal
from functools import partial

def _json_default_trans(obj):
    '''json对处理不了的格式的处理方法'''
    if isinstance(obj, datetime.datetime):
        return obj.strftime('%Y-%m-%d %H:%M:%S')
    if isinstance(obj, datetime.date):
        return obj.strftime('%Y-%m-%d')
    if isinstance(obj, decimal.Decimal):
        return str(obj)
    raise TypeError('%r is not JSON serializable' % obj)


json.dumps = partial(json.dumps, default=_json_default_trans, separators=(',', ':'))


