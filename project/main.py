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
from simplekv.memory.redisstore import RedisStore  # pylint: disable=E0401
from simplekv.memory import DictStore  # pylint: disable=E0401
from redis import StrictRedis  # pylint: disable=E0401

from core.tools import log
from core.tools import config
from core.tools import module
from core.tools import storage


def main():  # pylint: disable=R0912,R0914,R0915
    """ Entry point """
    # Register signal handling
    signal.signal(signal.SIGTERM, signal_sigterm)
    # Enable logging
    if os.environ.get("CORE_DEBUG_LOGGING", "").lower() in ["true", "yes"]:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO
    log.init(log_level)
    log.info("Starting plugin-based Galloper core")
    # Load settings from seed
    log.info("Loading settings")
    settings_data = None
    settings_seed = os.environ.get("CORE_CONFIG_SEED", None)
    if settings_seed and ":" in settings_seed:
        settings_seed_tag = settings_seed[:settings_seed.find(":")]
        settings_seed_data = settings_seed[len(settings_seed_tag)+1:]
        try:
            seed = importlib.import_module(f"core.seeds.{settings_seed_tag}")
            settings_data = seed.unseed(settings_seed_data)
        except:  # pylint: disable=W0702
            log.exception("Failed to unseed settings")
    if not settings_data:
        log.error("Settings are empty or invalid. Exiting")
        os._exit(1)  # pylint: disable=W0212
    # Parse settings
    log.info("Parsing settings")
    settings = yaml.load(os.path.expandvars(settings_data), Loader=yaml.SafeLoader)
    settings = config.config_substitution(settings, config.vault_secrets(settings))
    # Register provider for template and resource loading from modules
    pkg_resources.register_loader_type(module.DataModuleLoader, module.DataModuleProvider)
    # Make ModuleManager instance
    module_manager = module.ModuleManager(settings)
    # Make app instance
    log.info("Creating Flask application")
    app = flask.Flask("project")
    if settings.get("server", dict()).get("proxy", False):
        app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
    # Set app settings
    app.config["SETTINGS"] = settings
    app.config["MODULES"] = module_manager
    app.config.from_mapping(settings.get("application", dict()))
    # Enable third-party extensions
    redis_config = settings.get("redis", dict())
    if redis_config:
        session_store = RedisStore(
            StrictRedis(
                host=redis_config.get("host", "localhost"),
                password=redis_config.get("password", None),
            )
        )
        log.info("Using redis for session storage")
    else:
        session_store = DictStore()
        log.info("Using memory for session storage")
    KVSessionExtension(session_store, app)
    # Load and initialize modules
    temporary_data_dirs = list()
    #
    for module_name in storage.list_modules(settings):
        log.info("Module: %s", module_name)
        module_data = storage.get_module(settings, module_name)
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
                storage.get_config(settings, module_name), module_root_path, app
            )
            # Initialize module
            module_obj.init()
            # Finally done
            module_manager.add_module(module_name, module_root_path, module_metadata, module_obj)
            log.info("Initialized module: %s", module_name)
        except:  # pylint: disable=W0702
            log.exception("Failed to initialize module: %s", module_name)
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
        # De-init modules
        for module_name in module_manager.modules:
            _, _, module_obj = module_manager.get_module(module_name)
            module_obj.deinit()
        # Delete module data dirs
        for directory in temporary_data_dirs:
            log.info("Deleting temporary data directory: %s", directory)
            shutil.rmtree(directory)
    # Exit
    log.info("Exiting")


def signal_sigterm(signal_num, stack_frame):
    """ SIGTERM signal handler: for clean and fast docker stop/restart """
    raise SystemExit


if __name__ == "__main__":
    # Call entry point
    main()
