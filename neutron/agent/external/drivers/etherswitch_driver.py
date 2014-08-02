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

from time import sleep
import re
import telnetlib
import socket
import random

from neutron.openstack.common import log as logging
from neutron.agent.external.drivers.external_driver import ExternalDriver

LOG = logging.getLogger(__name__)

class EtherSwitchDriver(ExternalDriver):
    """Cisco EtherSwitch IOS External driver for automating
       configuration on attachment points.
       Currently communicates only through telnet."""

    @classmethod
    def driver_name(cls):
        return 'etherswitch'

    def __init__(self, os_ip_addr, ap_ip_addr, identifier, technology, index):
        super(ExternalDriver, self).__init__()

        self.os_ip_addr = os_ip_addr
        self.ap_ip_addr = ap_ip_addr
        self.identifier = identifier
        self.technology = technology # gre, vxlan, ipsec, ppp, l2tp...
        self.index = index 

        # Attributes from the identifier:
        self.usr = re.match('.*usr=([^;]+);.*', identifier)
        self.pwd = re.match('.*pwd=([^;]+);.*', identifier)
        self.port = re.match('.*port=([^;]+);.*', identifier)
        self.comm = re.match('.*comm=([^;]+);.*', identifier) # ssh, telnet...

        random.seed()

        # TODO: make the following procedure more straightforward:
        self.usr = self.p_usr.match(self.identifier)
        if self.usr is not None:
            self.usr = self.usr.group(1)
        self.pwd = self.p_pwd.match(self.identifier)
        if self.pwd is not None:
            self.pwd = self.pwd.group(1)
        self.port = self.p_port.match(self.identifier)
        if self.port is not None:
            self.port = self.port.group(1)
        self.comm = self.p_comm.match(self.identifier)
        if self.comm is not None:
            self.comm = int(self.comm.group(1)) 

        self.tag = str(index + 10)
        self.tagzero = self.tag.zfill(4)
        self.key = str(index)

    def _connect(self, ap_ip_addr, usr, pwd):
        self._log('Connecting to the remote device...')
        telnet = telnetlib.Telnet(ap_ip_addr)
#        telnet.set_debuglevel(9)
#        telnet.read_until(b'login: ')
#        telnet.write(usr.encode('ascii') + b'\r')
        telnet.read_until(b'Password: ')
        telnet.write(pwd.encode('ascii') + b'\r')
        telnet.read_until(b'#')
        self._log('Connected.')
        return telnet

    def _dispatch_cmd(self, telnet, cmd, single=True):
        telnet.write(cmd.encode('ascii') + b'\r\n')
        sleep(0.1)
        response = telnet.read_until(b'\r\n')
        self._log('RESP: ' + response)
        if single:
            telnet.read_until(b'\r\n')

    def _dispatch_cmds(self, telnet, cmdlist):
        for cmd in cmdlist:
            self._log('EXEC: ' + cmd)
            self._dispatch_cmd(telnet, cmd, False)
        del(cmdlist[:])

# TODO: use telnet.expect() ?
# TODO: don't use telnetlib ?
# TODO: why must read_until be done some time after write()?

    def attach(self):
        self._log('Attaching to device...')

        telnet = self._connect(self.ap_ip_addr, self.usr, self.pwd)
        # TODO: still assumes a "default" vlan 1 (at fe0/0) already enabled
        # and configured with the AP ip_address.
        cmdlist = []
        cmdlist.append('enable')
        cmdlist.append('vlan database')
        cmdlist.append('vlan ' + self.tag + ' name AP' + self.tagzero)
        cmdlist.append('exit')
        cmdlist.append('configure terminal')
        cmdlist.append('bridge irb')
        cmdlist.append('bridge ' + self.tag + ' protocol ieee')
        cmdlist.append('interface Tunnel' + self.tag)
        cmdlist.append('tunnel key ' + self.key)
        cmdlist.append('no ip address')
        cmdlist.append('tunnel source Vlan1 ')
        cmdlist.append('tunnel destination ' + self.os_ip_addr)
        cmdlist.append('bridge-group ' + self.tag)
        cmdlist.append('bridge-group ' + self.tag + ' spanning-disabled')
        cmdlist.append('no shutdown')
        cmdlist.append('exit')
        cmdlist.append('interface Vlan' + self.tag)
        cmdlist.append('no ip address')
        cmdlist.append('bridge-group ' + self.tag)
        cmdlist.append('no shutdown')
        cmdlist.append('exit')
        cmdlist.append('interface FastEthernet0/' + self.port)
        cmdlist.append('switchport access vlan ' + self.tag)
        cmdlist.append('spanning-tree portfast')
        cmdlist.append('no shutdown')
        cmdlist.append('end')

        self._dispatch_cmds(telnet, cmdlist)
        telnet.read_all()
        self._log('Attachment point attached!')
        telnet.close()

    def detach(self):
        self._log('Detaching from device...')

        telnet = self._connect(self.ap_ip_addr, self.usr, self.pwd)

        cmdlist = []
        cmdlist.append('enable')
        cmdlist.append('configure terminal')
        cmdlist.append('bridge irb')
        cmdlist.append('no bridge ' + self.tag + ' protocol ieee')
        cmdlist.append('interface Tunnel' + self.tag)
        cmdlist.append('no tunnel key ' + self.key)
        cmdlist.append('no ip address')
        cmdlist.append('no tunnel source Vlan1 ')
        cmdlist.append('no tunnel destination ' + self.os_ip_addr)
        cmdlist.append('no bridge-group ' + self.tag)
        cmdlist.append('no bridge-group ' + self.tag + ' spanning-disabled')
        cmdlist.append('no shutdown')
        cmdlist.append('exit')
        cmdlist.append('no interface Tunnel' + self.tag)
        cmdlist.append('interface Vlan' + self.tag)
        cmdlist.append('no ip address')
        cmdlist.append('no bridge-group ' + self.tag)
        cmdlist.append('no shutdown')
        cmdlist.append('exit')
        cmdlist.append('no interface Vlan' + self.tag)
        cmdlist.append('interface FastEthernet0/' + self.port)
        cmdlist.append('no switchport access vlan ' + self.tag)
        cmdlist.append('no spanning-tree portfast')
        cmdlist.append('no shutdown')
        cmdlist.append('end')
        cmdlist.append('vlan database')
        cmdlist.append('no vlan ' + self.tag)
        cmdlist.append('exit')

        self._dispatch_cmds(telnet, cmdlist)
        telnet.read_all()
        self._log('Attachment point detached!')
        telnet.close()
 
