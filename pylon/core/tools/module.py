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
import shutil
import zipfile
import tempfile
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


class ModuleManager:
    """ Manages modules """

    def __init__(self, context):
        self.context = context
        self.settings = self.context.settings
        self.modules = dict()  # module_name -> (module_root_path, module_metadata, module_obj)
        self.metadata = dict()  # module_obj -> module_metadata
        #
        self.temporary_data_dirs = list()
        # Register provider for template and resource loading from modules
        pkg_resources.register_loader_type(DataModuleLoader, DataModuleProvider)

    def add_module(self, module_name, module_root_path, module_metadata, module_obj):
        """ Register module """
        self.modules[module_name] = (module_root_path, module_metadata, module_obj)
        self.metadata[module_obj] = (module_root_path, module_metadata, module_name)

    def get_module(self, module_name):
        """ Get loaded module """
        return self.modules.get(module_name, None)

    def get_metadata(self, module_obj):
        """ Get module metadata """
        return self.metadata.get(module_obj, None)

    def init_modules(self):
        """ Load and init modules """
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


class DataModuleLoader(importlib.abc.MetaPathFinder):
    """ Allows to load modules from ZIP in-memory data """

    def __init__(self, module_data):
        self.storage = zipfile.ZipFile(io.BytesIO(module_data))
        self.storage_files = [item.filename for item in self.storage.filelist]

    def _fullname_to_filename(self, fullname):
        base = fullname.replace(".", os.sep)
        # Try module directory
        filename = os.path.join(base, "__init__.py")
        if filename in self.storage_files:
            return filename, True
        # Try module file
        filename = f"{base}.py"
        if filename in self.storage_files:
            return filename, False
        # Not found
        return None, None

    def find_spec(self, fullname, path, target=None):  # pylint: disable=W0613
        """ Find spec for new module """
        filename, is_package = self._fullname_to_filename(fullname)
        if filename is None:
            return None
        return importlib.machinery.ModuleSpec(
            fullname, self, origin=filename, is_package=is_package
        )

    def create_module(self, spec):  # pylint: disable=W0613,R0201
        """ Create new module """
        return None

    def exec_module(self, module):
        """ Execute new module """
        module.__file__ = module.__spec__.origin
        module.__dict__["__file__"] = module.__file__
        with self.storage.open(module.__file__, "r") as file:
            exec(file.read(), module.__dict__)  # pylint: disable=W0122

    def get_data(self, path):
        """ Read data resource """
        try:
            with self.storage.open(path, "r") as file:
                data = file.read()
            return data
        except BaseException as exc:
            raise OSError("Resource not found") from exc


class DataModuleProvider(pkg_resources.NullProvider):  # pylint: disable=W0223
    """ Allows to load resources from ZIP in-memory data """

    def __init__(self, module):
        pkg_resources.NullProvider.__init__(self, module)
        self.module_name = getattr(module, "__name__", "")

    def _has(self, path):
        return path in self.loader.storage_files
