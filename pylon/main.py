#!/usr/bin/python3
# coding=utf-8
# pylint: disable=C0411,C0413

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
    Project entry point
"""

#
# Before all other imports and code: patch standard library and other libraries to use async I/O
#

import os

CORE_DEVELOPMENT_MODE = os.environ.get("CORE_DEVELOPMENT_MODE", "").lower() in ["true", "yes"]

if not CORE_DEVELOPMENT_MODE:
    import gevent.monkey  # pylint: disable=E0401
    gevent.monkey.patch_all(thread=False, subprocess=False)
    #
    import psycogreen.gevent  # pylint: disable=E0401
    psycogreen.gevent.patch_psycopg()

#
# Normal imports and code below
#

import sys
import json
import shutil
import socket
import signal
import tempfile
import importlib
import pkg_resources

import flask  # pylint: disable=E0401
from flask_restful import Api  # pylint: disable=E0401
from werkzeug.middleware.proxy_fix import ProxyFix  # pylint: disable=E0401

from pylon.core.tools import log
from pylon.core.tools import log_loki
from pylon.core.tools import module
from pylon.core.tools import event
from pylon.core.tools import storage
from pylon.core.tools import seed
from pylon.core.tools import rpc
from pylon.core.tools import slot
from pylon.core.tools import server
from pylon.core.tools import session
from pylon.core.tools import traefik
from pylon.core.tools import dependency
from pylon.core.tools.context import Context
from pylon.core.tools.git_manager import GitManager


def main():  # pylint: disable=R0912,R0914,R0915
    """ Entry point """
    # Register signal handling
    signal.signal(signal.SIGTERM, signal_sigterm)
    # Enable logging
    log.enable_logging()
    # Say hello
    log.info("Starting plugin-based Galloper core")
    # Make context holder
    context = Context()
    # Save debug status
    context.debug = CORE_DEVELOPMENT_MODE
    # Load settings from seed
    log.info("Loading and parsing settings")
    settings = seed.load_settings()
    if not settings:
        log.error("Settings are empty or invalid. Exiting")
        os._exit(1)  # pylint: disable=W0212
    context.settings = settings
    # Save global node name
    context.node_name = settings.get("server", dict()).get("name", socket.gethostname())
    # Enable Loki logging if requested in config
    log_loki.enable_loki_logging(context)
    # Register provider for template and resource loading from modules
    pkg_resources.register_loader_type(module.DataModuleLoader, module.DataModuleProvider)
    # Make ModuleManager instance
    module_manager = module.ModuleManager(settings)
    context.module_manager = module_manager
    # Make EventManager instance
    event_manager = event.EventManager(context)
    context.event_manager = event_manager
    # Initiate Dulwich Git Manager
    git_manager = GitManager(settings.get('git_manager'))
    context.git_manager = git_manager
    # Make app instance
    log.info("Creating Flask application")
    app = flask.Flask("project")
    if settings.get("server", dict()).get("proxy", False):
        app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
    context.app = app
    # Make API instance
    log.info("Creating API instance")
    api = Api(app, catch_all_404s=True)
    context.api = api
    # Set application settings
    app.config["CONTEXT"] = context
    app.config.from_mapping(settings.get("application", dict()))
    # Save global URL prefix to context. May merge with traefik rule in future
    context.url_prefix = settings.get("server", dict()).get("path", "/")
    while context.url_prefix.endswith("/"):
        context.url_prefix = context.url_prefix[:-1]
    # Enable server-side sessions
    session.init_flask_sessions(context)
    # Make RpcManager instance
    rpc_manager = rpc.RpcManager(context)
    context.rpc_manager = rpc_manager
    # Make SlotManager instance
    slot_manager = slot.SlotManager(context)
    context.slot_manager = slot_manager
    app.context_processor(slot.template_slot_processor(context))
    # Load and initialize modules
    if not context.debug:
        temporary_data_dirs = load_modules(context)
    else:
        temporary_data_dirs = load_development_modules(context)
    # Register Traefik route via Redis KV
    traefik.register_traefik_route(context)
    # Run WSGI server
    try:
        server.run_server(context)
    finally:
        log.info("WSGI server stopped")
        # Unregister traefik route
        traefik.unregister_traefik_route(context)
        # De-init modules
        for module_name in module_manager.modules:
            _, _, module_obj = module_manager.get_module(module_name)
            module_obj.deinit()
        # Delete module data dirs
        for directory in temporary_data_dirs:
            log.info("Deleting temporary data directory: %s", directory)
            try:
                shutil.rmtree(directory)
            except:  # pylint: disable=W0702
                log.exception("Failed to delete, skipping")
    # Exit
    log.info("Exiting")


def load_modules(context):
    """ Load and enable platform modules """
    #
    module_map = dict()  # module_name -> (metadata, loader)
    #
    for module_name in storage.list_modules(context.settings):
        log.info("Found module: %s", module_name)
        module_data = storage.get_module(context.settings, module_name)
        if not module_data:
            log.error("Failed to get module data, skipping")
            continue
        try:
            # Make loader for this module
            module_loader = module.DataModuleLoader(module_data)
            # Load module metadata
            if "metadata.json" not in module_loader.storage_files:
                log.error("No module metadata, skipping")
                continue
            with module_loader.storage.open("metadata.json", "r") as file:
                module_metadata = json.load(file)
            # Add to module map
            module_map[module_name] = (module_metadata, module_loader)
        except:  # pylint: disable=W0702
            log.exception("Failed to prepare module: %s", module_name)
    #
    module_order = dependency.resolve_depencies(module_map)
    log.debug("Module order: %s", module_order)
    #
    temporary_data_dirs = list()
    #
    for module_name in module_order:
        log.info("Enabling module: %s", module_name)
        try:
            # Get module metadata and loader
            module_metadata, module_loader = module_map[module_name]
            log.info(
                "Initializing module: %s [%s]",
                module_metadata.get("name", "N/A"),
                module_metadata.get("version", "N/A"),
            )
            # Extract module data if needed
            if module_metadata.get("extract", False):
                module_data_dir = tempfile.mkdtemp()
                temporary_data_dirs.append(module_data_dir)
                module_loader.storage.extractall(module_data_dir)
                module_root_path = os.path.join(
                    module_data_dir, module_metadata.get("module").replace(".", os.path.sep)
                )
            else:
                module_root_path = None
            # Import module package
            sys.meta_path.insert(0, module_loader)
            importlib.invalidate_caches()
            module_pkg = importlib.import_module(module_metadata.get("module"))
            # Make module instance
            module_obj = module_pkg.Module(
                settings=storage.get_config(context.settings, module_name),
                root_path=module_root_path,
                context=context
            )
            # Initialize module
            module_obj.init()
            # Finally done
            context.module_manager.add_module(
                module_name, module_root_path, module_metadata, module_obj
            )
            log.info("Initialized module: %s", module_name)
        except:  # pylint: disable=W0702
            log.exception("Failed to initialize module: %s", module_name)
    #
    return temporary_data_dirs


def get_development_module_map(context) -> dict:
    module_map = dict()  # module_name -> (metadata, loader)
    #
    for module_name in storage.list_development_modules(context.settings):
        log.info("Found module: %s", module_name)
        #
        module_path = os.path.join(context.settings["development"]["modules"], module_name)
        metadata_path = os.path.join(module_path, "metadata.json")
        #
        try:
            # Make loader for this module
            module_loader = None
            # Load module metadata
            if not os.path.exists(metadata_path):
                log.error("No module metadata, skipping")
                continue
            with open(metadata_path, "r") as file:
                module_metadata = json.load(file)
            # Add to module map
            module_map[module_name] = (module_metadata, module_loader)
        except:  # pylint: disable=W0702
            log.exception("Failed to prepare module: %s", module_name)
    return module_map


def enable_development_module(module_name, module_metadata, context):
    # Get module metadata and loader
    log.info(
        "Initializing module: %s [%s]",
        module_metadata.get("name", "N/A"),
        module_metadata.get("version", "N/A"),
    )
    # Extract module data if needed
    module_data_dir = os.path.join(context.settings["development"]["modules"], module_name)
    module_root_path = os.path.join(
        module_data_dir, module_metadata.get("module").replace(".", os.path.sep)
    )
    # Import module package
    sys.path.insert(1, module_data_dir)
    importlib.invalidate_caches()
    module_pkg = importlib.import_module(module_metadata.get("module"))
    # Make module instance
    module_obj = module_pkg.Module(
        settings=storage.get_development_config(context.settings, module_name),
        root_path=module_root_path,
        context=context
    )
    # Initialize module
    module_obj.init()
    # Finally done
    context.module_manager.add_module(
        module_name, module_root_path, module_metadata, module_obj
    )


def load_development_modules(context):
    """ Load and enable platform modules in development mode """
    #
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        log.info("Running in development mode before reloader is started. Skipping module loading")
        return list()
    log.info("Using module dir: %s", context.settings["development"]["modules"])

    module_map = get_development_module_map(context)

    log.info("Enabling module: Market")
    try:
        module_metadata, _ = module_map.pop('market')
        enable_development_module('market', module_metadata, context=context)
        log.info("Initialized module: Market")
        module_map = get_development_module_map(context)
        del module_map['market']
    except:  # pylint: disable=W0702
        log.exception("Failed to initialize module: Market")

    module_order = dependency.resolve_depencies(module_map)
    log.debug("Module order: %s", module_order)

    temporary_data_dirs = list()
    for module_name in module_order:
        log.info("Enabling module: %s", module_name)
        try:
            module_metadata, _ = module_map[module_name]
            enable_development_module(module_name, module_metadata, context=context)
            log.info("Initialized module: %s", module_name)
        except:  # pylint: disable=W0702
            log.exception("Failed to initialize module: %s", module_name)
    return temporary_data_dirs


def signal_sigterm(signal_num, stack_frame):
    """ SIGTERM signal handler: for clean and fast docker stop/restart """
    raise SystemExit


if __name__ == "__main__":
    # Call entry point
    main()
