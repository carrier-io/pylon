#!/usr/bin/python
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

""" Context """


class Context:
    """ Application context holder """

    def __init__(self):
        self.__dict__["_context"] = dict()

    def __getattr__(self, name):
        if name not in self._context:
            raise AttributeError(f"{name} not present in current context")
        return self._context[name]

    def __setattr__(self, name, value):
        self._context[name] = value

    def __delattr__(self, name):
        if name in self._context:
            del self._context[name]
