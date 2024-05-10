#!/usr/bin/python3
# coding=utf-8

#   Copyright 2023 getcarrier.io
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
    Logging tool: SysLog support
"""

import socket
import logging
import logging.handlers


def enable_syslog_logging(context):
    """ Enable logging to SysLog """
    if "syslog" not in context.settings:
        return
    #
    settings = context.settings.get("syslog")
    #
    address = (
        settings.get("address", "localhost"),
        settings.get("port", 514)
    )
    facility = settings.get("facility", "user")
    socktype = socket.SOCK_DGRAM if settings.get("socktype", "udp").lower() == "udp" \
        else socket.SOCK_STREAM
    #
    handler = logging.handlers.SysLogHandler(
        address=address,
        facility=facility,
        socktype=socktype,
    )
    #
    handler.setFormatter(logging.getLogger("").handlers[0].formatter)
    logging.getLogger("").addHandler(handler)
