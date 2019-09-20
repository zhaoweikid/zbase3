# coding:utf-8
import os, sys
import client

class Ping:
    name = 'ping'


def test_ping():
    c = client.HTTPClient()
    
    ret = c.open(c._make_args('/', name=1, id=[1,2,3,4]))
    print(ret)


   
if __name__ == '__main__':
    test_ping()

