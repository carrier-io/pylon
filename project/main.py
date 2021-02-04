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

import gevent.monkey  # pylint: disable=E0401
gevent.monkey.patch_all()

import psycogreen.gevent  # pylint: disable=E0401
psycogreen.gevent.patch_psycopg()

#
# Normal imports and code below
#

import os
import sys
import json
import shutil
import socket
import logging
import signal
import tempfile
import importlib
import pkg_resources

import yaml  # pylint: disable=E0401
import flask  # pylint: disable=E0401
from gevent.pywsgi import WSGIServer  # pylint: disable=E0401
from werkzeug.middleware.proxy_fix import ProxyFix  # pylint: disable=E0401

from flask_kvsession import KVSessionExtension  # pylint: disable=E0401
from simplekv.decorator import PrefixDecorator  # pylint: disable=E0401
from simplekv.memory.redisstore import RedisStore  # pylint: disable=E0401
from simplekv.memory import DictStore  # pylint: disable=E0401
from redis import StrictRedis  # pylint: disable=E0401

from core.tools import log
from core.tools import config
from core.tools import module
from core.tools import event
from core.tools import storage
from core.tools import slot
from core.tools import dependency
from core.tools.context import Context


def main():  # pylint: disable=R0912,R0914,R0915
    """ Entry point """
    # Register signal handling
    signal.signal(signal.SIGTERM, signal_sigterm)
    # Enable logging
    enable_logging()
    # Say hello
    log.info("Starting plugin-based Galloper core")
    # Make context holder
    context = Context()
    # Load settings from seed
    log.info("Loading and parsing settings")
    settings = load_settings()
    if not settings:
        log.error("Settings are empty or invalid. Exiting")
        os._exit(1)  # pylint: disable=W0212
    context.settings = settings
    # Register provider for template and resource loading from modules
    pkg_resources.register_loader_type(module.DataModuleLoader, module.DataModuleProvider)
    # Make ModuleManager instance
    module_manager = module.ModuleManager(settings)
    context.module_manager = module_manager
    # Make EventManager instance
    event_manager = event.EventManager(context)
    context.event_manager = event_manager
    # Make app instance
    log.info("Creating Flask application")
    app = flask.Flask("project")
    if settings.get("server", dict()).get("proxy", False):
        app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
    context.app = app
    # Set application settings
    app.config["CONTEXT"] = context
    app.config.from_mapping(settings.get("application", dict()))
    # Enable server-side sessions
    init_flask_sessions(context)
    # Make SlotManager instance
    slot_manager = slot.SlotManager(context)
    context.slot_manager = slot_manager
    app.context_processor(slot.template_slot_processor(context))
    # Load and initialize modules
    temporary_data_dirs = load_modules(context)
    # Register Traefik route via Redis KV
    register_traefik_route(context)
    # Run WSGI server
    log.info("Starting WSGI server")
    try:
        http_server = WSGIServer(
            (
                settings.get("server", dict()).get("host", ""),
                settings.get("server", dict()).get("port", 8080)
            ),
            app
        )
        http_server.serve_forever()
    finally:
        log.info("WSGI server stopped")
        # Unregister traefik route
        unregister_traefik_route(context)
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


def register_traefik_route(context):
    """ Create Traefik route for this Pylon instance """
    node = socket.gethostname()
    log.info("Registering Traefik route for node '%s'", node)
    #
    redis_config = context.settings.get("redis", dict())
    if not redis_config:
        log.error("Cannot register route: no refis config")
        return
    #
    store = StrictRedis(
        host=redis_config.get("host", "localhost"),
        password=redis_config.get("password", None),
    )
    #
    store.set(f"traefik/http/routers/{node}/rule", "PathPrefix(`/`)")  # pylint: disable=C0301
    store.set(f"traefik/http/routers/{node}/entrypoints/0", "http")
    store.set(f"traefik/http/routers/{node}/service", f"{node}")
    store.set(f"traefik/http/services/{node}/loadbalancer/servers/0/url", f"http://{node}:8080/")


def unregister_traefik_route(context):
    """ Delete Traefik route for this Pylon instance """
    node = socket.gethostname()
    log.info("Unregistering Traefik route for node '%s'", node)
    #
    redis_config = context.settings.get("redis", dict())
    if not redis_config:
        log.error("Cannot unregister route: no refis config")
        return
    #
    store = StrictRedis(
        host=redis_config.get("host", "localhost"),
        password=redis_config.get("password", None),
    )
    #
    store.delete(f"traefik/http/services/{node}/loadbalancer/servers/0/url")
    store.delete(f"traefik/http/routers/{node}/service")
    store.delete(f"traefik/http/routers/{node}/entrypoints/0")
    store.delete(f"traefik/http/routers/{node}/rule")


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
                storage.get_config(context.settings, module_name), module_root_path, context
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


def init_flask_sessions(context):
    """ Enable third-party server-side session storage """
    redis_config = context.settings.get("redis", dict())
    #
    if redis_config:
        session_store = RedisStore(
            StrictRedis(
                host=redis_config.get("host", "localhost"),
                password=redis_config.get("password", None),
            )
        )
        if redis_config.get("session_prefix", None):
            session_store = PrefixDecorator("pylon_session_", session_store)
        log.info("Using redis for session storage")
    else:
        session_store = DictStore()
        log.info("Using memory for session storage")
    #
    KVSessionExtension(session_store, context.app)


def load_settings():
    """ Load settings from seed from env """
    settings_data = None
    settings_seed = os.environ.get("CORE_CONFIG_SEED", None)
    #
    if not settings_seed or ":" not in settings_seed:
        return None
    #
    settings_seed_tag = settings_seed[:settings_seed.find(":")]
    settings_seed_data = settings_seed[len(settings_seed_tag)+1:]
    try:
        seed = importlib.import_module(f"core.seeds.{settings_seed_tag}")
        settings_data = seed.unseed(settings_seed_data)
    except:  # pylint: disable=W0702
        log.exception("Failed to unseed settings")
    #
    if not settings_data:
        return None
    #
    try:
        settings = yaml.load(os.path.expandvars(settings_data), Loader=yaml.SafeLoader)
        settings = config.config_substitution(settings, config.vault_secrets(settings))
    except:  # pylint: disable=W0702
        log.exception("Failed to parse settings")
        return None
    #
    return settings


def enable_logging():
    """ Enable logging using log level supplied from env """
    if os.environ.get("CORE_DEBUG_LOGGING", "").lower() in ["true", "yes"]:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO
    #
    log.init(log_level)


def signal_sigterm(signal_num, stack_frame):
    """ SIGTERM signal handler: for clean and fast docker stop/restart """
    raise SystemExit


if __name__ == "__main__":
    # Call entry point
    main()
