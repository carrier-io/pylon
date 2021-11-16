#!/usr/bin/python3
# coding=utf-8

#   Copyright 2021 getcarrier.io
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

""" RequirementsProvider """


class RequirementsProviderModel:
    """ Provider model """

    # def __init__(self, context, settings):

    def init(self):
        """ Initialize provider """
        raise NotImplementedError()

    def deinit(self):
        """ De-initialize provider """
        raise NotImplementedError()

    def requirements_exist(self, plugin_name, cache_hash):
        """ Check if plugin requirements exist """
        raise NotImplementedError()

    def get_requirements(self, plugin_name, cache_hash, temporary_objects=None):
        """ Get plugin requirements (a.k.a user site data) """
        raise NotImplementedError()

    def add_requirements(self, plugin_name, cache_hash, path):
        """ Add plugin requirements (a.k.a user site data) """
        raise NotImplementedError()

    def delete_requirements(self, plugin_name):
        """ Delete plugin requirements (a.k.a user site data) """
        raise NotImplementedError()
