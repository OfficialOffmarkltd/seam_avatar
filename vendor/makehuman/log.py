# Headless stub for MakeHuman's log module.
# Replaces the GUI-coupled original which depends on core.G (the Qt app singleton).
# Delegates to Python's stdlib logging under the logger name "mh".

import logging as _logging

_log = _logging.getLogger("mh")

def debug(msg, *args, **kwargs):   _log.debug(msg, *args)
def message(msg, *args, **kwargs): _log.info(msg, *args)
def warning(msg, *args, **kwargs): _log.warning(msg, *args)
def error(msg, *args, **kwargs):   _log.error(msg, *args)
def notice(msg, *args, **kwargs):  _log.info(msg, *args)

def getLogger(name):
    return _logging.getLogger(name)
