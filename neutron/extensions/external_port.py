# Copyright (c) 2014 Igor Duarte Cardoso.
# All Rights Reserved.
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
#
# @author: Igor Duarte Cardoso

from abc import ABCMeta
from abc import abstractmethod

from neutron.openstack.common import log as logging
from neutron.api import extensions
from neutron.api.v2 import attributes as attr
from neutron.api.v2 import base
from neutron.api.v2 import resource_helper
from neutron.common import exceptions as exc
from neutron import manager
from neutron.plugins.common import constants

LOG = logging.getLogger(__name__)

def enforce_driver_format(data):
    if len(data) < 1:
        msg = _("'%s' cannot be converted to boolean") % data
        raise n_exc.InvalidInput(error_message=msg)
    else:
        return data.lower()

RESOURCE_ATTRIBUTE_MAP = {
    'attachment_points': {
        'id': {
            'allow_post': False,
            'allow_put': False,
            'enforce_policy': True,
            'is_visible': True,
            'primary_key': True},
        'name': {
            'allow_post': True,
            'allow_put': True,
            'default': '',
            'enforce_policy': True,
            'is_visible': True,
            'validate': {'type:string': None}},
        'description': {
            'allow_post': True,
            'allow_put': True,
            'default': '',
            'enforce_policy': True,
            'is_visible': True,
            'validate': {'type:string': None}},
        'tenant_id': {
            'allow_post': True,
            'allow_put': True,
            'enforce_policy': True,
            'is_visible': True,
            'required_by_policy': True,
            'validate': {'type:string': None}},
        'ip_address': {
            'allow_post': True,
            'allow_put': True,
            'enforce_policy': True,
            'is_visible': True,
            'validate': {'type:ip_address': None}},
        'driver': {
            'allow_post': True,
            'allow_put': False,
            'enforce_policy': True,
            'is_visible': True,
            'required_by_policy': True,
            'validate': {'type:string': None}},
        'identifier': {
            'allow_post': True,
            'allow_put': True,
            'convert_to': enforce_driver_format,
            'enforce_policy': True,
            'is_visible': True,
            'required_by_policy': True,
            'validate': {'type:string': None}},
        'technology': {
            'allow_post': True,
            'allow_put': True,
            'enforce_policy': True,
            'is_visible': True,
            'required_by_policy': True,
            'validate': {'type:string': None}},
        'network_id': {
            'allow_post': True,
            'allow_put': True,
            'default': attr.ATTR_NOT_SPECIFIED,
            'enforce_policy': True,
            'is_visible': True,
            'validate': {'type:uuid_or_none': None}},
        'index': {
            'allow_post': False,
            'allow_put': False,
            'enforce_policy': True,
            'is_visible': True,
            'primary_key': True,
            'autoincrement': True,
            'validate': {'type:int': None}},
        'admin_state_up': {
            'allow_post': True,
            'allow_put': True,
            'convert_to': attr.convert_to_boolean,
            'default': True,
            'enforce_policy': True,
            'is_visible': True},
        'status': {
            'allow_post': False,
            'allow_put': False,
            'enforce_policy': True,
            'is_visible': True},
        'error': {
            'allow_post': False,
            'allow_put': False,
            'enforce_policy': True,
            'is_visible': True}
    },
    'external_ports': {
        'id': {
            'allow_post': False,
            'allow_put': False,
            'enforce_policy': True,
            'is_visible': True,
            'primary_key': True},
        'name': {
            'allow_post': True,
            'allow_put': True,
            'default': '',
            'enforce_policy': True,
            'is_visible': True,
            'validate': {'type:string': None}},
        'description': {
            'allow_post': True,
            'allow_put': True,
            'default': '',
            'enforce_policy': True,
            'is_visible': True,
            'validate': {'type:string': None}},
        'tenant_id': {
            'allow_post': True,
            'allow_put': True,
            'enforce_policy': True,
            'is_visible': True,
            'required_by_policy': True,
            'validate': {'type:string': None}},
        'mac_address': {
            'allow_post': True,
            'allow_put': True,
            'enforce_policy': True,
            'is_visible': True,
            'validate': {'type:mac_address': None}},
        'attachment_point_id': {
            'allow_post': True,
            'allow_put': True,
            'enforce_policy': True,
            'is_visible': True,
            'required_by_policy': True,
            'validate': {'type:uuid_or_none': None}},
        'port_id': {
            'allow_post': True,
            'allow_put': True,
            'default': attr.ATTR_NOT_SPECIFIED,
            'enforce_policy': True,
            'is_visible': True,
            'validate': {'type:uuid_or_none': None}},
        'admin_state_up': {
            'allow_post': True,
            'allow_put': True,
            'convert_to': attr.convert_to_boolean,
            'default': True,
            'enforce_policy': True,
            'is_visible': True},
        'status': {
            'allow_post': False,
            'allow_put': False,
            'enforce_policy': True,
            'is_visible': True},
        'error': {
            'allow_post': False,
            'allow_put': False,
            'enforce_policy': True,
            'is_visible': True}
    }
}

class External_port(extensions.ExtensionDescriptor):
    @classmethod
    def get_name(cls):
        return _("External Port")

    @classmethod
    def get_alias(cls):
        return "external-port"

    @classmethod
    def get_description(cls):
        return _("Extension to allow assigning external ports to neutron networks, in order to fetch external hosts and attach them to the network")

    @classmethod
    def get_namespace(cls):
        return "http://docs.openstack.org/ext/neutron/external-port/api/v2.0"

    @classmethod
    def get_updated(cls):
        return "2014-05-29T00:00:00-00:00"

    @classmethod
    def get_resources(cls):
        plural_mappings = resource_helper.build_plural_mappings({}, RESOURCE_ATTRIBUTE_MAP)
        attr.PLURALS.update(plural_mappings)
        resources = resource_helper.build_resource_info(plural_mappings, RESOURCE_ATTRIBUTE_MAP, constants.CORE)
        return resources

    def get_extended_resources(self, version):
        if version == "2.0":
            return RESOURCE_ATTRIBUTE_MAP
        else:
            return {}

    @classmethod
    def get_plugin_interface(cls):
        return ExternalPortPluginBase

    def update_attributes_map(self, attributes):
        super(External_port, self).update_attributes_map(
            attributes, extension_attrs_map=RESOURCE_ATTRIBUTE_MAP)


class ExternalPortPluginBase(extensions.PluginInterface):

    __metaclass__ = ABCMeta
    
    @abstractmethod
    def create_attachment_point(self, context, attachment_point):
        pass

    @abstractmethod
    def update_attachment_point(self, context, id, attachment_point):
        pass

    @abstractmethod
    def get_attachment_point(self, context, id, fields=None):
        pass

    @abstractmethod
    def get_attachment_points(self, context, filters=None, fields=None):
        pass

    @abstractmethod
    def delete_attachment_point(self, context, id):
        pass


    @abstractmethod
    def create_external_port(self, context, external_port):
        pass

    @abstractmethod
    def update_external_port(self, context, id, external_port):
        pass

    @abstractmethod
    def get_external_port(self, context, id, fields=None):
        pass

    @abstractmethod
    def get_external_ports(self, context, filters=None, fields=None):
        pass

    @abstractmethod
    def delete_external_port(self, context, id):
        pass

# Exceptions
class AttachmentPointNotFound(exc.NotFound):
    message = _('Attachment point %(ap_id)s could not be found')
class ExternalPortNotFound(exc.NotFound):
    message = _('External port %(eport_id)s could not be found')
