#!/usr/bin/python3
# coding=utf-8

#   Copyright 2020 getcarrier.io
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

"""
    Logging tool
"""

import io
import logging
import inspect
import urllib3  # pylint: disable=E0401
import requests  # pylint: disable=E0401

from pylon.core import constants
from pylon.core.tools import env


def init(level=logging.INFO):
    """ Initialize logging """
    logging.basicConfig(
        level=level,
        datefmt=constants.LOG_DATE_FORMAT,
        format=constants.LOG_FORMAT,
    )
    logging.raiseExceptions = False
    # Disable requests/urllib3 logging
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    # Disable SSL warnings
    urllib3.disable_warnings()
    requests.packages.urllib3.disable_warnings()  # pylint: disable=E1101
    # Disable additional logging
    logging.getLogger("pika").setLevel(logging.WARNING)
    logging.getLogger("paramiko.hostkeys").setLevel(logging.WARNING)


def get_logger():
    """ Get logger for caller context """
    return logging.getLogger(
        inspect.currentframe().f_back.f_globals["__name__"]
    )


def get_outer_logger():
    """ Get logger for callers context (for use in this module) """
    return logging.getLogger(
        inspect.currentframe().f_back.f_back.f_globals["__name__"]
    )


def debug(msg, *args, **kwargs):
    """ Logs a message with level DEBUG """
    return get_outer_logger().debug(msg, *args, **kwargs)


def info(msg, *args, **kwargs):
    """ Logs a message with level INFO """
    return get_outer_logger().info(msg, *args, **kwargs)


def warning(msg, *args, **kwargs):
    """ Logs a message with level WARNING """
    return get_outer_logger().warning(msg, *args, **kwargs)


def error(msg, *args, **kwargs):
    """ Logs a message with level ERROR """
    return get_outer_logger().error(msg, *args, **kwargs)


def critical(msg, *args, **kwargs):
    """ Logs a message with level CRITICAL """
    return get_outer_logger().critical(msg, *args, **kwargs)


def log(lvl, msg, *args, **kwargs):
    """ Logs a message with integer level lvl """
    return get_outer_logger().log(lvl, msg, *args, **kwargs)


def exception(msg, *args, **kwargs):
    """ Logs a message with level ERROR inside exception handler """
    return get_outer_logger().exception(msg, *args, **kwargs)


def enable_logging():
    """ Enable logging using log level supplied from env """
    if env.get_var("DEBUG_LOGGING", "").lower() in ["true", "yes"]:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO
    #
    init(log_level)


class DebugLogStream(io.RawIOBase):
    """ IO stream that writes to log.debug """

    def read(self, size=-1):  # pylint: disable=W0613
        return None

    def readall(self):
        return None

    def readinto(self, b):  # pylint: disable=W0613
        return None

    def write(self, b):
        for line in b.decode().splitlines():
            get_outer_logger().debug(line)


class Filter(logging.Filter):  # pylint: disable=R0903
    """ Logging filter """

    def __init__(self, filters=None):
        super().__init__()
        #
        self.filters = []
        #
        if filters:
            self.filters.extend(filters)

    def filter(self, record):
        """ Filter record """
        message = record.getMessage()
        #
        for item in self.filters:
            if item in message:
                return False
        #
        return True
