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
import zipfile
import importlib
import pkg_resources


class ModuleModel:
    """ Module model """

    def init(self):
        """ Initialize module """
        raise NotImplementedError()

    def deinit(self):
        """ De-initialize module """
        raise NotImplementedError()


class ModuleManager:
    """ Manages modules """

    def __init__(self, settings):
        self.settings = settings
        self.modules = dict()  # module_name -> (module_root_path, module_metadata, module_obj)
        self.metadata = dict()  # module_obj -> module_metadata

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
