#!/usr/bin/python
# coding=utf-8
# pylint: disable=C0302

#   Copyright 2024 getcarrier.io
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

import inspect

from pylon.core.tools import db_support
from pylon.core.tools.context import Context


class This:  # pylint: disable=R0903
    """ Module-specific tools/helpers """

    def __init__(self, context):
        self.__context = context
        self.__modules = {}
        self.__spaces = {}

    def __getattr__(self, name):
        module_name = None
        caller_module = inspect.currentframe().f_back.f_globals["__name__"]
        #
        if caller_module.startswith("plugins."):
            module_name = caller_module.split(".")[1]
        #
        if module_name is None:
            raise RuntimeError(f"Caller is not a pylon module: {caller_module}")
        #
        exact = self.for_module(module_name)
        return getattr(exact, name)

    def for_module(self, name):
        """ Get exact for known module name """
        if name not in self.__modules:
            self.__modules[name] = ModuleThis(self.__context, self.__spaces, name)
        #
        return self.__modules[name]


class ModuleThis:  # pylint: disable=R0903
    """ Exact module-specific tools/helpers """

    def __init__(self, context, spaces, module_name):
        self.context = context
        self.spaces = spaces
        self.module_name = module_name
        #
        self.data = Context()
        #
        self.db = db_support.make_module_entities(self.context, self.spaces)
