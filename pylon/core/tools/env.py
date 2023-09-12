#!/usr/bin/python
# coding=utf-8
# pylint: disable=I0011,E0401

#   Copyright 2023 getcarrier.io
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

"""
    Environment tools
"""

import os


def get_var(name, default=""):
    """ Allows to use get environmental variables with CORE_ and PYLON_ prefix """
    return os.environ.get(
        f"PYLON_{name}",
        os.environ.get(
            f"CORE_{name}", default
        )
    )
