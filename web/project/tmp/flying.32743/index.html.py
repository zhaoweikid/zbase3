# -*- coding:utf-8 -*-
from mako import runtime, filters, cache
UNDEFINED = runtime.UNDEFINED
STOP_RENDERING = runtime.STOP_RENDERING
__M_dict_builtin = dict
__M_locals_builtin = locals
_magic_number = 10
_modified_time = 1538109754.8071194
_enable_loop = True
_template_filename = 'templates/index.html'
_template_uri = 'index.html'
_source_encoding = 'utf-8'
_exports = []


def render_body(context,**pageargs):
    __M_caller = context.caller_stack._push_frame()
    try:
        __M_locals = __M_dict_builtin(pageargs=pageargs)
        data = context.get('data', UNDEFINED)
        __M_writer = context.writer()
        __M_writer('\n<!DOCTYPE html>\n<html>\n<head>\n<meta name="description" content="" />\n<title>Welcome To Web Server!</title>\n<meta http-equiv="Content-Type" content="text/html; charset=utf-8" />\n<link rel="shortcut icon" href="/static/images/favicon.ico" />\n<script language="javascript">\n</script>\n</head>\n<body>\n<h1>Welcome To Web Server!</h1>\n')
        __M_writer(filters.decode.utf8(data))
        __M_writer('\n</body>\n</html>\n')
        return ''
    finally:
        context.caller_stack._pop_frame()


"""
__M_BEGIN_METADATA
{"uri": "index.html", "line_map": {"16": 0, "24": 15, "30": 24, "22": 2, "23": 15}, "filename": "templates/index.html", "source_encoding": "utf-8"}
__M_END_METADATA
"""
