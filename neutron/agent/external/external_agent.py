# Copyrigh 2014 Igor Duarte Cardoso.  All rights reserved.
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

import eventlet
import netaddr
import time
from oslo.config import cfg

from neutron.agent.common import config
from neutron.agent.linux import external_process
from neutron.agent.linux import interface
from neutron.agent.linux import ip_lib
from neutron.agent.linux import ovs_lib
from neutron.agent import rpc as agent_rpc
from neutron.common import constants as constants
from neutron.common import topics
from neutron.common import utils as common_utils
from neutron import context
from neutron import manager
from neutron.openstack.common import excutils
from neutron.openstack.common import importutils
from neutron.openstack.common import lockutils
from neutron.openstack.common import log as logging
from neutron.openstack.common import loopingcall
from neutron.openstack.common import periodic_task
from neutron.openstack.common import processutils
from neutron.openstack.common.rpc import common as rpc_common
from neutron.openstack.common.rpc import proxy
from neutron.openstack.common.rpc import dispatcher 
from neutron.openstack.common import service
from neutron import service as neutron_service
from neutron.api.v2 import attributes
from neutron.db import external_port_rpc_base

LOG = logging.getLogger(__name__)

class ExternalPluginApi(proxy.RpcProxy):
    """Agent side of the External agent RPC API.

    API version history:
        1.0 - Initial version.
    """

    BASE_RPC_API_VERSION = '1.0'

    def __init__(self, topic, host):
        super(ExternalPluginApi, self).__init__(
            topic=topic, default_version=self.BASE_RPC_API_VERSION)
        self.host = host

    def get_attachment_points(self, context, attachment_point_ids=None):
        """Make an RPC to retrieve the list of all attachment points."""
        return self.call(context,
                         self.make_msg('get_attachment_points', host=self.host, attachment_point_ids=attachment_point_ids),
                         topic=self.topic)

    def get_attachment_point(self, context, attachment_point_id):
        """Make an RPC to retrieve a specific attachment point."""
        return self.call(context,
                         self.make_msg('get_attachment_point', host=self.host, attachment_point_id=attachment_point_id),
                         topic=self.topic)

    def get_external_ports(self, context, external_port_ids=None):
        """Make an RPC to retrieve the list of all external ports."""
        return self.call(context,
                         self.make_msg('get_external_ports', host=self.host, external_port_ids=external_port_ids),
                         topic=self.topic)

class ExternalInfo(object):

    def __init__(self, external_port_id, root_helper, external_port, attachment_point):
        self.external_port_id = external_port_id
        self.root_helper = root_helper
        self.external_port = external_port
        self.attachment_point = attachment_point

    @property
    def external_port(self):
        return self._external_port

    @external_port.setter
    def external_port(self, value):
        self._external_port = value
        if not self._external_port:
            return

class ExternalAgent(manager.Manager,
                    external_port_rpc_base.EPExternalAgentRpcCallbackMixin):
    """Manager for ExternalAgent

    API version history:
        1.0 initial Version
    """
    RPC_API_VERSION = '1.1'

    OPTS = [
        cfg.StrOpt('public_ip',
                   default='127.0.0.1',
                   help=_('Public IP address to access OpenStack')),
    ]

    def __init__(self, host, conf=None):
        if conf:
            self.conf = conf
        else:
            self.conf = cfg.CONF
        self.root_helper = config.get_root_helper(self.conf)
        self.external_infos = {}

        self._check_config_params()

        self.fullsync = True

        self.agent_state = {
            'binary': 'neutron-external-agent',
            'host': host,
            'topic': topics.EXTERNAL_AGENT,
            'start_flag': True,
            'agent_type': constants.AGENT_TYPE_EXTERNAL}

        self.setup_rpc(host)

        self.public_ip = self.conf.public_ip
        
        super(ExternalAgent, self).__init__()

    def setup_rpc(self, host):
        self.agent_id = '%s%s' % ('ext', (int(time.time())))
        self.topic = topics.AGENT
        self.plugin_rpc = ExternalPluginApi(topics.PLUGIN, host)
        self.state_rpc = agent_rpc.PluginReportStateAPI(topics.PLUGIN)

        # RPC network init
        self.context = context.get_admin_context_without_session()
        # Handle updates from service
        self.dispatcher = dispatcher.RpcDispatcher([self])
        # Define the listening consumers for the agent
        consumers = [[topics.ATTACHMENT_POINT, topics.ATTACH],
                     [topics.ATTACHMENT_POINT, topics.DETACH]]
        self.connection = agent_rpc.create_consumers(self.dispatcher,
                                                     self.topic,
                                                     consumers)

        report_interval = cfg.CONF.AGENT.report_interval
        self.use_call = True
        if report_interval:
            self.heartbeat = loopingcall.FixedIntervalLoopingCall(
                self._report_state)
            self.heartbeat.start(interval=report_interval)

    def _report_state(self):
            LOG.debug(_("External agent is reporting State..."))

    def agent_updated(self, context, payload):
        """Handle the agent_updated notification event."""
        self.fullsync = True
        LOG.info(_("agent_updated by server side %s!"), payload)

    def _check_config_params(self):
        """Check items in configuration files.

        Check for required and invalid configuration items.
        The actual values are not verified for correctness.
        """

    @lockutils.synchronized('external-agent', 'neutron-')
    def _rpc_loop(self):
        try:
            pass

        except Exception:
            self.fullsync = True

    def after_start(self):
        LOG.info(_("External agent started!"))

def register_options():
    conf = cfg.CONF
    conf.register_opts(ExternalAgent.OPTS)
    config.register_agent_state_opts_helper(conf)
    config.register_root_helper(conf)
    conf.register_opts(interface.OPTS)
    conf.register_opts(external_process.OPTS)

def main(manager='neutron.agent.external.external_agent.ExternalAgent'):
    eventlet.monkey_patch()
    register_options()
    cfg.CONF(project='neutron')
    config.setup_logging(cfg.CONF)
    server = neutron_service.Service.create(
        binary='neutron-external-agent',
        topic=topics.EXTERNAL_AGENT,
        report_interval=cfg.CONF.AGENT.report_interval,
        manager=manager)
    service.launch(server).wait()
