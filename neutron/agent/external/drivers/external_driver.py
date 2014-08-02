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

from neutron.openstack.common import log as logging
LOG = logging.getLogger(__name__)

class ExternalDriver(object):
    """Base class for External drivers,
    automating configuration on attachment points."""

    @classmethod
    def driver_name(cls):
        return '_base'

    @classmethod
    def _get_drivers(cls):
        drivers = ExternalDriver.__subclasses__()
        return drivers 

    @classmethod
    def get_driver(cls, name):
        """Returns a class object representing the desired driver."""
        drivers = cls._get_drivers()
        for driver in drivers:
            if driver.driver_name() == name:
                return driver

    def __init__(self, os_ip_addr, ap_ip_addr, identifier, technology, index):
        pass

    def _log(self, ftext, *params):
        """Logs either to neutron.openstack.common.log or
        by a normal print(), so it can be debugged without OpenStack."""
        print(params)
        try:
            LOG.debug(_(ftext), *params)
        except NameError:
            print("LOG: " + ftext % params)

    def attach(self):
        """Calling this method will ensure the remote device
        will be properly configured to become an attachment
        point for a Neutron network"""
        pass

    def detach(self):
        """Calling this method will ensure that a previous call
        to attach() will be properly and totally reverted at
        the remote device (being an active attachment point)."""
        pass
