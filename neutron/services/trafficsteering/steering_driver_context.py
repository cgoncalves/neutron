# Copyright 2014, OpenStack Foundation.
# All rights reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.


from neutron.services.trafficsteering import steering_driver_api as api


class TrafficSteeringContext(object):
    """TrafficSteering context base class."""
    def __init__(self, plugin, plugin_context):
        self._plugin = plugin
        self._plugin_context = plugin_context


class PortChainContext(TrafficSteeringContext, api.PortChainContext):

    def __init__(self, plugin, plugin_context, portchain,
                 original_portchain=None):
        super(PortChainContext, self).__init__(plugin, plugin_context)
        self._portchain = portchain
        self._original_portchain = original_portchain

    @property
    def current(self):
        return self._portchain

    @property
    def original(self):
        return self._original_portchain


class SteeringClassifierContext(TrafficSteeringContext, api.SteeringClassifierContext):

    def __init__(self, plugin, plugin_context, steering_classifier,
                 original_steering_classifier=None):
        super(SteeringClassifierContext, self).__init__(plugin, plugin_context)
        self._steering_classifier = steering_classifier
        self._original_steering_classifier = original_steering_classifier

    @property
    def current(self):
        return self._steering_classifier

    @property
    def original(self):
        return self._original_steering_classifier
