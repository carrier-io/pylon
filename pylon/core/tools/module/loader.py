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
import zipfile
import tempfile
import posixpath
from importlib.abc import MetaPathFinder, ResourceReader
from importlib.machinery import ModuleSpec, PathFinder
from importlib.util import spec_from_file_location

import pkg_resources


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

    def find_spec(self, fullname, path=None, target=None):  # pylint: disable=W0237
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
        self.storage = zipfile.ZipFile(io.BytesIO(module_data))  # pylint: disable=R1732
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

    def create_module(self, spec):  # pylint: disable=W0613
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

    def is_resource(self, name):  # pylint: disable=W0237
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
