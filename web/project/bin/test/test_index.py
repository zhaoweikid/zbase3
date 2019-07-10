# coding:utf-8
import os, sys
import client

class Ping:
    name = 'ping'


def test_ping():
    c = client.HTTPClient()
    
    ret = c.open('ping')
    print(ret)


   
if __name__ == '__main__':
    test_ping()

