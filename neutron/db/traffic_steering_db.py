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

import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy.orm import exc

from neutron.common import log
from neutron.db import api as db
from neutron.db import db_base_plugin_v2 as base_db
from neutron.db import model_base
from neutron.db import models_v2
from neutron.extensions import traffic_steering as ts
from neutron.openstack.common import jsonutils
from neutron.openstack.common import log as logging
from neutron.openstack.common import uuidutils


LOG = logging.getLogger(__name__)


class SteeringClassifier(model_base.BASEV2, models_v2.HasId, models_v2.HasTenant):
    """Represents a Steering Classifier resource."""
    __tablename__ = 'ts_steering_classifiers'
    name = sa.Column(sa.String(255))
    description = sa.Column(sa.String(1024))
    protocol = sa.Column(sa.Integer)
    source_port_range_min = sa.Column(sa.Integer)
    source_port_range_max = sa.Column(sa.Integer)
    destination_port_range_min = sa.Column(sa.Integer)
    destination_port_range_max = sa.Column(sa.Integer)
    source_ip_address = sa.Column(sa.String(46))
    destination_ip_address = sa.Column(sa.String(46))
    port_chains = orm.relationship('PortChainSteeringClassifierAssociation',
                                   cascade='all',
                                   backref='ts_steering_classifiers')


class PortChain(model_base.BASEV2, models_v2.HasId, models_v2.HasTenant):
    """Represents a Port Chain resource."""
    __tablename__ = 'ts_port_chains'
    name = sa.Column(sa.String(255))
    description = sa.Column(sa.String(1024))
    #ports = orm.relationship("PortChainPortAssociation", backref="port_chains")
    ports = sa.Column(sa.String(4096))
    steering_classifiers = orm.relationship('PortChainSteeringClassifierAssociation',
                                            cascade='all', lazy='joined',
                                            backref="ts_port_chain")


#class PortChainPortAssociation(model_base.BASEV2):
#    """Many to many relation between PortChains and Neutron Ports."""
#    __tablename__ = 'ts_port_chain_port_associations'
#    port_chain_id = sa.Column(sa.String(36),
#                              sa.ForeignKey('ts_port_chains.id'),
#                              primary_key=True)
#    neutron_port_id = sa.Column(sa.String(36),
#                                sa.ForeignKey('ports.id'),
#                                primary_key=True)


class PortChainSteeringClassifierAssociation(model_base.BASEV2):
    """Many to many relation between PortChains and SteeringClassifiers."""
    __tablename__ = 'ts_port_chain_classifier_associations'
    port_chain_id = sa.Column(sa.String(36),
                              sa.ForeignKey('ts_port_chains.id'),
                              primary_key=True)
    steering_classifier_id = sa.Column(sa.String(36),
                              sa.ForeignKey('ts_steering_classifiers.id'),
                              primary_key=True)


class TrafficSteeringDbMixin(ts.TrafficSteeringPluginBase,
                             base_db.CommonDbMixin):
    """Mixin class for Traffic Steering DB implementation."""

    __native_bulk_support = False
    __native_pagination_support = True
    __native_sorting_support = True

    def __init__(self, *args, **kwargs):
        db.configure_db()
        super(TrafficSteeringDbMixin, self).__init__(*args, **kwargs)

    def _get_port_chain(self, context, id):
        try:
            return self._get_by_id(context, PortChain, id)
        except exc.NoResultFound:
            raise ts.PortChainNotFound(port_chain_id=id)

    def _get_steering_classifier(self, context, id):
        try:
            return self._get_by_id(context, SteeringClassifier, id)
        except exc.NoResultFound:
            raise ts.SteeringClassifierNotFound(steering_classifier_id=id)

    def _get_min_max_ports_from_range(self, port_range):
        if not port_range:
            return [None, None]
        min_port, sep, max_port = port_range.partition(":")
        if not max_port:
            max_port = min_port
        return [int(min_port), int(max_port)]

    def _get_port_range_from_min_max_ports(self, min_port, max_port):
        if not min_port:
            return None
        if min_port == max_port:
            return str(min_port)
        else:
            return '%d:%d' % (min_port, max_port)

    def _set_classifiers_for_port_chain(self, context, pc_db, c_id_list):
      if not c_id_list:
          pc_db.steering_classifiers = []
          return
      with context.session.begin(subtransactions=True):
          filters = {'id': [c_id for c_id in c_id_list]}
          classifiers_in_db = self._get_collection_query(context,
                                                         SteeringClassifier,
                                                         filters=filters)
          classifiers_dict = dict((c_db['id'], c_db)
                                  for c_db in classifiers_in_db)
          for classifier_id in c_id_list:
              if classifier_id not in classifiers_dict:
                  raise ts.SteeringClassifierNotFound(steering_classifier_id=
                                                      classifier_id)
          pc_db.steering_classifiers = []
          for classifier_id in c_id_list:
              assoc = PortChainSteeringClassifierAssociation(port_chain_id=pc_db.id,
                                                             steering_classifier_id=classifier_id)
              pc_db.steering_classifiers.append(assoc)

    def _make_steering_classifier_dict(self, c, fields=None):
        src_port_range = self._get_port_range_from_min_max_ports(
            c['source_port_range_min'],
            c['source_port_range_max'])
        dst_port_range = self._get_port_range_from_min_max_ports(
            c['destination_port_range_min'],
            c['destination_port_range_max'])
        res = {'id': c['id'],
               'tenant_id': c['tenant_id'],
               'name': c['name'],
               'description': c['description'],
               'protocol': c['protocol'],
               'src_port_range': src_port_range,
               'dst_port_range': dst_port_range,
               'src_ip': c['source_ip_address'],
               'dst_ip': c['destination_ip_address']}
        return self._fields(res, fields)

    def _make_port_chain_dict(self, c, fields=None):
        res = {'id': c['id'],
               'tenant_id': c['tenant_id'],
               'name': c['name'],
               'description': c['description'],
               'ports': jsonutils.loads(c['ports']),
               }
        res['steering_classifiers'] = [sc['steering_classifier_id']
                                       for sc in c['steering_classifiers']]
        return self._fields(res, fields)

    @log.log
    def create_port_chain(self, context, port_chain):
        c = port_chain['port_chain']
        tenant_id = self._get_tenant_id_for_create(context, c)
        with context.session.begin(subtransactions=True):
            chain_db = PortChain(id=uuidutils.generate_uuid(),
                                 tenant_id=tenant_id,
                                 name=c['name'],
                                 description=c['description'],
                                 ports=jsonutils.dumps(c['ports']))
            self._set_classifiers_for_port_chain(context, chain_db,
                                                 c['steering_classifiers'])
            context.session.add(chain_db)
        return self._make_port_chain_dict(chain_db)

    @log.log
    def update_port_chain(self, context, id, port_chain):
        c = port_chain['port_chain']
        with context.session.begin(subtransactions=True):
            query = context.session.query(PortChain)
            chain_db = query.filter_by(id=id).first()
            chain_db.update(c)
        return self._make_port_chain_dict(chain_db)

    @log.log
    def delete_port_chain(self, context, id):
        with context.session.begin(subtransactions=True):
            c_db = context.session.query(PortChain).filter_by(id=id).first()
            context.session.delete(c_db)

    @log.log
    def get_port_chain(self, context, id, fields=None):
        c_db = self._get_port_chain(context, id)
        return self._make_port_chain_dict(c_db, fields)

    @log.log
    def get_port_chains(self, context, filters=None, fields=None):
        return self._get_collection(context, PortChain,
                                    self._make_port_chain_dict,
                                    filters=filters, fields=fields)

    @log.log
    def create_steering_classifier(self, context, steering_classifier):
        c = steering_classifier['steering_classifier']
        tenant_id = self._get_tenant_id_for_create(context, c)
        src_p_min, src_p_max = self._get_min_max_ports_from_range(c['src_port_range'])
        dst_p_min, dst_p_max = self._get_min_max_ports_from_range(c['dst_port_range'])
        with context.session.begin(subtransactions=True):
            c_db = SteeringClassifier(id=uuidutils.generate_uuid(),
                                      tenant_id=tenant_id,
                                      name=c['name'],
                                      description=c['description'],
                                      protocol=c['protocol'],
                                      source_port_range_min=src_p_min,
                                      source_port_range_max=src_p_max,
                                      destination_port_range_min=dst_p_min,
                                      destination_port_range_max=dst_p_max,
                                      source_ip_address=c['src_ip'],
                                      destination_ip_address=c['dst_ip'])
            context.session.add(c_db)
        return self._make_steering_classifier_dict(c_db)

    @log.log
    def update_steering_classifier(self, context, id, steering_classifier):
        c = steering_classifier['steering_classifier']
        with context.session.begin(subtransactions=True):
            query = context.session.query(SteeringClassifier)
            classifier_db = query.filter_by(id=id).first()
            classifier_db.update(c)
        return self._make_steering_classifier_dict(classifier_db)

    @log.log
    def delete_steering_classifier(self, context, id):
        with context.session.begin(subtransactions=True):
            query = context.session.query(SteeringClassifier)
            classifier_db = query.filter_by(id=id).first()
            context.session.delete(classifier_db)

    @log.log
    def get_steering_classifier(self, context, id, fields=None):
        classifier_db = self._get_steering_classifier(context, id)
        return self._make_steering_classifier_dict(classifier_db, fields)

    @log.log
    def get_steering_classifiers(self, context, filters=None, fields=None):
        return self._get_collection(context, SteeringClassifier,
                                    self._make_steering_classifier_dict,
                                    filters=filters, fields=fields)
