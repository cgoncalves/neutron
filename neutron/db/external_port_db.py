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
# Per the latest architecture, most of this file should be decoupled from ML2
# and instead placed under /neutron/db/.
# See also: https://review.openstack.org/#/c/97173/

import sqlalchemy as sa

from neutron.api.v2 import attributes
from neutron.common import exceptions as exc
from neutron.db import db_base_plugin_v2
from neutron.db import model_base
from neutron.db import models_v2
from neutron.extensions import portbindings
from neutron.extensions import external_port
from neutron.openstack.common import log as logging
from neutron.openstack.common import uuidutils
from neutron.common import constants

LOG = logging.getLogger(__name__)

# TODO: "status" field of attachment points should reflect the actual
# attachment point status, by interfacing with the
# external agent (as there may be an error, e.g.).
class Attachment_point(model_base.BASEV2, models_v2.HasId, models_v2.HasTenant):
    name = sa.Column(sa.String(36))
    description = sa.Column(sa.String(1024))
    admin_state_up = sa.Column(sa.Boolean(), nullable=False)
    status = sa.Column(sa.String(16), nullable=False)
    error = sa.Column(sa.String(255))
    ip_address = sa.Column(sa.String(50), nullable=False) # TODO: IPv6 support?
    driver = sa.Column(sa.String(36), nullable=False)
    identifier = sa.Column(sa.String(255), nullable=False)
    technology = sa.Column(sa.String(255), nullable=False)
    index = sa.Column(sa.Integer(), nullable=False,
                      primary_key=True, autoincrement=True)
    network_id = sa.Column(sa.String(36), sa.ForeignKey('networks.id'))

class External_port(model_base.BASEV2, models_v2.HasId, models_v2.HasTenant):
    name = sa.Column(sa.String(36))
    description = sa.Column(sa.String(1024))
    admin_state_up = sa.Column(sa.Boolean(), nullable=False)
    status = sa.Column(sa.String(16), nullable=False)
    error = sa.Column(sa.String(255))
    mac_address = sa.Column(sa.String(20), nullable=False)
    attachment_point_id = sa.Column(sa.String(36),
                                    sa.ForeignKey('attachment_points.id'),
                                    nullable=False)
    port_id = sa.Column(sa.String(36), sa.ForeignKey('ports.id'))


class ExternalPortMixin(external_port.ExternalPortPluginBase,
                        db_base_plugin_v2.CommonDbMixin):

    def create_attachment_point(self, context, attachment_point):
        ap = attachment_point['attachment_point']
        
        if not ap['ip_address']:
            err_msg = _('An IP address for the attachment point admin host must be provided')
            raise exc.InvalidInput(error_message=err_msg)

        if not ap['driver']:
            err_msg = _('A driver name must be provided')
            raise exc.InvalidInput(error_message=err_msg)

        if not ap['identifier']:
            err_msg = _('The identifier for the attachment point must be provided')
            raise exc.InvalidInput(error_message=err_msg)
        
        if not ap['technology']:
            err_msg = _('The technology of the attachment point must be provided')
            raise exc.InvalidInput(error_message=err_msg)

        ap['id'] = uuidutils.generate_uuid()
        ap['tenant_id'] = self._get_tenant_id_for_create(context, ap)
        
        with context.session.begin(subtransactions=True):
            ap_db = Attachment_point(id = ap['id'],
                                    name = ap['name'],
                                    description = ap['description'],
                                    admin_state_up = ap['admin_state_up'],
                                    ip_address = ap['ip_address'],
                                    status = constants.STATUS_BUILD,
                                    tenant_id = ap['tenant_id'],
                                    network_id = None,
                                    driver = ap['driver'],
                                    identifier = ap['identifier'],
                                    technology = ap['technology'])
            context.session.add(ap_db)
            
        ap_obj = self._make_attachment_point_dict(ap_db)
        return ap_obj

    def get_attachment_point(self, context, id, fields=None):
        ap_db = self._get_attachment_point(context, id)
        return self._make_attachment_point_dict(ap_db, fields)

    def get_attachment_points(self, context, filters=None, fields=None):
        return self._get_collection(context, Attachment_point,
                                    self._make_attachment_point_dict,
                                    filters=filters, fields=fields)

    def update_attachment_point(self, context, id, attachment_point):
        ap = attachment_point['attachment_point']
        ap_db = self._get_attachment_point(context, id)

        tenant_set = 'tenant_id' in ap
        network_set = 'network_id' in ap

        # Check if changing ownership only (not attachment)
        if tenant_set and not network_set:
            self._check_tenant_update(context, ap, ap_db)

        if network_set:
            # Process an attachment/detachment
            self._process_attachment_network(context, ap, ap_db)

        with context.session.begin(subtransactions=True):
            ap_db.update(ap)

        index = ap_db['index']
        LOG.error(_("Index of AP is: %s"), index)

        if network_set:
            if ap['network_id']:
                self.notifier.attachment_point_attach(context, ap_db, index)
            else:
                self.notifier.attachment_point_detach(context, ap_db, index)

        return self._make_attachment_point_dict(ap_db)

    def delete_attachment_point(self, context, id):
        ap_db = self._get_attachment_point(context, id)
        with context.session.begin(subtransactions=True):
            context.session.delete(ap_db)

    def create_external_port(self, context, external_port):
        eport = external_port['external_port']

        if not eport['mac_address']:
            err_msg = _('The MAC address cannot be empty')

        if network_set:
            if ap['network_id']:
                self.notifier.attachment_point_attach(context, ap_db)
            else:
                self.notifier.attachment_point_detach(context, ap_db)

        return self._make_attachment_point_dict(ap_db)

    def delete_attachment_point(self, context, id):
        ap_db = self._get_attachment_point(context, id)
        with context.session.begin(subtransactions=True):
            context.session.delete(ap_db)

    def create_external_port(self, context, external_port):
        eport = external_port['external_port']

        if not eport['mac_address']:
            err_msg = _('The MAC address cannot be empty')
            raise exc.InvalidInput(error_message=err_msg)

        if not eport['attachment_point_id']:
            err_msg = _('The attachment point ID cannot be empty')
            raise exc.InvalidInput(error_message=err_msg)

        eport_id = uuidutils.generate_uuid()
        eport['tenant_id'] = self._get_tenant_id_for_create(context, eport)

        with context.session.begin(subtransactions=True):
            eport_db = External_port(id = eport_id,
                                    name = eport['name'],
                                    description = eport['description'],
                                    admin_state_up = eport['admin_state_up'],
                                    status = constants.STATUS_BUILD,
                                    tenant_id = eport['tenant_id'],
                                    mac_address = eport['mac_address'],
                                    attachment_point_id = eport['attachment_point_id'],
                                    port_id = None)
            context.session.add(eport_db)

        return self._make_external_port_dict(eport_db)

    def get_external_port(self, context, id, fields=None):
        eport_db = self._get_external_port(context, id)
        return self._make_external_port_dict(eport_db, fields)

    def get_external_ports(self, context, filters=None, fields=None):
        return self._get_collection(context, External_port,
                                    self._make_external_port_dict,
                                    filters=filters, fields=fields)

    def update_external_port(self, context, id, external_port):

        eport = external_port['external_port']
        eport_db = self._get_external_port(context, id)

        tenant_set = 'tenant_id' in eport
        port_set = 'port_id' in eport

        # Check if changing ownership only (not attachment)
        if tenant_set and not port_set:
            self._check_tenant_update(context, eport, eport_db)

        if port_set:
            # Process an attachment/detachment
            self._process_attachment_port(context, eport, eport_db)

        port_db = self._process_attachment_port(context, eport, eport_db)
        eport['port_id'] = port_db['id']

        with context.session.begin(subtransactions=True):
            eport_db.update(eport)

        return self._make_external_port_dict(eport_db)

    def delete_external_port(self, context, id):
        eport_db = self._get_external_port(context, id)

        with context.session.begin(subtransactions=True):
            context.session.delete(eport_db)

    def _get_index_of_dict_in_list(self, dlist, attr, value):
        # TODO: check is the oslo lib has something like this already.
        return next(index for (index, d) in enumerate(dlist) if d[attr] == value)

    def _get_attachment_point(self, context, id):
        try:
            ap_db = self._get_by_id(context, Attachment_point, id)
        except exc.NoResultFound:
            raise external_port.AttachmentPointNotFound(ap_id=id)
        return ap_db

    def _get_external_port(self, context, id):
        try:
            eport_db = self._get_by_id(context, External_port, id)
        except exc.NoResultFound:
            raise external_port.ExternalPortNotFound(eport_id=id)
        return eport_db

    def _make_external_port_dict(self, external_port, fields=None):
        res = {'id': external_port['id'],
               'name': external_port['name'],
               'description': external_port['description'],
               'admin_state_up': external_port['admin_state_up'],
               'status': external_port['status'],
               'error': '',
               'mac_address': external_port['mac_address'],
               'attachment_point_id': external_port['attachment_point_id'],
               'port_id': external_port['port_id']}
        return self._fields(res, fields)
    
    def _make_attachment_point_dict(self, attachment_point, fields=None):
        res = {'id': attachment_point['id'],
               'name': attachment_point['name'],
               'description': attachment_point['description'],
               'admin_state_up': attachment_point['admin_state_up'],
               'status': attachment_point['status'],
               'error': '',
               'ip_address': attachment_point['ip_address'],
               'tenant_id': attachment_point['tenant_id'],
               'network_id': attachment_point['network_id'],
               'driver': attachment_point['driver'],
               'identifier': attachment_point['identifier'],
               'technology': attachment_point['technology'],
               'index': attachment_point['index']}
        return self._fields(res, fields)

    def _check_tenant_update(self, context, ap, ap_db):
        if ap['tenant_id'] == ap_db['tenant_id']:
            # Not changing anything: can proceed
            return

        try:
            self._get_network(context, network_id)
        except exc.NetworkNotFound:
            # Not attached: tenant can be updated
            return

        msg = _('Attachment point %s is attached to a network, cannot change ownership') % (
            ap_db['id'])
        raise exc.BadRequest(resource='attachment-point', msg=msg)

    def _process_attachment_network(self, context, ap, ap_db):
        network_id = ap['network_id']

        if not network_id:
            # Detaching ap: can proceed
            return

        if ap_db['network_id']:
            # Already attached
            msg = _('Attachment point %s is already attached to network %s') % (
                ap_db['id'], ap_db['network_id'])
            raise exc.BadRequest(resource='attachment-point', msg=msg)

        network_db = self._get_network(context, network_id)

        # Check if changing ownership also
        tenant_set = 'tenant_id' in ap
        tenant_id = ap['tenant_id'] if tenant_set else ap_db['tenant_id']

        if tenant_id != network_db['tenant_id']:
            msg = _('Attachment point %s cannot be attached to network %s'
                    ' belonging to a different tenant') % (
                    ap_db['id'], network_id)
            raise exc.BadRequest(resource='attachment-point', msg=msg)

    def _process_attachment_port(self, context, eport, eport_db):

        if eport_db['port_id']:
            # Already attached
            msg = _('External port %s is already attached to port %s') % (
                eport_db['id'], eport_db['port_id'])
            raise exc.BadRequest(resource='external-port', msg=msg)

        port_db = self._attach_ep_create_port(context, eport_db)
        return port_db

    def _attach_ep_create_port(self, context, eport):
        # TODO extend port instead of creating new resource external-port.
        ap_db = self._get_attachment_point(context, eport['attachment_point_id'])
        if ap_db['network_id']:
            port = {
                'name': 'port_'+eport['name'],
                'network_id': ap_db['network_id'],
                'device_id': eport['id'],
                'mac_address': eport['mac_address'],
                'device_owner': constants.DEVICE_OWNER_EXTERNAL_PORT,
                'fixed_ips': attributes.ATTR_NOT_SPECIFIED,
                'admin_state_up': True,
            }
            # TODO: OVS port bindings! DHCP and other services may malfunction.
            # E.g.: DHCP server won't start just by adding a port like this;
            # Also, each new external port is only visible
            # after subsequent DHCP server restart.
            port_db = self.create_port(context, {'port': port})
            return port_db

