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

""" Core template slots """

from core.tools import log


class SlotManager:
    """ Simple template slot manager """

    def __init__(self, context):
        self.context = context
        self.callbacks = dict()

    def register_callback(self, slot, callback):
        """ Register slot callback """
        if slot not in self.callbacks:
            self.callbacks[slot] = list()
        if callback not in self.callbacks[slot]:
            self.callbacks[slot].append(callback)

    def unregister_callback(self, slot, callback):
        """ Unregister slot callback """
        if slot not in self.callbacks:
            return
        if callback not in self.callbacks[slot]:
            return
        self.callbacks[slot].remove(callback)

    def run_slot(self, slot, payload=None):
        """ Run callbacks for slot """
        result = list()
        if slot not in self.callbacks:
            return ""
        for callback in self.callbacks[slot]:
            try:
                callback_result = callback(self.context, slot, payload)
                if callback_result is not None:
                    result.append(callback_result)
            except:  # pylint: disable=W0702
                log.exception("Template slot callback exception")
        return "\n".join(result)


def template_slot_processor(context):
    """ Template slot support """
    _context = context
    #
    def _template_slot_processor():
        return {"template_slot": template_slot(_context)}
    #
    return _template_slot_processor


def template_slot(context):
    """ template slot callback """
    _context = context
    #
    def _template_slot(slot, payload=None):
        return _context.slot_manager.run_slot(slot, payload)
    #
    return _template_slot
