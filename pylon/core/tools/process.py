#!/usr/bin/python
# coding=utf-8
# pylint: disable=I0011

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
    Process tools
"""

import subprocess

from pylon.core.tools import log


def run_command(*args, **kwargs):
    """ Run command and log output """
    target_kwargs = kwargs.copy()
    for key in ["stdout", "stderr"]:
        if key in target_kwargs:
            target_kwargs.pop(key)
    #
    with subprocess.Popen(
        *args, **target_kwargs,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    ) as proc:
        #
        while proc.poll() is None:
            while True:
                line = proc.stdout.readline().decode().strip()
                #
                if not line:
                    break
                #
                log.info(line)
        #
        if proc.returncode != 0:
            raise RuntimeError(f"Command failed, return code={proc.returncode}")
