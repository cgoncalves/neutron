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

"""Exceptions used by Traffic Steering plugin and drivers."""

from neutron.common import exceptions


class SteeringDriverError(exceptions.NeutronException):
    """Steering driver call failed."""
    message = _("%(method)s failed.")


class NotFound(exceptions.NeutronException):
    pass


class PortChainNotFound(NotFound):
    message = _("Port chain %(port_chain_id)s could not be found")


class ClassifierNotFound(NotFound):
    message = _("Classifier %(classifier_id)s could not be found")