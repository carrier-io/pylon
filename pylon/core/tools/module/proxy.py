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
