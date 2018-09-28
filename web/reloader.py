# coding: utf-8
# reloader from web.py

import os, sys
import traceback
import logging

log = logging.getLogger()

class Reloader:
    """Checks to see if any loaded modules have changed on disk and,
    if so, reloads them.
    """
    SUFFIX = '.pyc'

    def __init__(self):
        self.mtimes = {}

    def __call__(self):
        is_reload = False
        for mod in sys.modules.values():
            if self.check(mod):
                is_reload = True

        return is_reload

    def check(self, mod):
        # jython registers java packages as modules but they either
        # don't have a __file__ attribute or its value is None

        is_reload = False

        if not (mod and hasattr(mod, '__file__') and mod.__file__):
            return is_reload
        try:
            mtime = os.stat(mod.__file__).st_mtime
        except (OSError, IOError):
            return is_reload
        if mod.__file__.endswith(self.__class__.SUFFIX) and os.path.exists(mod.__file__[:-1]):
            mtime = max(os.stat(mod.__file__[:-1]).st_mtime, mtime)

        if mod not in self.mtimes:
            self.mtimes[mod] = mtime
        elif self.mtimes[mod] < mtime:
            try:
                log.debug('reload %s', mod)
                reload(mod)
                is_reload = True
                self.mtimes[mod] = mtime
            except ImportError:
                log.debug('reload error: %s', traceback.format_exc())

        return is_reload
