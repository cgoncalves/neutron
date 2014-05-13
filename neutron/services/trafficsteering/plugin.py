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

from neutron.common import log
from neutron.db import api as qdbapi
from neutron.db import traffic_steering_db
from neutron.openstack.common import excutils
from neutron.openstack.common import log as logging
from neutron.services.trafficsteering.common import exceptions as ts_exc
from neutron.services.trafficsteering import config  # noqa
from neutron.services.trafficsteering import steering_driver_context as s_ctx
from neutron.services.trafficsteering import steering_driver_manager as manager


LOG = logging.getLogger(__name__)


class TrafficSteeringPlugin(traffic_steering_db.TrafficSteeringDbMixin):

    """Implementation of the Traffic Steering Model Plugin."""
    supported_extension_aliases = ["traffic-steering"]

    def __init__(self):
        qdbapi.register_models()
        self.s_manager = manager.SteeringDriverManager()
        super(TrafficSteeringPlugin, self).__init__()
        self.s_manager.initialize()
        LOG.info(_("Traffic Steering Plugin initialization completed"))

    @log.log
    def create_port_chain(self, context, port_chain):
        session = context.session
        with session.begin(subtransactions=True):
            result = super(TrafficSteeringPlugin, self).create_port_chain(
                context, port_chain)
            steer_context = s_ctx.PortChainContext(self, context, result)
            self.s_manager.create_port_chain_precommit(steer_context)
        try:
            self.s_manager.create_port_chain_postcommit(steer_context)
        except ts_exc.SteeringDriverError:
            with excutils.save_and_reraise_exception():
                LOG.error(_("s_manager.create_port_chain_postcommit "
                            "failed, deleting port chain '%s'"), result['id'])
        return result

    @log.log
    def update_port_chain(self, context, id, port_chain):
        session = context.session
        with session.begin(subtransactions=True):
            original_port_chain = super(TrafficSteeringPlugin,
                                       self).get_port_chain(context, id)
            updated_port_chain = super(TrafficSteeringPlugin,
                                      self).update_port_chain(context, id,
                                                             port_chain)
            steering_context = s_ctx.PortChainContext(self, context,
                updated_port_chain, original_port_chain=original_port_chain)
            self.s_manager.update_port_chain_precommit(steering_context)

        self.s_manager.update_port_chain_postcommit(steering_context)
        return updated_port_chain

    @log.log
    def delete_port_chain(self, context, id):
        session = context.session
        with session.begin(subtransactions=True):
            port_chain = self.get_port_chain(context, id)
            steering_context = s_ctx.PortChainContext(self, context, port_chain)
            self.s_manager.delete_port_chain_precommit(steering_context)
            super(TrafficSteeringPlugin, self).delete_port_chain(context, id)

        try:
            self.s_manager.delete_port_chain_postcommit(steering_context)
        except ts_exc.SteeringDriverError:
            with excutils.save_and_reraise_exception():
                LOG.error(_("s_manager.delete_port_chain_postcommit "
                            "failed, deleting port chain '%s'"), id)

    @log.log
    def create_steering_classifier(self, context, steering_classifier):
        session = context.session
        with session.begin(subtransactions=True):
            result = super(TrafficSteeringPlugin, self).create_steering_classifier(
                context, steering_classifier)
            steer_context = s_ctx.SteeringClassifierContext(self, context, result)
            self.s_manager.create_steering_classifier_precommit(steer_context)
        try:
            self.s_manager.create_steering_classifier_postcommit(steer_context)
        except ts_exc.SteeringDriverError:
            with excutils.save_and_reraise_exception():
                LOG.error(_("s_manager.create_steering_classifier_postcommit "
                            "failed, deleting classifier '%s'"), result['id'])
        return result

    @log.log
    def update_steering_classifier(self, context, steering_classifier):
        session = context.session
        with session.begin(subtransactions=True):
            original_classifier = super(TrafficSteeringPlugin,
                                        self).get_classifier(context, id)
            updated_classifier = super(TrafficSteeringPlugin,
                                       self).update_steering_classifier(context, id,
                                                               steering_classifier)
            steering_context = s_ctx.SteeringClassifierContext(self, context,
                updated_classifier, original_classifier=original_classifier)
            self.s_manager.update_steering_classifier_precommit(steering_context)

        self.s_manager.update_steering_classifier_postcommit(steering_context)
        return updated_classifier

    @log.log
    def delete_steering_classifier(self, context, id):
        session = context.session
        with session.begin(subtransactions=True):
            classifier = self.get_steering_classifier(context, id)
            steering_context = s_ctx.SteeringClassifierContext(self, context,
                                                       classifier)
            self.s_manager.delete_steering_classifier_precommit(steering_context)
            super(TrafficSteeringPlugin, self).delete_steering_classifier(context, id)

        try:
            self.s_manager.delete_steering_classifier_postcommit(steering_context)
        except ts_exc.SteeringDriverError:
            with excutils.save_and_reraise_exception():
                LOG.error(_("s_manager.delete_steering_classifier_postcommit "
                            "failed, deleting classifier '%s'"), id)
