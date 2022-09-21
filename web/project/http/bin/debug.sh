#!/bin/bash
p1=`pwd`
p2=${p1%zbase3*}
export PYTHONPATH=$PYTHONPATH:$p2
python3 server.py debug $1
#/home/test/python/bin/watchmedo auto-restart -d . -p "*.py" /home/test/python/bin/python server.py debug $1
#watchmedo auto-restart -d . -p "*.py" python server.py debug $1
