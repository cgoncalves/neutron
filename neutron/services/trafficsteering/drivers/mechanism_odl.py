# Copyright (c) 2014 OpenStack Foundation
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

import time

from oslo.config import cfg
import requests

from neutron.common import utils
from neutron.openstack.common import excutils
from neutron.openstack.common import jsonutils
from neutron.openstack.common import log
from neutron.services.trafficsteering.common import exceptions as n_exc
from neutron.services.trafficsteering import steering_driver_api as api

LOG = log.getLogger(__name__)

ODL_PORT_CHAINS = 'port_chains'
ODL_PORT_CHAIN = 'port_chain'
ODL_CLASSIFIERS = 'steering_classifiers'
ODL_CLASSIFIER = 'steering_classifier'

not_found_exception_map = {ODL_PORT_CHAINS: n_exc.PortChainNotFound,
                           ODL_CLASSIFIERS: n_exc.ClassifierNotFound}

odl_opts = [
    cfg.StrOpt('url',
               help=_("HTTP URL of OpenDaylight REST interface.")),
    cfg.StrOpt('username',
               help=_("HTTP username for authentication")),
    cfg.StrOpt('password', secret=True,
               help=_("HTTP password for authentication")),
    cfg.IntOpt('timeout', default=10,
               help=_("HTTP timeout in seconds.")),
    cfg.IntOpt('session_timeout', default=30,
               help=_("Tomcat session timeout in minutes.")),
]

cfg.CONF.register_opts(odl_opts, "ts_odl")


def try_del(d, keys):
    """Ignore key errors when deleting from a dictionary."""
    for key in keys:
        try:
            del d[key]
        except KeyError:
            pass


class JsessionId(requests.auth.AuthBase):

    """Attaches the JSESSIONID and JSESSIONIDSSO cookies to an HTTP Request.

    If the cookies are not available or when the session expires, a new
    set of cookies are obtained.
    """

    def __init__(self, url, username, password):
        """Initialization function for JsessionId."""

        # NOTE(kmestery) The 'limit' paramater is intended to limit how much
        # data is returned from ODL. This is not implemented in the Hydrogen
        # release of OpenDaylight, but will be implemented in the Helium
        # timeframe. Hydrogen will silently ignore this value.
        self.url = str(url) + '/' + ODL_CLASSIFIERS + '?limit=1'
        self.username = username
        self.password = password
        self.auth_cookies = None
        self.last_request = None
        self.expired = None
        self.session_timeout = cfg.CONF.ml2_odl.session_timeout * 60
        self.session_deadline = 0

    def obtain_auth_cookies(self):
        """Make a REST call to obtain cookies for ODL authenticiation."""

        r = requests.get(self.url, auth=(self.username, self.password))
        r.raise_for_status()
        jsessionid = r.cookies.get('JSESSIONID')
        jsessionidsso = r.cookies.get('JSESSIONIDSSO')
        if jsessionid and jsessionidsso:
            self.auth_cookies = dict(JSESSIONID=jsessionid,
                                     JSESSIONIDSSO=jsessionidsso)

    def __call__(self, r):
        """Verify timestamp for Tomcat session timeout."""

        if time.time() > self.session_deadline:
            self.obtain_auth_cookies()
        self.session_deadline = time.time() + self.session_timeout
        r.prepare_cookies(self.auth_cookies)
        return r


class OpenDaylightMechanismDriver(api.SteeringDriver):

    """Mechanism Driver for OpenDaylight."""
    auth = None
    out_of_sync = True

    def initialize(self):
        self.url = cfg.CONF.ts_odl.url
        self.timeout = cfg.CONF.ts_odl.timeout
        self.username = cfg.CONF.ts_odl.username
        self.password = cfg.CONF.ts_odl.password
        required_opts = ('url', 'username', 'password')
        for opt in required_opts:
            if not getattr(self, opt):
                raise cfg.RequiredOptError(opt, 'ts_odl')
        self.auth = JsessionId(self.url, self.username, self.password)

    # Postcommit hooks are used to trigger synchronization.

    def create_port_chain_postcommit(self, context):
        self.synchronize('create', ODL_PORT_CHAINS, context)

    def update_port_chain_postcommit(self, context):
        self.synchronize('update', ODL_PORT_CHAINS, context)

    def delete_port_chain_postcommit(self, context):
        self.synchronize('delete', ODL_PORT_CHAINS, context)

    def create_steering_classifier_postcommit(self, context):
        self.synchronize('create', ODL_CLASSIFIERS, context)

    def update_steering_classifier_postcommit(self, context):
        self.synchronize('update', ODL_CLASSIFIERS, context)

    def delete_steering_classifier_postcommit(self, context):
        self.synchronize('delete', ODL_CLASSIFIERS, context)

    def synchronize(self, operation, object_type, context):
        """Synchronize ODL with Neutron following a configuration change."""
        # FIXME(cgoncalves): following should be uncommented
        #if self.out_of_sync:
        #    self.sync_full(context)
        #else:
        self.sync_object(operation, object_type, context)

    def filter_create_port_chain_attributes(self, port_chain, context,
                                            dbcontext):
        """Filter out port_chain attributes not required for a create."""
        try_del(port_chain, ['status', 'subnets'])

    def filter_create_steering_classifier_attributes(self, classifier, context,
                                                     dbcontext):
        """Filter out classifier attributes not required for a create."""
        pass

    def sync_resources(self, resource_name, collection_name, resources,
                       context, dbcontext, attr_filter):
        """Sync objects from Neutron over to OpenDaylight.

        This will handle syncing port chains and classifiers from Neutron to
        OpenDaylight. It also filters out the requisite items which are not
        valid for create API operations.
        """
        to_be_synced = []
        for resource in resources:
            try:
                urlpath = collection_name + '/' + resource['id']
                self.sendjson('get', urlpath, None)
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 404:
                    attr_filter(resource, context, dbcontext)
                    to_be_synced.append(resource)

        key = resource_name if len(to_be_synced) == 1 else collection_name

        # 400 errors are returned if an object exists, which we ignore.
        self.sendjson('post', collection_name, {key: to_be_synced}, [400])

    @utils.synchronized('odl-sync-full')
    def sync_full(self, context):
        """Resync the entire database to ODL.

        Transition to the in-sync state on success.
        Note: we only allow a single thead in here at a time.
        """
        if not self.out_of_sync:
            return
        dbcontext = context._plugin_context
        port_chains = context._plugin.get_port_chains(dbcontext)
        classifiers = context._plugin.get_steering_classifiers(dbcontext)

        #self.sync_resources(ODL_PORT_CHAIN, ODL_PORT_CHAINS, port_chains,
        #                    context, dbcontext,
        #                    self.filter_create_port_chain_attributes)
        self.sync_resources(ODL_CLASSIFIER, ODL_CLASSIFIERS, classifiers,
                            context, dbcontext,
                            self.filter_create_steering_classifier_attributes)
        self.out_of_sync = False

    def filter_update_port_chain_attributes(self, port_chain, context,
                                            dbcontext):
        """Filter out port_chain attributes for an update operation."""
        try_del(port_chain, ['id', 'status', 'subnets', 'tenant_id'])

    def filter_update_steering_classifier_attributes(self, classifier, context,
                                                     dbcontext):
        """Filter out classifier attributes for an update operation."""
        try_del(classifier, ['id', 'network_id', 'ip_version', 'cidr',
                             'allocation_pools', 'tenant_id'])

    create_object_map = {ODL_PORT_CHAINS: filter_create_port_chain_attributes,
                         ODL_CLASSIFIERS: filter_create_steering_classifier_attributes}

    update_object_map = {ODL_PORT_CHAINS: filter_update_port_chain_attributes,
                         ODL_CLASSIFIERS: filter_update_steering_classifier_attributes}

    def sync_single_resource(self, operation, object_type, obj_id,
                             context, attr_filter_create, attr_filter_update):
        """Sync over a single resource from Neutron to OpenDaylight.

        Handle syncing a single operation over to OpenDaylight, and correctly
        filter attributes out which are not required for the requisite
        operation (create or update) being handled.
        """
        dbcontext = context._plugin_context
        if operation == 'create':
            urlpath = object_type
            method = 'post'
        else:
            urlpath = object_type + '/' + obj_id
            method = 'put'

        try:
            obj_getter = getattr(context._plugin, 'get_%s' % object_type[:-1])
            resource = obj_getter(dbcontext, obj_id)
        except not_found_exception_map[object_type]:
            LOG.debug(_('%(object_type)s not found (%(obj_id)s)'),
                      {'object_type': object_type.capitalize(),
                       'obj_id': obj_id})
        else:
            if operation == 'create':
                attr_filter_create(self, resource, context, dbcontext)
            elif operation == 'update':
                attr_filter_update(self, resource, context, dbcontext)
            try:
                # 400 errors are returned if an object exists, which we ignore.
                self.sendjson(method, urlpath, {object_type[:-1]: resource},
                              [400])
            except Exception:
                with excutils.save_and_reraise_exception():
                    self.out_of_sync = True

    def sync_object(self, operation, object_type, context):
        """Synchronize the single modified record to ODL."""
        obj_id = context.current['id']

        self.sync_single_resource(operation, object_type, obj_id, context,
                                  self.create_object_map[object_type],
                                  self.update_object_map[object_type])

    def sendjson(self, method, urlpath, obj, ignorecodes=[]):
        """Send json to the OpenDaylight controller."""

        headers = {'Content-Type': 'application/json'}
        data = jsonutils.dumps(obj, indent=2) if obj else None
        url = '/'.join([self.url, urlpath])
        LOG.debug(_('ODL-----> sending URL (%s) <-----ODL') % url)
        LOG.debug(_('ODL-----> sending JSON (%s) <-----ODL') % obj)
        LOG.debug(_('ODL-----> sending AUTH (%s) <-----ODL') % self.auth)
        r = requests.request(method, url=url,
                             headers=headers, data=data,
                             auth=self.auth, timeout=self.timeout)

        # ignorecodes contains a list of HTTP error codes to ignore.
        if r.status_code in ignorecodes:
            return
        r.raise_for_status()
