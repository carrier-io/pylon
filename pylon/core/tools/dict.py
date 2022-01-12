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

"""
    Dict tools
"""


def recursive_merge(dict_a, dict_b):
    """ Merge dictionaries recursively """
    result = dict()
    for key in set(list(dict_a.keys()) + list(dict_b.keys())):
        if key not in dict_a:
            result[key] = dict_b[key]
        elif key not in dict_b:
            result[key] = dict_a[key]
        elif isinstance(dict_a[key], dict) and isinstance(dict_b[key], dict):
            result[key] = recursive_merge(dict_a[key], dict_b[key])
        else:
            result[key] = dict_b[key]
    return result
