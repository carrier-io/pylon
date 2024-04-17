#!/usr/bin/python
# coding=utf-8
# pylint: disable=I0011

#   Copyright 2024 getcarrier.io
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
    DB support tools
"""

from pylon.core.tools import log
from pylon.core.tools.context import Context


def init(context):
    """ Init DB support """
    if context.before_reloader:
        log.info(
            "Running in development mode before reloader is started. Skipping DB support init"
        )
        return
    #
    log.info("Initializing DB support")
    #
    context.db = Context()
    context.pylon_db = Context()
    #
    db_config = context.settings.get("db", {})
    pylon_db_config = context.settings.get("pylon_db", {})


def deinit(context):
    """ De-init DB support """
    if context.before_reloader:
        log.info(
            "Running in development mode before reloader is started. Skipping DB support de-init"
        )
        return
    #
    log.info("De-initializing DB support")
