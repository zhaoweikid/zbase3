# coding: utf-8
import os, sys

def loadlib(path):
    files = os.listdir(path)
    for fn in files:
        if os.path.isfile(fn) and fn.endswith('.zip'):
            fpath = os.path.join(path, fn)
            sys.path.append(fpath)

def loadconf(HOME, config_name=None):
    '''加载模块搜索路径以及使用对用的配置文件'''
    # 加载库路径
    #HOME = os.path.dirname(os.path.abspath(__file__))
    # 默认认为项目路径下lib, conf为模块搜索路径
    libpath = [os.path.join(os.path.dirname(HOME), 'lib'), 
               os.path.join(os.path.dirname(HOME), 'conf'),
               os.path.dirname(os.path.dirname(HOME)),
               ]   
    for path in libpath:
        if os.path.isdir(path):
            sys.path.append(path)

    # 如有lib目录,里面可以有zip包是模块 
    pth = os.path.join(os.path.dirname(HOME), 'lib')
    if os.path.isdir(pth):
        loadlib(pth)

    # 如果有有参数表明是指定配置文件
    if config_name:
        config_file = 'config_' + config_name
        sys.modules['config'] = __import__(config_file)

def loadconf_argv(HOME):
    if len(sys.argv) > 1:
        loadconf(HOME, sys.argv[1])
    else:
        loadconf(HOME)


if __name__ == '__main__':
    loadlib(sys.argv[1])


