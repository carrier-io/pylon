#!/usr/bin/python
# coding=utf-8
# pylint: disable=C0302

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

""" Modules """

import os
import sys
import tempfile
import functools
import importlib

import yaml  # pylint: disable=E0401
import flask  # pylint: disable=E0401
import jinja2  # pylint: disable=E0401

from pylon.core.tools import log
from pylon.core.tools import web
from pylon.core.tools import process
from pylon.core.tools.dict import recursive_merge
from pylon.core.tools.config import config_substitution, vault_secrets


class ModuleDescriptor:  # pylint: disable=R0902,R0904
    """ Module descriptor """

    def __init__(self, context, name, loader, metadata, requirements):  # pylint: disable=R0913
        self.context = context
        self.name = name
        self.loader = loader
        self.metadata = metadata
        self.requirements = requirements
        #
        self.path = self.loader.get_local_path()
        self.config = None
        self.config_data = None
        #
        self.requirements_base = None
        self.requirements_path = None
        #
        self.activated_paths = []
        self.activated_bases = []
        #
        self.module = None
        self.prepared = False
        self.activated = False

    def load_config(self):
        """ Load custom (or default) configuration """
        #
        base_config_data = {}
        if self.loader.has_file("config.yml"):
            base_config_data = self._load_yaml_data(self.loader.get_data("config.yml"), "base")
        #
        pylon_config_data = self.context.settings.get("configs", {}).get(self.name, {})
        #
        custom_config_data = {}
        if self.context.module_manager.providers["config"].config_data_exists(self.name):
            self.config_data = \
                self.context.module_manager.providers["config"].get_config_data(self.name)
            custom_config_data = self._load_yaml_data(self.config_data, "custom")
        #
        yaml_data = {}
        yaml_data = recursive_merge(yaml_data, base_config_data)
        yaml_data = recursive_merge(yaml_data, pylon_config_data)
        yaml_data = recursive_merge(yaml_data, custom_config_data)
        #
        try:
            self.config = config_substitution(yaml_data, vault_secrets(self.context.settings))
        except:  # pylint: disable=W0702
            log.exception("Could not add config secrets and env data for: %s", self.name)
            self.config = yaml_data

    def _load_yaml_data(self, config_data, config_type):
        try:
            yaml_data = yaml.load(os.path.expandvars(config_data), Loader=yaml.SafeLoader)
        except:  # pylint: disable=W0702
            log.exception("Invaid YAML config data for: %s (%s)", self.name, config_type)
            yaml_data = None
        #
        if yaml_data is None:
            yaml_data = {}
        #
        return yaml_data

    def save_config(self):
        """ Save custom config """
        config_data = yaml.dump(self.config).encode()
        self.context.module_manager.providers["config"].add_config_data(self.name, config_data)

    def make_blueprint(self, url_prefix=None, static_url_prefix=None, use_template_prefix=True):
        """ Make configured Blueprint instance """
        template_folder = None
        if self.loader.has_directory("templates"):
            template_folder = "templates"
        #
        if url_prefix is None:
            url_prefix = f"/{self.name}"
        #
        static_folder = None
        if self.loader.has_directory("static"):
            static_folder = "static"
            if static_url_prefix is None:
                static_url_prefix = "static"
        #
        result_blueprint = flask.Blueprint(
            self.name, f"plugins.{self.name}",
            root_path=self.path,
            url_prefix=url_prefix,
            template_folder=template_folder,
            static_folder=static_folder,
            static_url_path=static_url_prefix,
        )
        #
        if template_folder is not None:
            if use_template_prefix:
                result_blueprint.jinja_loader = jinja2.PrefixLoader({
                    self.name: jinja2.loaders.PackageLoader(f"plugins.{self.name}", "templates"),
                }, delimiter=":")
            else:
                result_blueprint.jinja_loader = jinja2.loaders.PackageLoader(
                    f"plugins.{self.name}", "templates"
                )
        #
        return result_blueprint

    def init_blueprint(  # pylint: disable=R0913,R0914
            self,
            url_prefix=None, static_url_prefix=None, use_template_prefix=True,
            register_in_app=True, module_routes=True,
        ):
        """ Make and register blueprint with pre-registered routes """
        # Make Blueprint
        result_blueprint = self.make_blueprint(url_prefix, static_url_prefix, use_template_prefix)
        # Add routes
        if self.loader.has_directory("routes"):
            module_pkg = self.loader.module_name
            #
            for route_resource in importlib.resources.contents(
                    f"{module_pkg}.routes"
            ):
                if not self.loader.has_file(f"routes/{route_resource}"):
                    continue
                if route_resource.startswith("_") or not route_resource.endswith(".py"):
                    continue
                #
                resource_name, _ = os.path.splitext(route_resource)
                #
                try:
                    importlib.import_module(
                        f"{module_pkg}.routes.{resource_name}"
                    ).Route
                except:  # pylint: disable=W0702
                    log.exception(
                        "Failed to import Route module: %s",
                        resource_name,
                    )
                    continue
        #
        routes = web.routes_registry.pop(f"plugins.{self.name}", [])
        for route in routes:
            rule, endpoint, obj, options = route
            if module_routes:
                obj = functools.partial(obj, self.module)
                obj.__name__ = obj.func.__name__
            result_blueprint.add_url_rule(rule, endpoint, obj, **options)
        # Register in app
        if register_in_app:
            self.context.app.register_blueprint(result_blueprint)
        #
        return result_blueprint

    def init_api(self):
        """ Register all API resources from this module """
        if not self.loader.has_directory("api"):
            return
        #
        module_pkg = self.loader.module_name
        module_name = self.name
        #
        for api_version in importlib.resources.contents(f"{module_pkg}.api"):
            if not self.loader.has_directory(f"api/{api_version}"):
                continue
            #
            for api_resource in importlib.resources.contents(
                    f"{module_pkg}.api.{api_version}"
            ):
                if not self.loader.has_file(f"api/{api_version}/{api_resource}"):
                    continue
                if api_resource.startswith("_") or not api_resource.endswith(".py"):
                    continue
                #
                resource_name, _ = os.path.splitext(api_resource)
                #
                try:
                    resource = importlib.import_module(
                        f"{module_pkg}.api.{api_version}.{resource_name}"
                    ).API
                except:  # pylint: disable=W0702
                    log.exception(
                        "Failed to import API module: %s.%s",
                        api_version, resource_name,
                    )
                    continue
                #
                resource_urls = []
                if hasattr(resource, "url_params"):
                    for url_param in resource.url_params:
                        url_param = url_param.lstrip("/").rstrip("/")
                        #
                        resource_urls.append(
                            f"/api/{api_version}/{module_name}/{resource_name}/{url_param}"
                        )
                        resource_urls.append(
                            f"/api/{api_version}/{module_name}/{resource_name}/{url_param}/"
                        )
                else:
                    resource_urls.append(f"/api/{api_version}/{module_name}/{resource_name}")
                    resource_urls.append(f"/api/{api_version}/{module_name}/{resource_name}/")
                #
                self.context.api.add_resource(
                    resource,
                    *resource_urls,
                    endpoint=f"api.{api_version}.{module_name}.{resource_name}",
                    resource_class_kwargs={
                        "module": self.module,
                    }
                )

    def init_slots(self, module_slots=True):
        """ Register all decorated slots from this module """
        if self.loader.has_directory("slots"):
            module_pkg = self.loader.module_name
            #
            for slot_resource in importlib.resources.contents(
                    f"{module_pkg}.slots"
            ):
                if not self.loader.has_file(f"slots/{slot_resource}"):
                    continue
                if slot_resource.startswith("_") or not slot_resource.endswith(".py"):
                    continue
                #
                resource_name, _ = os.path.splitext(slot_resource)
                #
                try:
                    importlib.import_module(
                        f"{module_pkg}.slots.{resource_name}"
                    ).Slot
                except:  # pylint: disable=W0702
                    log.exception(
                        "Failed to import Slot module: %s",
                        resource_name,
                    )
                    continue
        #
        slots = web.slots_registry.pop(f"plugins.{self.name}", [])
        for slot in slots:
            name, obj = slot
            if module_slots:
                obj = functools.partial(obj, self.module)
                obj.__name__ = obj.func.__name__
                obj.__module__ = obj.func.__module__
            self.context.slot_manager.register_callback(name, obj)

    def init_rpcs(self, module_rpcs=True):
        """ Register all decorated RPCs from this module """
        module_name = self.name
        if self.loader.has_directory("rpc"):
            module_pkg = self.loader.module_name
            #
            for rpc_resource in importlib.resources.contents(
                    f"{module_pkg}.rpc"
            ):
                if not self.loader.has_file(f"rpc/{rpc_resource}"):
                    continue
                if rpc_resource.startswith("_") or not rpc_resource.endswith(".py"):
                    continue
                #
                resource_name, _ = os.path.splitext(rpc_resource)
                #
                try:
                    importlib.import_module(
                        f"{module_pkg}.rpc.{resource_name}"
                    ).RPC
                except:  # pylint: disable=W0702
                    log.exception(
                        "Failed to import RPC module: %s",
                        resource_name,
                    )
                    continue
        #
        rpcs = web.rpcs_registry.pop(f"plugins.{module_name}", [])
        for rpc in rpcs:
            name, proxy_name, auto_names, obj = rpc
            if module_rpcs:
                obj = functools.partial(obj, self.module)
                obj.__name__ = obj.func.__name__
            #
            if auto_names and name is None and proxy_name is None:
                try:
                    callable_name = self._get_callable_name(obj)
                    #
                    proxy_name = callable_name
                    name = f"{module_name}_{callable_name}"
                    #
                    log.debug("Set RPC name to: %s", name)
                    log.debug("Set RPC proxy name to: %s", proxy_name)
                except:  # pylint: disable=W0702
                    log.exception("Failed to get callable name for: %s", obj)
            #
            self.context.rpc_manager.register_function(obj, name)
            #
            if proxy_name is not None and name is not None:
                if hasattr(self.module, proxy_name):
                    raise RuntimeError(f"Name '{proxy_name}' is already set")
                #
                setattr(
                    self.module, proxy_name,
                    getattr(self.context.rpc_manager.call, name)
                )

    def _get_callable_name(self, func):
        if hasattr(func, "__name__"):
            return func.__name__
        if isinstance(func, functools.partial):
            return self._get_callable_name(func.func)
        raise ValueError("Cannot guess callable name")

    def init_sio(self, module_sios=True):
        """ Register all decorated SIO event listeners from this module """
        if self.loader.has_directory("sio"):
            module_pkg = self.loader.module_name
            #
            for sio_resource in importlib.resources.contents(
                    f"{module_pkg}.sio"
            ):
                if not self.loader.has_file(f"sio/{sio_resource}"):
                    continue
                if sio_resource.startswith("_") or not sio_resource.endswith(".py"):
                    continue
                #
                resource_name, _ = os.path.splitext(sio_resource)
                #
                try:
                    importlib.import_module(
                        f"{module_pkg}.sio.{resource_name}"
                    ).SIO
                except:  # pylint: disable=W0702
                    log.exception(
                        "Failed to import SIO module: %s",
                        resource_name,
                    )
                    continue
        #
        sios = web.sios_registry.pop(f"plugins.{self.name}", [])
        for sio in sios:
            name, obj = sio
            if module_sios:
                obj = functools.partial(obj, self.module)
                obj.__name__ = obj.func.__name__
            self.context.sio.on(name, handler=obj)

    def init_events(self, module_events=True):
        """ Register all decorated events from this module """
        if self.loader.has_directory("events"):
            module_pkg = self.loader.module_name
            #
            for event_resource in importlib.resources.contents(
                    f"{module_pkg}.events"
            ):
                if not self.loader.has_file(f"events/{event_resource}"):
                    continue
                if event_resource.startswith("_") or not event_resource.endswith(".py"):
                    continue
                #
                resource_name, _ = os.path.splitext(event_resource)
                #
                try:
                    importlib.import_module(
                        f"{module_pkg}.events.{resource_name}"
                    ).Event
                except:  # pylint: disable=W0702
                    log.exception(
                        "Failed to import Event module: %s",
                        resource_name,
                    )
                    continue
        #
        events = web.events_registry.pop(f"plugins.{self.name}", [])
        for event in events:
            name, obj = event
            if module_events:
                obj = functools.partial(obj, self.module)
                obj.__name__ = obj.func.__name__
                obj.__module__ = obj.func.__module__
            self.context.event_manager.register_listener(name, obj)

    def init_methods(self, module_methods=True):
        """ Register all decorated methods from this module """
        if self.loader.has_directory("methods"):
            module_pkg = self.loader.module_name
            #
            for method_resource in importlib.resources.contents(
                    f"{module_pkg}.methods"
            ):
                if not self.loader.has_file(f"methods/{method_resource}"):
                    continue
                if method_resource.startswith("_") or not method_resource.endswith(".py"):
                    continue
                #
                resource_name, _ = os.path.splitext(method_resource)
                #
                try:
                    importlib.import_module(
                        f"{module_pkg}.methods.{resource_name}"
                    ).Method
                except:  # pylint: disable=W0702
                    log.exception(
                        "Failed to import Method module: %s",
                        resource_name,
                    )
                    continue
        #
        methods = web.methods_registry.pop(f"plugins.{self.name}", [])
        for method in methods:
            name, obj = method
            if name is None:
                name = obj.__name__
            if module_methods:
                obj = functools.partial(obj, self.module)
                obj.__name__ = obj.func.__name__
                obj.__module__ = obj.func.__module__
            #
            if hasattr(self.module, name):
                raise RuntimeError(f"Name '{name}' is already set")
            #
            setattr(
                self.module, name,
                obj
            )

    def init_inits(self, module_inits=True):
        """ Run all decorated inits from this module """
        # NB: Inits are loaded by init_methods()
        inits = web.inits_registry.pop(f"plugins.{self.name}", [])
        for init in inits:
            if module_inits:
                init(self.module)
            else:
                init()

    def init_scripts(self):
        """ Run init shell scripts """
        scripts = self.metadata.get("init_scripts", [])
        if not scripts:
            scripts.append("bootstrap.sh")
        #
        local_path = self.loader.get_local_path()
        runtime = self.metadata.get("init_scripts_runtime", "/bin/bash")
        #
        for script in scripts:
            if not self.loader.has_file(script):
                continue
            #
            if local_path is not None:
                script_path = os.path.join(local_path, script)
            else:
                tmp_path = tempfile.mkdtemp()
                self.context.module_manager.temporary_objects.append(tmp_path)
                #
                with open(os.path.join(tmp_path, script), "wb") as file:
                    file.write(self.loader.get_data(script))
                #
                script_path = os.path.join(tmp_path, script)
            #
            log.info("Running init script: %s", script)
            self.run_command([runtime, script_path])

    def init_db(self):
        """ Load and initialize DB support """
        # Local imports
        # from tools import this  # pylint: disable=E0401,C0415
        from pylon.framework.db import db_migrations  # pylint: disable=C0415
        # Step: load models
        module_pkg = self.loader.module_name
        #
        if self.loader.has_directory("db/models"):
            for model_resource in importlib.resources.contents(
                    f"{module_pkg}.db.models"
            ):
                if not self.loader.has_file(f"db/models/{model_resource}"):
                    continue
                if model_resource.startswith("_") or not model_resource.endswith(".py"):
                    continue
                #
                resource_name, _ = os.path.splitext(model_resource)
                #
                try:
                    importlib.import_module(
                        f"{module_pkg}.db.models.{resource_name}"
                    )
                except:  # pylint: disable=W0702
                    log.exception(
                        "Failed to import DB model module: %s",
                        resource_name,
                    )
                    continue
        # Step: create entities
        # module_this = this.for_module(module_pkg)
        # db_namespace_helper = module_this.spaces.get("db_namespace_helper", None)
        # if db_namespace_helper is not None:
        #     db_namespaces = db_namespace_helper.get_namespaces()
        # Step: run migrations
        if self.loader.has_directory("db/migrations"):
            db_migrations.run_db_migrations(self.module, self.context.db.url)
        # Step: run automigrations

    def init_all(  # pylint: disable=R0913
            self,
            url_prefix=None, static_url_prefix=None, use_template_prefix=True,
            register_in_app=True, module_routes=True,
            module_slots=True,
            module_rpcs=True,
            module_events=True,
            module_sios=True,
            module_methods=True,
            module_inits=True
        ):
        """ Shortcut to perform fast basic init of this module services """
        self.init_rpcs(module_rpcs)
        self.init_events(module_events)
        self.init_slots(module_slots)
        self.init_sio(module_sios)
        self.init_api()
        self.init_methods(module_methods)
        self.init_db()
        self.init_inits(module_inits)
        self.init_scripts()
        #
        return self.init_blueprint(
            url_prefix, static_url_prefix, use_template_prefix, register_in_app, module_routes
        )

    def deinit_deinits(self, module_deinits=True):
        """ Run all decorated deinits from this module """
        # NB: Deinits are loaded by init_methods()
        deinits = web.deinits_registry.pop(f"plugins.{self.name}", [])
        for deinit in deinits:
            if module_deinits:
                deinit(self.module)
            else:
                deinit()

    def deinit_all(  # pylint: disable=R0913
            self,
            module_deinits=True
        ):
        """ Shortcut to perform fast basic deinit of this module services """
        self.deinit_deinits(module_deinits)

    def template_name(self, name, module=None):
        """ Make prefixed template name """
        if module is None:
            module = self.name
        #
        return f"{module}:{name}"

    def render_template(self, name, **context):
        """ Render tempate from this module """
        module = self.name
        return flask.render_template(f"{module}:{name}", **context)

    def register_tool(self, name, tool):
        """ Register package or object in tools namespace """
        if hasattr(sys.modules["tools"], name):
            raise RuntimeError(f"Tool is already registered: {name}")
        #
        setattr(sys.modules["tools"], name, tool)

    def unregister_tool(self, name):
        """ Unregister package or object from tools namespace """
        if not hasattr(sys.modules["tools"], name):
            raise RuntimeError(f"Tool is not registered: {name}")
        #
        delattr(sys.modules["tools"], name)

    def run_command(self, *args, **kwargs):
        """ Run command with PATH set to installed requirements 'bin' """
        target_kwargs = kwargs.copy()
        #
        if "env" in target_kwargs:
            environ = target_kwargs.pop("env").copy()
        else:
            environ = os.environ.copy()
        #
        environ_path = environ.pop("PATH", None)
        if not environ_path:
            environ_path = os.defpath
        #
        new_path = [
            os.path.join(base, "bin") for base in reversed(self.activated_bases)
        ]
        new_path.extend(environ_path.split(os.pathsep))
        #
        environ["PATH"] = os.pathsep.join(new_path)
        environ["PYTHONUSERBASE"] = self.requirements_base
        environ["PYTHONPATH"] = os.pathsep.join(self.activated_paths)
        #
        return process.run_command(*args, **target_kwargs, env=environ)
