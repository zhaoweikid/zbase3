#!/bin/bash

#/home/test/python/bin/gunicorn -c ../conf/gunicorn_setting.py server:app
gunicorn -c ../conf/gunicorn_setting.py server:app
