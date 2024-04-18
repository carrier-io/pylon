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
import json
import types
import shutil
import hashlib
import tempfile
import subprocess
import importlib

import pkg_resources

from pylon.core.tools import (
    log,
    process,
    dependency,
    env,
    db_support,
)

from .proxy import (
    ModuleProxy,
    ModuleDescriptorProxy,
)
from .loader import (
    DataModuleLoader,
    DataModuleProvider,
)
from .descriptor import ModuleDescriptor
from .this import This


class ModuleManager:
    """ Manages modules """

    def __init__(self, context):
        self.context = context
        self.settings = self.context.settings.get("modules", {})
        self.providers = {}  # object_type -> provider_instance
        self.modules = {}  # module_name -> module_descriptor
        self.temporary_objects = []
        #
        self.descriptor = ModuleDescriptorProxy(self)
        self.module = ModuleProxy(self)

    def init_modules(self):
        """ Load and init modules """
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
        # Register module helpers as a tool
        setattr(sys.modules["tools"], "this", This(self.context))
        # Check if actions are needed
        reloader_used = self.context.settings.get("server", {}).get(
            "use_reloader", env.get_var("USE_RELOADER", "true").lower() in ["true", "yes"],
        )
        #
        if self.context.debug and reloader_used and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
            log.info(
                "Running in development mode before reloader is started. Skipping module loading"
            )
            return
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
        module_meta_map = {}  # module_name -> (metadata, loader)
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
        module_meta_map = {}  # module_name -> (metadata, loader)
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
        module_descriptors = []
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
            cache_hash_chunks = []
            module_site_paths = []
            module_constraint_paths = []
        else:
            cache_hash_chunks, module_site_paths, module_constraint_paths = prepared_items
        #
        for module_descriptor in module_descriptors:
            if module_descriptor.name in self.settings.get("skip", []):
                log.warning("Skipping module prepare: %s", module_descriptor.name)
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
                log.info("Installing requirements for: %s", module_descriptor.name)
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
        requirements_activation = self.settings["requirements"].get("activation", "steps")
        #
        if requirements_activation == "bulk":
            log.info("Using bulk module requirements activation mode")
            for module_descriptor in module_descriptors:
                if module_descriptor.prepared:
                    self.activate_path(module_descriptor.requirements_path)
        #
        for module_descriptor in module_descriptors:
            if not module_descriptor.prepared:
                log.warning("Skipping un-prepared module: %s", module_descriptor.name)
            #
            all_required_dependencies_present = True
            #
            for required_dependency in module_descriptor.metadata.get("depends_on", []):
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
            if requirements_activation != "bulk":
                self.activate_path(module_descriptor.requirements_path)
            #
            self.activate_loader(module_descriptor.loader)
            #
            try:
                module_pkg = importlib.import_module(f"plugins.{module_descriptor.name}.module")
                module_obj = module_pkg.Module(
                    context=self.context,
                    descriptor=module_descriptor,
                )
                module_descriptor.module = module_obj
                #
                db_support.create_local_session()
                try:
                    module_obj.init()
                finally:
                    db_support.close_local_session()
                #
            except:  # pylint: disable=W0702
                log.exception("Failed to enable module: %s", module_descriptor.name)
                continue
            #
            self.modules[module_descriptor.name] = module_descriptor
            module_descriptor.activated = True

    def deinit_modules(self):
        """ De-init and unload modules """
        reloader_used = self.context.settings.get("server", {}).get(
            "use_reloader", env.get_var("USE_RELOADER", "true").lower() in ["true", "yes"],
        )
        #
        if self.context.debug and reloader_used and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
            log.info(
                "Running in development mode before reloader is started. Skipping module unloading"
            )
            return
        #
        for module_name in reversed(list(self.modules)):
            try:
                db_support.create_local_session()
                try:
                    self.modules[module_name].module.deinit()
                finally:
                    db_support.close_local_session()
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
        new_env = os.environ.copy()
        new_env["PYTHONUSERBASE"] = base
        #
        return subprocess.check_output(
            [sys.executable, "-m", "site", "--user-site"],
            env=new_env,
        ).decode().strip()

    def install_requirements(
            self, requirements_path, target_site_base,
            additional_site_paths=None, constraint_paths=None,
        ):
        """ Install requirements into target site """
        cache_dir = self.settings["requirements"].get("cache", "/tmp/pylon_pip_cache")
        try:
            os.makedirs(cache_dir, exist_ok=True)
        except:  # pylint: disable=W0702
            pass
        #
        if constraint_paths is None:
            constraint_paths = []
        #
        environ = os.environ.copy()
        environ["PYTHONUSERBASE"] = target_site_base
        #
        if additional_site_paths is not None:
            environ["PYTHONPATH"] = os.pathsep.join(additional_site_paths)
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
                "--disable-pip-version-check",
                "--root-user-action=ignore",
                "--cache-dir", cache_dir,
            ] + c_args + [
                "-r", requirements_path,
            ],
            env=environ,
        )

    def freeze_site_requirements(
            self, target_site_base, requirements_path=None, additional_site_paths=None
        ):
        """ Get installed requirements (a.k.a pip freeze) """
        cache_dir = self.settings["requirements"].get("cache", "/tmp/pylon_pip_cache")
        #
        environ = os.environ.copy()
        environ["PYTHONUSERBASE"] = target_site_base
        #
        if additional_site_paths is not None:
            environ["PYTHONPATH"] = os.pathsep.join(additional_site_paths)
        #
        opt_args = []
        if requirements_path is not None:
            opt_args.append("-r")
            opt_args.append(requirements_path)
        #
        return subprocess.check_output(
            [
                sys.executable,
                "-m", "pip", "freeze",
                "--user",
                "--disable-pip-version-check",
                "--cache-dir", cache_dir,
            ] + opt_args,
            env=environ,
        ).decode()
