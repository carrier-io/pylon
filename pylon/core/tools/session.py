#!/usr/bin/python
# coding=utf-8
# pylint: disable=I0011

#   Copyright 2021 getcarrier.io
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
    Session tools
"""

from flask_kvsession import KVSessionExtension  # pylint: disable=E0401
from simplekv.decorator import PrefixDecorator  # pylint: disable=E0401
from simplekv.memory.redisstore import RedisStore  # pylint: disable=E0401
from simplekv.memory import DictStore  # pylint: disable=E0401
from redis import StrictRedis  # pylint: disable=E0401

from pylon.core.tools import log


def init_flask_sessions(context):
    """ Enable third-party server-side session storage """
    redis_config = context.settings.get("sessions", {}).get("redis", {})
    #
    if redis_config:
        session_store = RedisStore(
            StrictRedis(
                host=redis_config.get("host", "localhost"),
                port=redis_config.get("port", 6379),
                password=redis_config.get("password", None),
                ssl=redis_config.get("use_ssl", False),
            )
        )
        session_prefix = context.settings.get("sessions", {}).get("prefix", None)
        if session_prefix:
            session_store = PrefixDecorator(session_prefix, session_store)
        log.info("Using redis for session storage")
    else:
        session_store = DictStore()
        log.info("Using memory for session storage")
    #
    KVSessionExtension(session_store, context.app)
