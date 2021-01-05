#coding: utf-8
import os, sys, time
import random, operator
import logging

log = logging.getLogger()


op_map = {
    '=':  'eq',
    '==': 'eq',
    '!=': 'ne',
    '>':  'gt',
    '>=': 'ge',
    '<':  'lt',
    '<=': 'le',
    'in': 'contains',
}


class ServerItem:
    def __init__(self, data):
        self.data = data
        self.timestamp = 0


class ServerList:
    def __init__(self, serverlist, policy='round_robin'):
        self.servers = []
        self.fail_servers = {}
        self.pos = 0
        self.policy = policy

        for item in serverlist:
            self.servers.append(ServerItem(item))

    def _do_rule(self, indata):
        if not indata:
            return self.servers
        serv = []
        for item in self.servers:
            rule = item.data.get('rule')
            if not rule:
                serv.append(item)
                continue
            for r in rule:
                name, op, value = r
                v = indata.get(name, '')
                if not v:
                    break
                if not getattr(operator, op_map[op])(v, value):
                    #log.debug('not match %s %s', v, value)
                    break
            else:
                #log.debug('append:%s', item)
                serv.append(item)
        return serv

    def next(self, indata=None):
        return getattr(self, self.policy)(indata)

    def round_robin(self, indata=None):
        servers = self._do_rule(indata)
        if not servers:
            return None
        serv = servers[self.pos % len(servers)]
        self.pos += 1
        return serv.data

    def random(self, indata=None):
        servers = self._do_rule(indata)
        if not servers:
            return None
        return servers[random.randint(0,len(servers)-1)].data

    
    def fail(self, serv):
        addr = serv['addr']
        k = '%s:%d' % addr
      
        serv = None
        for i in range(0, len(self.servers)):
            if self.servers[i].data['addr'] == addr:
                serv = self.servers.pop(i)
                break
        else:
            return

        self.fail_servers[k] = serv

    def restore(self, serv):
        addr = serv['addr']
        k = '%s:%d' % addr
 
        serv = self.fail_servers.pop(k)
        self.servers.append(serv)

    def get_fails(self):
        serv = []
        for k,v in self.fail_servers.items():
            serv.append(v.data)
        return serv



def test():
    from zbase3.base import logger
    log = logger.install('stdout')

    s = [
        {'addr':('127.0.0.1', 1000), 'timeout':1000},
        {'addr':('127.0.0.1', 1000), 'timeout':1001},
        {'addr':('127.0.0.1', 1000), 'timeout':1002},
        {'addr':('127.0.0.1', 1000), 'timeout':1003},
    ]
   
    print('test roundrobin')
    servers = ServerList(s)
    for i in range(0, 10):
        print(servers.next())

    print('test random')
    servers = ServerList(s, 'random')
    for i in range(0, 10):
        print(servers.next())


    s2 = [
        {'addr':('127.0.0.1', 1001), 'timeout':1000},
        {'addr':('127.0.0.1', 1002), 'timeout':1000, 'rule':[('amt','>',100), ('name','=','haha')]},
        {'addr':('127.0.0.1', 1003), 'timeout':1000},
        {'addr':('127.0.0.1', 1004), 'timeout':1000},
    ]
    print('test rule')
    indata1 = {'name':'haha1111', 'amt':99}
    indata2 = {'name':'haha', 'amt':199}

    servers = ServerList(s2)
    for i in range(0, 10):
        print(servers.next(indata1))

    print('test rule2 ---------')
    for i in range(0, 10):
        print(servers.next(indata2))

def test_fail():
    from zbase3.base import logger
    log = logger.install('stdout')

    s = [
        {'addr':('127.0.0.1', 1001), 'timeout':1000},
        {'addr':('127.0.0.1', 1002), 'timeout':1000},
        {'addr':('127.0.0.1', 1003), 'timeout':1000},
        {'addr':('127.0.0.1', 1004), 'timeout':1000},
    ]
   
    print('test roundrobin')
    servers = ServerList(s)
    for i in range(0, 10):
        one = servers.next()
        print(one)
        assert one['addr'][1] in (1001,1002,1003,1004)



    print('1002 1003 fail')
    servers.fail(s[1])
    servers.fail(s[2])

    for i in range(0, 10):
        one = servers.next()
        print(one)
        assert one['addr'][1] in (1001,1004)

    print('all fail')   
    servers.fail(s[0])
    servers.fail(s[3])

    for i in range(0, 10):
        one = servers.next()
        print(one)
        assert one == None
 
    print('restore 1001 1002')   
    servers.restore(s[0])
    servers.restore(s[1])

    for i in range(0, 10):
        one = servers.next()
        print(one)
        assert one['addr'][1] in (1001,1002)
    
    print('restore all')
    servers.restore(s[2])
    servers.restore(s[3])
    for i in range(0, 10):
        one = servers.next()
        print(one)
        assert one['addr'][1] in (1001,1002,1003,1004)
 
if __name__ == '__main__':
    test_fail()




