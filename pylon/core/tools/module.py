#!/usr/bin/python
# coding=utf-8

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
import importlib
import subprocess
import pkg_resources

import yaml  # pylint: disable=E0401
import flask  # pylint: disable=E0401
import jinja2  # pylint: disable=E0401

from pylon.core.tools import log
from pylon.core.tools import web
from pylon.core.tools import dependency
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


class ModuleDescriptor:
    """ Module descriptor """

    def __init__(self, context, name, loader, metadata, requirements):
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

    def load_config(self):
        """ Load custom (or default) configuration """
        if self.context.module_manager.providers["config"].config_data_exists(self.name):
            config_data = self.context.module_manager.providers["config"].get_config_data(self.name)
        elif self.loader.has_file("config.yml"):
            config_data = self.loader.get_data("config.yml")
        else:
            config_data = b""
        #
        yaml_data = yaml.load(os.path.expandvars(config_data), Loader=yaml.SafeLoader)
        if yaml_data is None:
            yaml_data = dict()
        #
        self.config = config_substitution(yaml_data, vault_secrets(self.context.settings))

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
            url_prefix = f"{self.context.url_prefix}/{self.name}"
        #
        static_folder = None
        if self.loader.has_directory("static"):
            static_folder = "static"
            if static_url_prefix is None:
                static_url_prefix = f"{self.context.url_prefix}/static/{self.name}"
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

    def init_blueprint(
            self,
            url_prefix=None, static_url_prefix=None, use_template_prefix=True,
            register_in_app=True, module_routes=True,
        ):
        """ Make and register blueprint with pre-registered routes """
        # Make Blueprint
        result_blueprint = self.make_blueprint(url_prefix, static_url_prefix, use_template_prefix)
        # Add routes
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


class ModuleManager:
    """ Manages modules """

    def __init__(self, context):
        self.context = context
        self.settings = self.context.settings.get("modules", dict())
        self.providers = dict()  # object_type -> provider_instance
        self.modules = dict()  # module_name -> module_descriptor
        self.temporary_objects = list()

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
        # Make providers
        self._init_providers()
        # TODO: preload
        # Create loaders for target modules
        module_meta_map = dict()  # module_name -> (metadata, loader)
        for module_name in self.providers["plugins"].list_plugins(exclude=list(self.modules)):
            module_loader = self.providers["plugins"].get_plugin_loader(module_name)
            #
            if not module_loader.has_file("metadata.json"):
                log.error("Module has no metadata: %s", module_name)
                continue
            #
            module_metadata = json.loads(module_loader.get_data("metadata.json"))
            #
            if module_loader.has_directory("static") or module_metadata.get("extract", False):
                module_loader = module_loader.get_local_loader(self.temporary_objects)
            #
            module_meta_map[module_name] = (module_metadata, module_loader)
        # Resolve module load order
        module_order = dependency.resolve_depencies(module_meta_map)
        log.debug("Module order: %s", module_order)
        # Make module descriptors
        module_descriptors = list()
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
        # Install/get/activate requirements and initialize module
        cache_hash_chunks = list()
        module_site_paths = list()
        module_constraint_paths = list()
        #
        for module_descriptor in module_descriptors:
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
                self.install_requirements(
                    requirements_path=requirements_txt,
                    target_site_base=requirements_base,
                    additional_site_paths=module_site_paths,
                    constraint_paths=module_constraint_paths,
                )
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
            self.activate_path(module_descriptor.requirements_path)
            self.activate_loader(module_descriptor.loader)
            #
            module_pkg = importlib.import_module(f"plugins.{module_descriptor.name}.module")
            module_obj = module_pkg.Module(
                context=self.context,
                descriptor=module_descriptor,
            )
            #
            module_descriptor.module = module_obj
            #
            module_obj.init()
            #
            self.modules[module_descriptor.name] = module_descriptor

    def deinit_modules(self):
        """ De-init and unload modules """
        if self.context.debug and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
            log.info(
                "Running in development mode before reloader is started. Skipping module unloading"
            )
            return
        #
        for _, module_descriptor in self.modules.items():
            try:
                module_descriptor.module.deinit()
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
            provider.deinit()

    @staticmethod
    def activate_loader(loader):
        """ Activate loader """
        sys.meta_path.insert(0, loader)
        importlib.invalidate_caches()

    @staticmethod
    def activate_path(path):
        """ Activate path """
        sys.path.insert(0, path)
        importlib.invalidate_caches()

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
        return subprocess.check_call(
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


class LocalModuleLoader(importlib.machinery.PathFinder):
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
        return importlib.util.spec_from_file_location(fullname, filename)

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

    def get_local_loader(self, temporary_objects=None):
        """ Get LocalModuleLoader from this module data """
        return self


class DataModuleLoader(importlib.abc.MetaPathFinder):
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
        return importlib.machinery.ModuleSpec(
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

    def get_local_path(self):
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


class DataModuleResourceReader(importlib.abc.ResourceReader):
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
