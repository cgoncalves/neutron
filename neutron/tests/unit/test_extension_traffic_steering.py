# Copyright (c) 2014 OpenStack Foundation.
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

import copy

import mock
from webob import exc

from neutron.extensions import traffic_steering as ts
from neutron.openstack.common import uuidutils
from neutron.plugins.common import constants

from neutron.tests.unit import test_api_v2
from neutron.tests.unit import test_api_v2_extension


_uuid = uuidutils.generate_uuid
_get_path = test_api_v2._get_path


class TrafficSteeringExtensionTestCase(test_api_v2_extension.ExtensionTestCase
                                       ):

    def setUp(self):
        super(TrafficSteeringExtensionTestCase, self).setUp()
        self._setUpExtension(
            'neutron.extensions.trafficsteering.TrafficSteeringPluginBase',
            constants.TRAFFIC_STEERING, ts.RESOURCE_ATTRIBUTE_MAP,
            ts.TrafficSteering, 'ts')

    def test_create_classifier(self):
        classifier_id = _uuid()
        data = {'classifier': {'name': 'classf1',
                               'tenant_id': _uuid(),
                               'description': '',
                               'type': 'unicast',
                               'protocol': 6,
                               'port_range': '8000:900',
                               'src_ip': '1.1.1.1',
                               'dst_ip': '2.2.2.2'}}
        return_value = copy.copy(data['classifier'])
        return_value.update({'id': classifier_id})

        instance = self.plugin.return_value
        instance.create_classifier.return_value = return_value
        res = self.api.post(_get_path('ts/classifiers', fmt=self.fmt),
                            self.serialize(data),
                            content_type='application/%s' % self.fmt)
        instance.create_classifier.assert_called_with(mock.ANY,
                                                      classifier=data)
        self.assertEqual(res.status_int, exc.HTTPCreated.code)
        res = self.deserialize(res)
        self.assertIn('classifier', res)
        self.assertEqual(res['classifier'], return_value)

    def test_list_classifiers(self):
        classifier_id = _uuid()
        return_value = [{'tenant_id': _uuid(),
                         'id': classifier_id}]
        instance = self.plugin.return_value
        instance.get_classifiers.return_value = return_value

        res = self.api.get(_get_path('ts/classifiers', fmt=self.fmt))

        instance.get_classifiers.assert_called_with(mock.ANY,
                                                    fields=mock.ANY,
                                                    filters=mock.ANY)
        self.assertEqual(res.status_int, exc.HTTPOk.code)

    def test_get_classifier(self):
        classifier_id = _uuid()
        return_value = {'tenant_id': _uuid(),
                        'id': classifier_id}

        instance = self.plugin.return_value
        instance.get_classifier.return_value = return_value

        res = self.api.get(_get_path('ts/classifiers', id=classifier_id,
                                     fmt=self.fmt))

        instance.get_classifier.assert_called_with(mock.ANY, classifier_id,
                                                   fields=mock.ANY)
        self.assertEqual(res.status_int, exc.HTTPOk.code)
        res = self.deserialize(res)
        self.assertIn('classifier', res)
        self.assertEqual(res['classifier'], return_value)

    def test_update_classifier(self):
        classifier_id = _uuid()
        update_data = {'classifier': {'name': 'new_name'}}
        return_value = {'tenant_id': _uuid(),
                        'id': classifier_id}

        instance = self.plugin.return_value
        instance.update_classifier.return_value = return_value

        res = self.api.put(_get_path('ts/classifiers', id=classifier_id,
                                     fmt=self.fmt),
                           self.serialize(update_data))

        instance.get_classifier.assert_called_with(mock.ANY, classifier_id,
                                                   fields=mock.ANY)
        self.assertEqual(res.status_int, exc.HTTPOk.code)
        res = self.deserialize(res)
        self.assertIn('classifier', res)
        self.assertEqual(res['classifier'], return_value)

    def test_delete_classifier(self):
        self._test_entity_delete('classifier')

    def test_create_port_chain(self):
        pc_id = _uuid()
        chain_list = [[_uuid(), _uuid()], [_uuid(), _uuid(), _uuid()]]
        data = {'port_chain': {'name': 'chain1',
                               'tenant_id': _uuid(),
                               'description': '',
                               'ports': chain_list}}
        return_value = copy.copy(data['port_chain'])
        return_value.update({'id': pc_id})

        instance = self.plugin.return_value
        instance.create_port_chain.return_value = return_value
        res = self.api.post(_get_path('ts/port_chains', fmt=self.fmt),
                            self.serialize(data),
                            content_type='application/%s' % self.fmt)
        instance.create_port_chain.assert_called_with(mock.ANY,
                                                      port_chain=data)
        self.assertEqual(res.status_int, exc.HTTPCreated.code)
        res = self.deserialize(res)
        self.assertIn('port_chain', res)
        self.assertEqual(res['port_chain'], return_value)

    def test_list_port_chains(self):
        pc_id = _uuid()
        return_value = [{'tenant_id': _uuid(),
                         'id': pc_id}]
        instance = self.plugin.return_value
        instance.get_port_chains.return_value = return_value

        res = self.api.get(_get_path('ts/port_chains', fmt=self.fmt))

        instance.get_port_chains.assert_called_with(mock.ANY,
                                                    fields=mock.ANY,
                                                    filters=mock.ANY)
        self.assertEqual(res.status_int, exc.HTTPOk.code)

    def test_get_port_chain(self):
        pc_id = _uuid()
        return_value = {'tenant_id': _uuid(),
                        'id': pc_id}

        instance = self.plugin.return_value
        instance.get_port_chain.return_value = return_value

        res = self.api.get(_get_path('ts/port_chains', id=pc_id,
                                     fmt=self.fmt))

        instance.get_port_chain.assert_called_with(mock.ANY, pc_id,
                                                   fields=mock.ANY)
        self.assertEqual(res.status_int, exc.HTTPOk.code)
        res = self.deserialize(res)
        self.assertIn('port_chain', res)
        self.assertEqual(res['port_chain'], return_value)

    def test_update_port_chain(self):
        pc_id = _uuid()
        update_data = {'port_chain': {'name': 'new_name'}}
        return_value = {'tenant_id': _uuid(),
                        'id': pc_id}

        instance = self.plugin.return_value
        instance.update_port_chain.return_value = return_value

        res = self.api.put(_get_path('ts/port_chains', id=pc_id,
                                     fmt=self.fmt),
                           self.serialize(update_data))

        instance.get_port_chain.assert_called_with(mock.ANY, pc_id,
                                                   fields=mock.ANY)
        self.assertEqual(res.status_int, exc.HTTPOk.code)
        res = self.deserialize(res)
        self.assertIn('port_chain', res)
        self.assertEqual(res['port_chain'], return_value)

    def test_delete_port_chain(self):
        self._test_entity_delete('port_chain')
