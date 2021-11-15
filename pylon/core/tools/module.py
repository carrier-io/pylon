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
import zipfile
import tempfile
import posixpath
import importlib
import pkg_resources

from pylon.core.tools import log
from pylon.core.tools import storage
from pylon.core.tools import dependency


class ModuleModel:
    """ Module model """

    # def __init__(self, context, descriptor):

    def init(self):
        """ Initialize module """
        raise NotImplementedError()

    def deinit(self):
        """ De-initialize module """
        raise NotImplementedError()


class ModuleDescriptior:
    """ Module descriptor """

    def __init__(self, context, settings, root_path):
        self.context = context
        self.settings = settings
        self.root_path = root_path

    def make_blueprint(self):
        """ Make configured Blueprint instance """

    def template_name(self, name, module=None):
        """ Make prefixed template name """


class ModuleManager:
    """ Manages modules """

    def __init__(self, context):
        self.context = context
        self.settings = self.context.settings
        #
        self.modules = dict()  # module_name -> module_descriptor
        self.temporary_data_dirs = list()

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
        #
        #
        if not self.context.debug:
            self.temporary_data_dirs = load_modules(self.context)
        else:
            self.temporary_data_dirs = load_development_modules(self.context)

    def deinit_modules(self):
        """ De-init and unload modules """
        for module_name in self.modules:
            _, _, module_obj = self.get_module(module_name)
            module_obj.deinit()
        # Delete module data dirs
        for directory in self.temporary_data_dirs:
            log.info("Deleting temporary data directory: %s", directory)
            try:
                shutil.rmtree(directory)
            except:  # pylint: disable=W0702
                log.exception("Failed to delete, skipping")


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
            module_loader = DataModuleLoader(module_data)
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
    """ Dev """
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
    """ Dev """
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

    def has_directory(self, path):
        """ Check if directory is present in module """
        return os.path.isdir(os.path.join(self.module_abspath, path))


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
