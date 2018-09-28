#coding: utf-8
import os, sys, time
import random, operator
import logging

log = logging.getLogger()

class Selector:
    def __init__(self, serverlist, policy='round_robin'):
        self.servers = []
        self.pos = 0
        self.policy = policy
        for item in serverlist:
            newitem = {}
            newitem['server'] = item
            newitem['valid']  = True
            newitem['timestamp'] = 0
            self.servers.append(newitem)

        self._op_map = {
            '=':  'eq',
            '!=': 'ne',
            '>':  'gt',
            '>=': 'ge',
            '<':  'lt',
            '<=': 'le',
            'in': 'contains',
        }

    def filter_by_rule(self, input):
        if not input:
            return self.servers
        serv = []
        addition_server = []
        for item in self.servers:
            rule = item['server'].get('rule', '')
            if not rule:
                addition_server.append(item)
                continue
            for r in rule:
                name, op, value = r
                v = input.get(name, '')
                if not v:
                    break
                if not getattr(operator, self._op_map[op])(v, value):
                    break
            else:
                serv.append(item)
        if not serv:
            return addition_server
        return serv

    def next(self, input=None):
        return getattr(self, self.policy)(input)

    def round_robin(self, input=None):
        server_valid = []
        servers = self.filter_by_rule(input)
        i = 0;
        for item in servers:
            if item['valid']:
                server_valid.append(item)
                i += 1
        if i == 0:
            return None
        select = server_valid[self.pos % i]
        self.pos = (self.pos + 1) % len(server_valid)
        #log.debug("select:%s, i:%d", select, i)
        return select


    def random(self, input=None):
        server_valid = []
        servers = self.filter_by_rule(input)
        i = 0
        for item in servers:
            if item['valid'] == True:
                server_valid.append(item)
                i += 1
        if i == 0:
            return None
        index = random.randint(0, i-1)
        return server_valid[index]

    def not_valid(self, input=None):
        notvalid = []
        servers = self.filter_by_rule(input)
        for item in servers:
            if not item['valid']:
                notvalid.append(item)
        return notvalid

    def valid(self, input=None):
        valid = []
        servers = self.filter_by_rule(input)
        for item in servers:
            if item['valid']:
                valid.append(item)
        return valid


