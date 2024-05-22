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
    Signal tools
"""

import os
import time
import threading

from pylon.core.tools import log


def signal_sigterm(signal_num, stack_frame):
    """ SIGTERM signal handler: for clean and fast docker stop/restart """
    raise SystemExit


class ZombieReaper(threading.Thread):
    """ Reap zombie processes """

    def __init__(self, context):
        super().__init__(daemon=True)
        #
        self.context = context
        self.interval = int(
            self.context.settings.get(
                "system", {}
            ).get(
                "zombie_reaping", {}
            ).get(
                "interval", 15
            )
        )
        #
        self.external_pids = set()

    def run(self):
        """ Run reaper thread """
        #
        while not self.context.stop_event.is_set():
            try:
                time.sleep(self.interval)
                self._reap_zombies()
            except:  # pylint: disable=W0702
                log.exception("Exception in reaper thread, continuing")

    def _reap_zombies(self):
        exited_pids = []
        known_pids = set()
        #
        # Collect stopped processes
        #
        while True:
            try:
                child_siginfo = os.waitid(  # pylint: disable=E1101
                    os.P_ALL, os.getpid(), os.WEXITED | os.WNOHANG | os.WNOWAIT  # pylint: disable=E1101
                )
                #
                if child_siginfo is None:
                    break
                #
                child_pid = child_siginfo.si_pid
                #
                if child_pid in known_pids:
                    break
                #
                known_pids.add(child_pid)
                #
                if child_pid in self.external_pids:
                    continue
                #
                exited_pids.append(child_pid)
            except:  # pylint: disable=W0702
                break
        #
        # Process collected PIDs
        #
        while exited_pids:
            child_pid = exited_pids.pop(0)
            #
            try:
                child_siginfo = os.waitid(  # pylint: disable=E1101
                    os.P_PID, child_pid, os.WEXITED | os.WNOHANG  # pylint: disable=E1101
                )
                #
                if child_siginfo is None:
                    continue
                #
                log.info(
                    "Reaped child process: %s -> %s -> %s",
                    child_siginfo.si_pid,
                    child_siginfo.si_code,
                    child_siginfo.si_status,
                )
            except:  # pylint: disable=W0702
                continue
