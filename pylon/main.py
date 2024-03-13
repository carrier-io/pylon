#!/usr/bin/python3
# coding=utf-8
# pylint: disable=C0411,C0412,C0413

#   Copyright 2020-2021 getcarrier.io
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
    Project entry point
"""

#
# Before all other imports and code: patch standard library and other libraries to use async I/O
#

from pylon.core.tools import env

CORE_DEVELOPMENT_MODE = env.get_var("DEVELOPMENT_MODE", "").lower() in ["true", "yes"]
CORE_WEB_RUNTIME = env.get_var("WEB_RUNTIME", "flask")

if not CORE_DEVELOPMENT_MODE and CORE_WEB_RUNTIME == "gevent":
    import gevent.monkey  # pylint: disable=E0401
    gevent.monkey.patch_all()
    #
    import psycogreen.gevent  # pylint: disable=E0401
    psycogreen.gevent.patch_psycopg()
    #
    import ssl
    import gevent.hub  # pylint: disable=E0401
    #
    hub_not_errors = list(gevent.hub.Hub.NOT_ERROR)
    hub_not_errors.append(ssl.SSLError)
    gevent.hub.Hub.NOT_ERROR = tuple(hub_not_errors)

#
# Normal imports and code below
#

import os
import uuid
import socket
import signal

import flask  # pylint: disable=E0401
import flask_restful  # pylint: disable=E0401

from pylon.core.tools import log
from pylon.core.tools import log_syslog
from pylon.core.tools import log_loki
from pylon.core.tools import module
from pylon.core.tools import event
from pylon.core.tools import seed
from pylon.core.tools import git
from pylon.core.tools import rpc
from pylon.core.tools import ssl
from pylon.core.tools import slot
from pylon.core.tools import server
from pylon.core.tools import session
from pylon.core.tools import traefik
from pylon.core.tools import exposure

from pylon.core.tools.signal import signal_sigterm
from pylon.core.tools.context import Context


def main():  # pylint: disable=R0912,R0914,R0915
    """ Entry point """
    # Register signal handling
    signal.signal(signal.SIGTERM, signal_sigterm)
    # Enable logging and say hello
    log.enable_logging()
    log.info("Starting plugin-based Carrier core")
    # Make context holder
    context = Context()
    # Save debug status
    context.debug = CORE_DEVELOPMENT_MODE
    context.web_runtime = CORE_WEB_RUNTIME
    # Load settings from seed
    log.info("Loading and parsing settings")
    context.settings = seed.load_settings()
    if not context.settings:
        log.error("Settings are empty or invalid. Exiting")
        os._exit(1)  # pylint: disable=W0212
    # Save global node name
    context.node_name = context.settings.get("server", {}).get("name", socket.gethostname())
    # Generate pylon ID
    context.id = f'{context.node_name}_{str(uuid.uuid4())}'
    log.info("Pylon ID: %s", context.id)
    # Set process title
    import setproctitle  # pylint: disable=C0415,E0401
    setproctitle.setproctitle(f'pylon {context.id}')
    # Set environment overrides (e.g. to add env var with data from vault)
    log.info("Setting environment overrides")
    for key, value in context.settings.get("environment", {}).items():
        os.environ[key] = value
    # Allow to override debug from config (if != gevent in env)
    if context.web_runtime != "gevent" and "debug" in context.settings.get("server", {}):
        context.debug = context.settings.get("server").get("debug")
    # Allow to override runtime from config (if != gevent in env)
    if context.web_runtime != "gevent" and "runtime" in context.settings.get("server", {}):
        context.web_runtime = context.settings.get("server").get("runtime")
    # TODO: reinit logging after full switch to centry_logging
    # Prepare SSL custom cert bundle
    ssl.init(context)
    # Enable SysLog logging if requested in config
    log_syslog.enable_syslog_logging(context)
    # Enable Loki logging if requested in config
    log_loki.enable_loki_logging(context)
    # Make ModuleManager instance
    log.info("Creating ModuleManager instance")
    context.module_manager = module.ModuleManager(context)
    # Make EventManager instance
    log.info("Creating EventManager instance")
    context.event_manager = event.EventManager(context)
    # Add global URL prefix to context
    server.add_url_prefix(context)
    # Make app instance
    log.info("Creating Flask application")
    context.app = flask.Flask("pylon")
    # Make API instance
    log.info("Creating API instance")
    context.api = flask_restful.Api(context.app, catch_all_404s=True)
    # Make SocketIO instance
    log.info("Creating SocketIO instance")
    context.sio = server.create_socketio_instance(context)
    # Add dispatcher and proxy middlewares if needed
    server.add_middlewares(context)
    # Set application settings
    context.app.config["CONTEXT"] = context
    context.app.config.from_mapping(context.settings.get("application", {}))
    # Enable server-side sessions
    session.init_flask_sessions(context)
    # Make RpcManager instance
    log.info("Creating RpcManager instance")
    context.rpc_manager = rpc.RpcManager(context)
    # Make SlotManager instance
    log.info("Creating SlotManager instance")
    context.slot_manager = slot.SlotManager(context)
    # Apply patches needed for pure-python git and providers
    git.apply_patches()
    # Load and initialize modules
    context.module_manager.init_modules()
    # Register Traefik route via Redis KV
    traefik.register_traefik_route(context)
    # Expose pylon
    exposure.expose(context)
    # Run WSGI server
    try:
        server.run_server(context)
    finally:
        log.info("WSGI server stopped")
        # Unexpose pylon
        exposure.unexpose(context)
        # Unregister traefik route
        traefik.unregister_traefik_route(context)
        # De-init modules
        context.module_manager.deinit_modules()
    # Exit
    log.info("Exiting")


if __name__ == "__main__":
    # Call entry point
    main()
