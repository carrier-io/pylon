#!/usr/bin/python3
# coding=utf-8

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

""" Toolkit """

import sys
import types

from pylon.core.tools.module.this import This


def init(context):
    """ Make tools holder and pre-populate toolkit """
    # Make tools holder
    if "tools" not in sys.modules:
        sys.modules["tools"] = types.ModuleType("tools")
        sys.modules["tools"].__path__ = []
    # Register context as a tool
    setattr(sys.modules["tools"], "context", context)
    # Register module helpers as a tool
    setattr(sys.modules["tools"], "this", This(context))
