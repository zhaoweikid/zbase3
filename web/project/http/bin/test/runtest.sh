#!/bin/bash
cwd=`pwd`
bindir=`dirname $cwd`
export PYTHONPATH=$PYTHONPATH:$bindir
pytest
