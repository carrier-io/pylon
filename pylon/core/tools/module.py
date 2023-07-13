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

import io
import os
import sys
import json
import types
import shutil
import hashlib
import zipfile
import tempfile
import functools
import posixpath
import subprocess
import importlib
from importlib.abc import MetaPathFinder, ResourceReader
from importlib.machinery import ModuleSpec, PathFinder
from importlib.util import spec_from_file_location

import pkg_resources

import yaml  # pylint: disable=E0401
import flask  # pylint: disable=E0401
import jinja2  # pylint: disable=E0401

from pylon.core.tools import log
from pylon.core.tools import web
from pylon.core.tools import process
from pylon.core.tools import dependency
from pylon.core.tools.dict import recursive_merge
from pylon.core.tools.config import config_substitution, vault_secrets


class ModuleModel:
    """ Module model """

    # def __init__(self, context, descriptor):

    def init(self):
        """ Initialize module """
        raise NotImplementedError()

    def deinit(self):
        """ De-initialize module """
        raise NotImplementedError()


class ModuleDescriptor:  # pylint: disable=R0902
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
        #
        self.requirements_base = None
        self.requirements_path = None
        #
        self.module = None
        self.prepared = False
        self.activated = False

    def load_config(self):
        """ Load custom (or default) configuration """
        #
        base_config_data = dict()
        if self.loader.has_file("config.yml"):
            base_config_data = self._load_yaml_data(self.loader.get_data("config.yml"), "base")
        #
        pylon_config_data = self.context.settings.get("configs", dict()).get(self.name, dict())
        #
        custom_config_data = dict()
        if self.context.module_manager.providers["config"].config_data_exists(self.name):
            custom_config_data = self._load_yaml_data(
                self.context.module_manager.providers["config"].get_config_data(self.name), "custom"
            )
        #
        yaml_data = dict()
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
            yaml_data = dict()
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
            module_name = self.name
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
                    resource = importlib.import_module(
                        f"{module_pkg}.routes.{resource_name}"
                    ).Route
                except:  # pylint: disable=W0702
                    log.exception(
                        "Failed to import Route module: %s",
                        resource_name,
                    )
                    continue
        #
        routes = web.routes_registry.pop(f"plugins.{self.name}", list())
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
                resource_urls = list()
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
            module_name = self.name
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
                    resource = importlib.import_module(
                        f"{module_pkg}.slots.{resource_name}"
                    ).Slot
                except:  # pylint: disable=W0702
                    log.exception(
                        "Failed to import Slot module: %s",
                        resource_name,
                    )
                    continue
        #
        slots = web.slots_registry.pop(f"plugins.{self.name}", list())
        for slot in slots:
            name, obj = slot
            if module_slots:
                obj = functools.partial(obj, self.module)
                obj.__name__ = obj.func.__name__
                obj.__module__ = obj.func.__module__
            self.context.slot_manager.register_callback(name, obj)

    def init_rpcs(self, module_rpcs=True):
        """ Register all decorated RPCs from this module """
        if self.loader.has_directory("rpc"):
            module_pkg = self.loader.module_name
            module_name = self.name
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
                    resource = importlib.import_module(
                        f"{module_pkg}.rpc.{resource_name}"
                    ).RPC
                except:  # pylint: disable=W0702
                    log.exception(
                        "Failed to import RPC module: %s",
                        resource_name,
                    )
                    continue
        #
        rpcs = web.rpcs_registry.pop(f"plugins.{self.name}", list())
        for rpc in rpcs:
            name, proxy_name, obj = rpc
            if module_rpcs:
                obj = functools.partial(obj, self.module)
                obj.__name__ = obj.func.__name__
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

    def init_sio(self, module_sios=True):
        """ Register all decorated SIO event listeners from this module """
        if self.loader.has_directory("sio"):
            module_pkg = self.loader.module_name
            module_name = self.name
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
                    resource = importlib.import_module(
                        f"{module_pkg}.sio.{resource_name}"
                    ).SIO
                except:  # pylint: disable=W0702
                    log.exception(
                        "Failed to import SIO module: %s",
                        resource_name,
                    )
                    continue
        #
        sios = web.sios_registry.pop(f"plugins.{self.name}", list())
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
            module_name = self.name
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
                    resource = importlib.import_module(
                        f"{module_pkg}.events.{resource_name}"
                    ).Event
                except:  # pylint: disable=W0702
                    log.exception(
                        "Failed to import Event module: %s",
                        resource_name,
                    )
                    continue
        #
        events = web.events_registry.pop(f"plugins.{self.name}", list())
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
            module_name = self.name
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
                    resource = importlib.import_module(
                        f"{module_pkg}.methods.{resource_name}"
                    ).Method
                except:  # pylint: disable=W0702
                    log.exception(
                        "Failed to import Method module: %s",
                        resource_name,
                    )
                    continue
        #
        methods = web.methods_registry.pop(f"plugins.{self.name}", list())
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
        inits = web.inits_registry.pop(f"plugins.{self.name}", list())
        for init in inits:
            if module_inits:
                init(self.module)
            else:
                init()

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
        self.init_inits(module_inits)
        return self.init_blueprint(
            url_prefix, static_url_prefix, use_template_prefix, register_in_app, module_routes
        )

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

    def register_tool(self, name, tool):  # pylint: disable=R0201
        """ Register package or object in tools namespace """
        if hasattr(sys.modules["tools"], name):
            raise RuntimeError(f"Tool is already registered: {name}")
        #
        setattr(sys.modules["tools"], name, tool)

    def unregister_tool(self, name):  # pylint: disable=R0201
        """ Unregister package or object from tools namespace """
        if not hasattr(sys.modules["tools"], name):
            raise RuntimeError(f"Tool is not registered: {name}")
        #
        delattr(sys.modules["tools"], name)


class ModuleManager:
    """ Manages modules """

    def __init__(self, context):
        self.context = context
        self.settings = self.context.settings.get("modules", dict())
        self.providers = dict()  # object_type -> provider_instance
        self.modules = dict()  # module_name -> module_descriptor
        self.temporary_objects = list()
        #
        self.descriptor = ModuleDescriptorProxy(self)
        self.module = ModuleProxy(self)

    def init_modules(self):
        """ Load and init modules """
        if self.context.debug and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
            log.info(
                "Running in development mode before reloader is started. Skipping module loading"
            )
            return
        # Disable bytecode caching and register resource providers
        sys.dont_write_bytecode = True
        pkg_resources.register_loader_type(DataModuleLoader, DataModuleProvider)
        # Make plugins holder
        if "plugins" not in sys.modules:
            sys.modules["plugins"] = types.ModuleType("plugins")
            sys.modules["plugins"].__path__ = []
        # Make tools holder
        if "tools" not in sys.modules:
            sys.modules["tools"] = types.ModuleType("tools")
            sys.modules["tools"].__path__ = []
        # Register context as a tool
        setattr(sys.modules["tools"], "context", self.context)
        # Make providers
        self._init_providers()
        #
        # Preload
        #
        log.info("Preloading modules")
        # Create loaders for preload modules
        preload_module_meta_map = self._make_preload_module_meta_map()
        # Resolve preload module load order
        preload_module_order = dependency.resolve_depencies(
            preload_module_meta_map, list(self.modules),
        )
        # Make preload module descriptors
        preload_module_descriptors = self._make_descriptors(
            preload_module_meta_map, preload_module_order,
        )
        # Install/get/activate requirements and initialize preload modules
        preloaded_items = self._prepare_modules(preload_module_descriptors)
        self._activate_modules(preload_module_descriptors)
        #
        # Target
        #
        log.info("Preparing modules")
        # Create loaders for target modules
        target_module_meta_map = self._make_target_module_meta_map()
        # Resolve target module load order
        target_module_order = dependency.resolve_depencies(
            target_module_meta_map, list(self.modules),
        )
        # Make target module descriptors
        target_module_descriptors = self._make_descriptors(
            target_module_meta_map, target_module_order,
        )
        # Install/get requirements
        self._prepare_modules(target_module_descriptors, preloaded_items)
        # Activate and init modules
        log.info("Activating modules")
        self._activate_modules(target_module_descriptors)

    def _make_preload_module_meta_map(self):
        module_meta_map = dict()  # module_name -> (metadata, loader)
        #
        if "preload" not in self.settings:
            return module_meta_map
        #
        for module_name in self.settings["preload"]:
            if not self.providers["plugins"].plugin_exists(module_name):
                module_target = self.settings["preload"][module_name].copy()
                #
                if "provider" not in module_target or \
                        "type" not in module_target["provider"]:
                    continue
                #
                provider_config = module_target.pop("provider").copy()
                provider_type = provider_config.pop("type")
                #
                try:
                    provider = importlib.import_module(
                        f"pylon.core.providers.source.{provider_type}"
                    ).Provider(self.context, provider_config)
                    provider.init()
                    #
                    module_source = provider.get_source(module_target)
                    #
                    provider.deinit()
                except:  # pylint: disable=W0702
                    log.exception("Could not preload module: %s", module_name)
                    continue
                #
                self.providers["plugins"].add_plugin(module_name, module_source)
            #
            try:
                module_loader, module_metadata = self._make_loader_and_metadata(module_name)
            except:  # pylint: disable=W0702
                log.exception("Could not make module loader: %s", module_name)
                continue
            #
            module_meta_map[module_name] = (module_metadata, module_loader)
        #
        return module_meta_map

    def _make_target_module_meta_map(self):
        module_meta_map = dict()  # module_name -> (metadata, loader)
        #
        for module_name in self.providers["plugins"].list_plugins(exclude=list(self.modules)):
            try:
                module_loader, module_metadata = self._make_loader_and_metadata(module_name)
            except:  # pylint: disable=W0702
                log.exception("Could not make module loader: %s", module_name)
                continue
            #
            module_meta_map[module_name] = (module_metadata, module_loader)
        #
        return module_meta_map

    def _make_loader_and_metadata(self, module_name):
        module_loader = self.providers["plugins"].get_plugin_loader(module_name)
        #
        if not module_loader.has_file("metadata.json"):
            raise ValueError(f"Module has no metadata: {module_name}")
        #
        module_metadata = json.loads(module_loader.get_data("metadata.json"))
        #
        if module_loader.has_directory("static") or module_metadata.get("extract", False):
            module_loader = module_loader.get_local_loader(self.temporary_objects)
        #
        return module_loader, module_metadata

    def _make_descriptors(self, module_meta_map, module_order):
        module_descriptors = list()
        #
        for module_name in module_order:
            module_metadata, module_loader = module_meta_map[module_name]
            # Get module requirements
            if module_loader.has_file("requirements.txt"):
                module_requirements = module_loader.get_data("requirements.txt").decode()
            else:
                module_requirements = ""
            # Make descriptor
            module_descriptor = ModuleDescriptor(
                self.context, module_name, module_loader, module_metadata, module_requirements
            )
            # Preload config
            module_descriptor.load_config()
            #
            module_descriptors.append(module_descriptor)
        #
        return module_descriptors

    def _prepare_modules(self, module_descriptors, prepared_items=None):  # pylint: disable=R0914,R0915
        if prepared_items is None:
            cache_hash_chunks = list()
            module_site_paths = list()
            module_constraint_paths = list()
        else:
            cache_hash_chunks, module_site_paths, module_constraint_paths = prepared_items
        #
        for module_descriptor in module_descriptors:
            if module_descriptor.name in self.settings.get("skip", []):
                log.warning("Skipping module init %s", module_descriptor.name)
                continue
            all_required_dependencies_present = True
            #
            for required_dependency in module_descriptor.metadata.get("depends_on", list()):
                if required_dependency not in self.modules:
                    log.error(
                        "Required dependency is not present: %s (required by %s)",
                        required_dependency, module_descriptor.name,
                    )
                    all_required_dependencies_present = False
            #
            if not all_required_dependencies_present:
                log.error("Skipping module: %s", module_descriptor.name)
                continue
            #
            requirements_hash = hashlib.sha256(module_descriptor.requirements.encode()).hexdigest()
            cache_hash_chunks.append(requirements_hash)
            cache_hash = hashlib.sha256("_".join(cache_hash_chunks).encode()).hexdigest()
            #
            module_name = module_descriptor.name
            #
            requirements_txt_fd, requirements_txt = tempfile.mkstemp(".txt")
            self.temporary_objects.append(requirements_txt)
            os.close(requirements_txt_fd)
            #
            with open(requirements_txt, "wb") as file:
                file.write(module_descriptor.requirements.encode())
            #
            if self.providers["requirements"].requirements_exist(module_name, cache_hash):
                requirements_base = \
                    self.providers["requirements"].get_requirements(
                        module_name, cache_hash, self.temporary_objects,
                    )
            else:
                requirements_base = tempfile.mkdtemp()
                self.temporary_objects.append(requirements_base)
                #
                try:
                    self.install_requirements(
                        requirements_path=requirements_txt,
                        target_site_base=requirements_base,
                        additional_site_paths=module_site_paths,
                        constraint_paths=module_constraint_paths,
                    )
                except:  # pylint: disable=W0702
                    log.exception("Failed to install requirements for: %s", module_descriptor.name)
                    continue
                #
                self.providers["requirements"].add_requirements(
                    module_name, cache_hash, requirements_base,
                )
            #
            requirements_path = self.get_user_site_path(requirements_base)
            module_site_paths.append(requirements_path)
            #
            module_descriptor.requirements_base = requirements_base
            module_descriptor.requirements_path = requirements_path
            #
            requirements_mode = self.settings["requirements"].get("mode", "relaxed")
            if requirements_mode == "constrained":
                module_constraint_paths.append(requirements_txt)
            elif requirements_mode == "strict":
                frozen_module_requirements = self.freeze_site_requirements(
                    target_site_base=requirements_base,
                    requirements_path=requirements_txt,
                    additional_site_paths=module_site_paths,
                )
                #
                frozen_requirements_fd, frozen_requirements = tempfile.mkstemp(".txt")
                self.temporary_objects.append(frozen_requirements)
                os.close(frozen_requirements_fd)
                #
                with open(frozen_requirements, "wb") as file:
                    file.write(frozen_module_requirements.encode())
                #
                module_constraint_paths.append(frozen_requirements)
            #
            module_descriptor.prepared = True
        #
        return cache_hash_chunks, module_site_paths, module_constraint_paths

    def _activate_modules(self, module_descriptors):  # pylint: disable=R0914,R0915
        for module_descriptor in module_descriptors:
            if not module_descriptor.prepared:
                log.warning("Skipping un-prepared module: %s", module_descriptor.name)
            #
            self.activate_path(module_descriptor.requirements_path)
            self.activate_loader(module_descriptor.loader)
            #
            try:
                module_pkg = importlib.import_module(f"plugins.{module_descriptor.name}.module")
                module_obj = module_pkg.Module(
                    context=self.context,
                    descriptor=module_descriptor,
                )
                module_descriptor.module = module_obj
                module_obj.init()
            except:  # pylint: disable=W0702
                log.exception("Failed to enable module: %s", module_descriptor.name)
                continue
            #
            self.modules[module_descriptor.name] = module_descriptor
            module_descriptor.activated = True

    def deinit_modules(self):
        """ De-init and unload modules """
        if self.context.debug and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
            log.info(
                "Running in development mode before reloader is started. Skipping module unloading"
            )
            return
        #
        for module_name in reversed(list(self.modules)):
            try:
                self.modules[module_name].module.deinit()
            except:  # pylint: disable=W0702
                pass
        #
        self._deinit_providers()
        #
        for obj in self.temporary_objects:
            try:
                if os.path.isdir(obj):
                    shutil.rmtree(obj)
                else:
                    os.remove(obj)
            except:  # pylint: disable=W0702
                pass

    def _init_providers(self):
        for key in ["plugins", "requirements", "config"]:
            log.info("Initializing %s provider", key)
            #
            if key not in self.settings or \
                    "provider" not in self.settings[key] or \
                    "type" not in self.settings[key]["provider"]:
                raise RuntimeError(f"No {key} provider set in config")
            #
            provider_config = self.settings[key]["provider"].copy()
            provider_type = provider_config.pop("type")
            #
            provider = importlib.import_module(
                f"pylon.core.providers.{key}.{provider_type}"
            ).Provider(self.context, provider_config)
            provider.init()
            #
            self.providers[key] = provider

    def _deinit_providers(self):
        for key, provider in self.providers.items():
            log.info("Deinitializing %s provider", key)
            try:
                provider.deinit()
            except:  # pylint: disable=W0702
                pass

    @staticmethod
    def activate_loader(loader):
        """ Activate loader """
        sys.meta_path.insert(0, loader)
        importlib.invalidate_caches()
        pkg_resources._initialize_master_working_set()  # pylint: disable=W0212

    @staticmethod
    def activate_path(path):
        """ Activate path """
        sys.path.insert(0, path)
        importlib.invalidate_caches()
        pkg_resources._initialize_master_working_set()  # pylint: disable=W0212

    @staticmethod
    def get_user_site_path(base):
        """ Get site path for specific site base """
        env = os.environ.copy()
        env["PYTHONUSERBASE"] = base
        #
        return subprocess.check_output(
            [sys.executable, "-m", "site", "--user-site"],
            env=env,
        ).decode().strip()

    @staticmethod
    def install_requirements(
            requirements_path, target_site_base, additional_site_paths=None, constraint_paths=None,
        ):
        """ Install requirements into target site """
        if constraint_paths is None:
            constraint_paths = list()
        #
        env = os.environ.copy()
        env["PYTHONUSERBASE"] = target_site_base
        #
        if additional_site_paths is not None:
            env["PYTHONPATH"] = os.pathsep.join(additional_site_paths)
        #
        c_args = []
        for const in constraint_paths:
            c_args.append("-c")
            c_args.append(const)
        #
        return process.run_command(
            [
                sys.executable,
                "-m", "pip", "install",
                "--user", "--no-warn-script-location",
            ] + c_args + [
                "-r", requirements_path,
            ],
            env=env,
        )

    @staticmethod
    def freeze_site_requirements(
            target_site_base, requirements_path=None, additional_site_paths=None
        ):
        """ Get installed requirements (a.k.a pip freeze) """
        env = os.environ.copy()
        env["PYTHONUSERBASE"] = target_site_base
        #
        if additional_site_paths is not None:
            env["PYTHONPATH"] = os.pathsep.join(additional_site_paths)
        #
        opt_args = []
        if requirements_path is not None:
            opt_args.append("-r")
            opt_args.append(requirements_path)
        #
        return subprocess.check_output(
            [sys.executable, "-m", "pip", "freeze", "--user"] + opt_args,
            env=env,
        ).decode()


class ModuleProxy:  # pylint: disable=R0903
    """ Module proxy - syntax sugar for module access """

    def __init__(self, module_manager):
        self.__module_manager = module_manager

    def __getattr__(self, name):
        return self.__module_manager.modules[name].module


class ModuleDescriptorProxy:  # pylint: disable=R0903
    """ Module descriptor proxy - syntax sugar for module descriptor access """

    def __init__(self, module_manager):
        self.__module_manager = module_manager

    def __getattr__(self, name):
        return self.__module_manager.modules[name]


class LocalModuleLoader(PathFinder):
    """ Allows to load modules from specific location """

    def __init__(self, module_name, module_path):
        self.module_name = module_name
        self.module_name_components = self.module_name.split(".")
        self.module_path = module_path
        self.module_abspath = os.path.abspath(self.module_path)

    def _fullname_to_filename(self, fullname):
        base = fullname.replace(".", os.sep)
        # Try module directory
        filename = os.path.join(self.module_abspath, base, "__init__.py")
        if os.path.isfile(filename):
            return filename
        # Try module file
        filename = os.path.join(self.module_abspath, f"{base}.py")
        if os.path.isfile(filename):
            return filename
        # Not found
        return None

    def find_spec(self, fullname, path=None, target=None):
        """ Find spec for new module """
        name_components = fullname.split(".")
        if name_components[:len(self.module_name_components)] != self.module_name_components:
            return None
        #
        filename = self._fullname_to_filename(
            ".".join(name_components[len(self.module_name_components):])
        )
        if filename is None:
            return None
        #
        return spec_from_file_location(fullname, filename)

    def get_data(self, path):
        """ Read data resource """
        try:
            with open(os.path.join(self.module_abspath, path), "rb") as file:
                data = file.read()
            return data
        except BaseException as exc:
            raise FileNotFoundError(f"Resource not found: {path}") from exc

    def has_file(self, path):
        """ Check if file is present in module """
        return os.path.isfile(os.path.join(self.module_abspath, path))

    def has_directory(self, path):
        """ Check if directory is present in module """
        return os.path.isdir(os.path.join(self.module_abspath, path))

    def get_local_path(self):
        """ Get path to module data """
        return self.module_abspath

    def get_local_loader(self, temporary_objects=None):    # pylint: disable=W0613
        """ Get LocalModuleLoader from this module data """
        return self


class DataModuleLoader(MetaPathFinder):
    """ Allows to load modules from ZIP in-memory data """

    def __init__(self, module_name, module_data):
        self.module_name = module_name
        self.module_name_components = self.module_name.split(".")
        self.storage = zipfile.ZipFile(io.BytesIO(module_data))
        self.storage_files = [item.filename for item in self.storage.filelist]

    def _fullname_to_filename(self, fullname):
        base = fullname.replace(".", posixpath.sep)
        # Try module directory
        filename = posixpath.join(base, "__init__.py")
        if filename in self.storage_files:
            return filename, True
        # Try module file
        filename = f"{base}.py"
        if filename in self.storage_files:
            return filename, False
        # Not found
        return None, None

    def find_spec(self, fullname, path=None, target=None):  # pylint: disable=W0613
        """ Find spec for new module """
        name_components = fullname.split(".")
        if name_components[:len(self.module_name_components)] != self.module_name_components:
            return None
        #
        filename, is_package = self._fullname_to_filename(
            ".".join(name_components[len(self.module_name_components):])
        )
        if filename is None:
            return None
        #
        return ModuleSpec(
            fullname, self, origin=filename, is_package=is_package
        )

    def create_module(self, spec):  # pylint: disable=W0613,R0201
        """ Create new module """
        return None

    def exec_module(self, module):
        """ Execute new module """
        module.__file__ = module.__spec__.origin
        module.__cached__ = None
        #
        with self.storage.open(module.__file__, "r") as file:
            code = compile(
                source=file.read(),
                filename=f"{self.module_name}:{module.__file__}",
                mode="exec",
                dont_inherit=True,
            )
            exec(code, module.__dict__)  # pylint: disable=W0122

    def get_data(self, path):
        """ Read data resource """
        if os.sep != posixpath.sep:
            path = path.replace(os.sep, posixpath.sep)
        #
        try:
            with self.storage.open(path, "r") as file:
                data = file.read()
            return data
        except BaseException as exc:
            raise FileNotFoundError(f"Resource not found: {path}") from exc

    def has_file(self, path):
        """ Check if file is present in module """
        if os.sep != posixpath.sep:
            path = path.replace(os.sep, posixpath.sep)
        #
        return path in self.storage_files

    def has_directory(self, path):
        """ Check if directory is present in module """
        if os.sep != posixpath.sep:
            path = path.replace(os.sep, posixpath.sep)
        #
        if not path.endswith(posixpath.sep):
            path = f"{path}{posixpath.sep}"
        #
        return path in self.storage_files

    def get_resource_reader(self, fullname):
        """ Get ResourceReader """
        name_components = fullname.split(".")
        return DataModuleResourceReader(
            self, posixpath.sep.join(name_components[len(self.module_name_components):])
        )

    def get_local_path(self):    # pylint: disable=R0201
        """ Get path to module data """
        return None

    def get_local_loader(self, temporary_objects=None):
        """ Get LocalModuleLoader from this module data """
        local_path = tempfile.mkdtemp()
        if temporary_objects is not None:
            temporary_objects.append(local_path)
        self.storage.extractall(local_path)
        return LocalModuleLoader(self.module_name, local_path)


class DataModuleProvider(pkg_resources.NullProvider):  # pylint: disable=W0223
    """ Allows to load resources from ZIP in-memory data """

    def _has(self, path):
        if os.sep != posixpath.sep:
            path = path.replace(os.sep, posixpath.sep)
        #
        return \
            not path or path in self.loader.storage_files or f"{path}/" in self.loader.storage_files

    def _isdir(self, path):
        if os.sep != posixpath.sep:
            path = path.replace(os.sep, posixpath.sep)
        #
        if path in self.loader.storage_files:
            return path.endswith(posixpath.sep)
        if not path or f"{path}/" in self.loader.storage_files:
            return True
        #
        return False

    def _listdir(self, path):
        if os.sep != posixpath.sep:
            path = path.replace(os.sep, posixpath.sep)
        #
        if not self._has(path):
            raise FileNotFoundError(f"Path not found: {path}")
        if not self._isdir(path):
            raise NotADirectoryError(f"Not a directory: {path}")
        #
        components = len(path.split(posixpath.sep)) if path else 0
        #
        files = [
            item.split(posixpath.sep)[-1] for item in self.loader.storage_files
            if item.split(posixpath.sep)[-1] and
            len(item.split(posixpath.sep)) == components + 1
        ]
        dirs = [
            item.split(posixpath.sep)[-2] for item in self.loader.storage_files
            if not item.split(posixpath.sep)[-1] and
            len(item.split(posixpath.sep)) == components + 2
        ]
        #
        return files + dirs


class DataModuleResourceReader(ResourceReader):
    """ Allows to read resources from ZIP in-memory data """

    def __init__(self, loader, path):
        self.loader = loader
        self.path = path

    def open_resource(self, resource):
        """ Implementation of open_resource """
        if os.sep != posixpath.sep:
            resource = resource.replace(os.sep, posixpath.sep)
        #
        try:
            return self.loader.storage.open(resource, "r")
        except BaseException as exc:
            raise FileNotFoundError(f"Resource not found: {resource}") from exc

    def resource_path(self, resource):
        """ Implementation of resource_path """
        if os.sep != posixpath.sep:
            resource = resource.replace(os.sep, posixpath.sep)
        #
        raise FileNotFoundError(f"Path to resource not found: {resource}")

    def is_resource(self, name):
        """ Implementation of is_resource """
        if os.sep != posixpath.sep:
            name = name.replace(os.sep, posixpath.sep)
        #
        if name in self.loader.storage_files:
            return not name.endswith(posixpath.sep)
        #
        return False

    def contents(self):
        """ Implementation of contents """
        path = self.path
        #
        if os.sep != posixpath.sep:
            path = path.replace(os.sep, posixpath.sep)
        #
        components = len(path.split(posixpath.sep)) if path else 0
        #
        files = [
            item.split(posixpath.sep)[-1] for item in self.loader.storage_files
            if item.split(posixpath.sep)[-1] and
            len(item.split(posixpath.sep)) == components + 1
        ]
        dirs = [
            item.split(posixpath.sep)[-2] for item in self.loader.storage_files
            if not item.split(posixpath.sep)[-1] and
            len(item.split(posixpath.sep)) == components + 2
        ]
        #
        return files + dirs
