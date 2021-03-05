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

# Next: callback order metadata?

""" Core template slots """

import functools

from pylon.core.tools import log


class SlotManager:
    """ Simple template slot manager """

    def __init__(self, context):
        self.context = context
        self.callbacks = dict()
        #
        self.context.event_manager.register_listener(
            "register_slot_callback", self._on_register_slot_callback
        )
        self.context.event_manager.register_listener(
            "unregister_slot_callback", self._on_unregister_slot_callback
        )

    def register_callback(self, slot, callback):
        """ Register slot callback """
        #
        name_path = list()
        name_path.append(self.context.node_name)
        name_path.append(callback.__module__)
        name_path.append(callback.__class__.__name__)
        name_path.append(callback.__name__)
        #
        callback_name = "_".join(name_path).replace(".", "_")
        self.context.rpc_manager.register_function(
            functools.partial(callback, self.context), callback_name
        )
        #
        self.context.event_manager.fire_event(
            "register_slot_callback",
            {
                "slot": slot,
                "callback": callback_name,
            }
        )
        #
        # if slot not in self.callbacks:
        #     self.callbacks[slot] = list()
        # if callback not in self.callbacks[slot]:
        #     self.callbacks[slot].append(callback)

    def unregister_callback(self, slot, callback):
        """ Unregister slot callback """
        #
        # if slot not in self.callbacks:
        #     return
        # if callback not in self.callbacks[slot]:
        #     return
        # self.callbacks[slot].remove(callback)

    def run_slot(self, slot, payload=None):
        """ Run callbacks for slot """
        result = list()
        if slot not in self.callbacks:
            return ""
        for callback in self.callbacks[slot]:
            try:
                callback_func = getattr(self.context.rpc_manager.call, callback)
                callback_result = callback_func(slot, payload)
                if callback_result is not None:
                    result.append(callback_result)
            except:  # pylint: disable=W0702
                log.exception("Template slot callback exception")
        return "\n".join(result)

    def _on_register_slot_callback(self, context, event_name, event_payload):
        _ = context, event_name
        #
        for key in ["slot", "callback"]:
            if key not in event_payload:
                log.error("Invalid slot registration data, skipping")
                return
        #
        log.debug("New slot callback: %s - %s", event_payload["slot"], event_payload["callback"])
        #
        if event_payload["slot"] not in self.callbacks:
            self.callbacks[event_payload["slot"]] = list()
        if event_payload["callback"] not in self.callbacks[event_payload["slot"]]:
            self.callbacks[event_payload["slot"]].append(event_payload["callback"])

    def _on_unregister_slot_callback(self, context, event_name, event_payload):
        _ = context, event_name
        #
        for key in ["slot", "callback"]:
            if key not in event_payload:
                log.error("Invalid slot unregistration data, skipping")
                return
        #
        if event_payload["slot"] not in self.callbacks:
            return
        if event_payload["callback"] not in self.callbacks[event_payload["slot"]]:
            return
        self.callbacks[event_payload["slot"]].remove(event_payload["callback"])


def template_slot_processor(context):
    """ Template slot support """
    _context = context
    #
    def _template_slot_processor():
        return {"template_slot": template_slot(_context)}
    #
    return _template_slot_processor


def template_slot(context):
    """ Template slot callback """
    _context = context
    #
    def _template_slot(slot, payload=None):
        return _context.slot_manager.run_slot(slot, payload)
    #
    return _template_slot
