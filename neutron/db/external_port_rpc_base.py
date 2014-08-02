# Copyright (c) 2014 Igor Duarte Cardoso.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from oslo.config import cfg

from neutron.api.v2 import attributes
from neutron.common import constants
from neutron.common import exceptions as n_exc
from neutron.common import utils
from neutron.common import topics
from neutron import context as neutron_context
from neutron.extensions import portbindings
from neutron import manager
from neutron.openstack.common.db import exception as db_exc
from neutron.openstack.common import log as logging
from neutron.openstack.common import excutils
from neutron.plugins.common import constants as p_const
from neutron.plugins.openvswitch.common import constants as ovs_const

from neutron.agent.external.drivers.external_driver import ExternalDriver

LOG = logging.getLogger(__name__)

# This mixin is not in use anymore, but its functionality
# is useful for future agent requests.
class ExternalPortServerRpcCallbackMixin(object):
    """A mix-in that enable External (port) agent
    support in plugin implementations."""

    def _get_attachment_points(self, context, **kwargs):
        """Retrieve and return a list of all attachment points."""
        host = kwargs.get('host')
        ids = kwargs.get('attachment_point_ids') # TODO
        plugin = manager.NeutronManager.get_plugin()
        filters = dict(admin_state_up=[True])
        attachment_points = plugin.get_attachment_points(context, filters=filters)
        return attachment_points

    def _get_external_ports(self, context, **kwargs):
        """Retrieve and return a list of all external ports."""
        host = kwargs.get('host')
        ids = kwargs.get('external_port_ids') # TODO
        plugin = manager.NeutronManager.get_plugin()
        filters = dict(admin_state_up=[True])
        external_ports = plugin.get_external_ports(context, filters=filters)
        return external_ports

    def _get_attachment_point(self, context, **kwargs):
        """Retrieve and return the attachment point with this ID."""
        host = kwargs.get('host')
        id = kwargs.get('attachment_point_id')
        plugin = manager.NeutronManager.get_plugin()
        filters = dict(admin_state_up=[True])
        attachment_point = plugin.get_attachment_point(context, id)
        return attachment_point

    def get_attachment_points(self, context, **kwargs):
        """Retrieve and return a list of all attachment points."""
        host = kwargs.get('host')
        attachment_points = self._get_attachment_points(context, **kwargs)
        return attachment_points

    def get_external_ports(self, context, **kwargs):
        """Retrieve and return a list of all external ports."""
        host = kwargs.get('host')
        external_ports = self._get_external_ports(context, **kwargs)
        return external_ports

    def get_attachment_point(self, context, **kwargs):
        """Retrieve and return the attachment point with this ID."""
        host = kwargs.get('host')
        attachment_point = self._get_attachment_point(context, **kwargs)
        LOG.debug(_('IGOR|get_attachment_point requested, contents = %s'), attachment_point)
        return attachment_point

    def get_external_network_id(self, context, **kwargs):
        """Get one external network id for the External agent.

        External agent expects only on external network when it performs
        this query.
        """
        context = neutron_context.get_admin_context()
        plugin = manager.NeutronManager.get_plugin()
        net_id = plugin.get_external_network_id(context)
        LOG.debug(_("External network ID returned to External agent: %s"),
                  net_id)
        return net_id

# This mixin is applied to the OVSNeutronAgent and RpcCallbacks from ML2.
class ExternalPortAgentRpcCallbackMixin(object):
    """Turns the Neutron Open vSwitch agent aware of operations related
    to the "external ports" extension, like attaching and detaching
    attachment points. It makes use of provided indices
    to assign GRE keys in a == fashion."""
    # TODO: This is OVS-specific, should be encapsulated in the mechanism driver.

    def attachment_point_attach(self, context, **kwargs):
        ap = kwargs.get('ap')
        index = kwargs.get('index')
        network_id = ap['network_id']
        remote_ip = ap['ip_address']
        LOG.error(_('local_vlan_map=%s'), self.local_vlan_map)
        # TODO: some kind of atomicity guarantee against the next 2 statements?
        if network_id not in self.local_vlan_map:
            self.provision_local_vlan(network_id, 'local', '', '')

        # TODO: detect net params and assign during provisioning
        vlan_tag = self.local_vlan_map.get(network_id).vlan
        gre_key = index
        self.int_br.add_explicit_tunnel_port("ap-"+ap['id'][:4], remote_ip,
                                             self.local_ip, p_const.TYPE_GRE,
                                             vlan_tag, gre_key)

    def attachment_point_detach(self, context, **kwargs):
        ap = kwargs.get('ap')
        self.int_br.delete_port("ap-"+ap['id'][:4])
        
# This mixin is applied to the ExternalAgent.
class EPExternalAgentRpcCallbackMixin(object):
    """ Provides the methods that makes the External Agent
    capable of attaching and detaching attachment points, as
    well as other functionality regarding these."""

    def attachment_point_attach(self, context, **kwargs):
        ap = kwargs.get('ap')
        index = kwargs.get('index')
        driver_cls = ExternalDriver.get_driver(ap['driver'])
        LOG.debug(_("Sending attach() request to driver %s..."),
                  driver_cls.driver_name())
        driver = driver_cls(self.public_ip,
                      ap['ip_address'],
                      ap['identifier'],
                      ap['technology'],
                      index)
        driver.attach()

    def attachment_point_detach(self, context, **kwargs):
        ap = kwargs.get('ap')
        index = kwargs.get('index')
        driver_cls = ExternalDriver.get_driver(ap['driver'])
        LOG.debug(_("Sending detach() request to driver %s..."),
                  driver_cls.driver_name())
        driver = driver_cls(self.public_ip,
                      ap['ip_address'],
                      ap['identifier'],
                      ap['technology'],
                      index)
        driver.detach()


# This mixin is applied to the AgentNotifierApi.
class ExternalPortAgentRpcApiMixin(object):
    """Provides the methods that make the agent notifier
    capable of sending new kinds of notifications related
    to the "external ports" extension."""

    def attachment_point_attach(self, context, ap, index):
        topic = topics.get_topic_name(self.topic,
                                     topics.ATTACHMENT_POINT,
                                     topics.ATTACH)
        self.fanout_cast(context,
                         self.make_msg('attachment_point_attach', ap=ap, index=index),
                         topic=topic)

    def attachment_point_detach(self, context, ap, index):
        topic = topics.get_topic_name(self.topic,
                                     topics.ATTACHMENT_POINT,
                                     topics.DETACH)
        self.fanout_cast(context,
                         self.make_msg('attachment_point_detach', ap=ap, index=index),
                         topic=topic)
