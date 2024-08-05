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
    Logging support tools
"""



import logging

from arbiter import log as arbiter_log  # pylint: disable=E0401

from pylon.core.tools import env
from pylon.core.tools import log


def enable_basic_logging():
    """ Init basic logging support """
    force_debug_logging = env.get_var("DEBUG_LOGGING", "").lower() in ["true", "yes"]
    #
    if force_debug_logging:
        basic_log_level = logging.DEBUG
    else:
        basic_log_level = logging.INFO
    #
    arbiter_log.initialized = True
    #
    log.init(level=basic_log_level, force=True)
    apply_pylon_patches()


def reinit_logging(context):
    """ (Re-)Init logging support """
    force_debug_logging = env.get_var("DEBUG_LOGGING", "").lower() in ["true", "yes"]
    #
    if "log" in context.settings:
        # New-style log configuration is present
        # Just apply forced debug logging (if requested)
        # And call init()
        log_config = context.settings.get("log")
        #
        if "level" in log_config and isinstance(log_config["level"], str):
            log_levels = {
                "CRITICAL": logging.CRITICAL,
                "FATAL": logging.FATAL,
                "ERROR": logging.ERROR,
                "WARN": logging.WARN,
                "WARNING": logging.WARNING,
                "INFO": logging.INFO,
                "DEBUG": logging.DEBUG,
                "NOTSET": logging.NOTSET,
            }
            log_config["level"] = log_levels.get(log_config["level"].upper(), logging.INFO)
        #
        if force_debug_logging:
            log_config["level"] = logging.DEBUG
        #
        log.init(config=log_config, force=True)
        apply_pylon_patches()
        return
    #
    # Construct config from debug mode, env vars, syslog and loki settings
    #
    log_config = {
        "level": logging.INFO,
        "handlers": [
            {
                "type": "logging.StreamHandler",
            },
        ],
    }
    #
    if force_debug_logging or context.debug:
        log_config["level"] = logging.DEBUG
    #
    if "syslog" in context.settings:
        syslog_config = context.settings.get("syslog").copy()
        syslog_config["type"] = "centry_logging.handlers.syslog.SysLogHandler"
        #
        log_config["handlers"].append(syslog_config)
    #
    if "loki" in context.settings:
        loki_config = context.settings.get("loki").copy()
        loki_config["type"] = "centry_logging.handlers.loki.CarrierLokiLogHandler"
        #
        if loki_config.get("buffering", True):
            loki_config["type"] = "centry_logging.handlers.loki.CarrierLokiBufferedLogHandler"
        #
        if loki_config.get("include_node_name", True):
            loki_labels = loki_config.get("labels", {}).copy()
            loki_labels["node"] = context.node_name
            loki_config["labels"] = loki_labels
        #
        log_config["handlers"].append(loki_config)
    #
    log.init(config=log_config, force=True)
    apply_pylon_patches()


def apply_pylon_patches():
    """ Pylon-specific logging patches """
    loggers_to_info = [
        # Mute websocket debug messages
        "geventwebsocket.handler",
    ]
    #
    for logger in loggers_to_info:
        logging.getLogger(logger).setLevel(logging.INFO)
