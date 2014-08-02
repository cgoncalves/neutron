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

import re
import paramiko
import socket
import random

from neutron.agent.external.drivers.external_driver import ExternalDriver

class OpenWrtDriver(ExternalDriver):
    """OpenWrt External driver for automating
    configuration on attachment points.
    Currently communicates only through SSH, configuring
    devices via UCI and Open vSwitch.
    This driver makes use of provided
    indices to assign GRE keys in a == fashion."""

    @classmethod
    def driver_name(cls):
        return 'openwrt'

    def __init__(self, os_ip_addr, ap_ip_addr, identifier, technology, index):
        super(ExternalDriver, self).__init__()

        self.os_ip_addr = os_ip_addr
        self.ap_ip_addr = ap_ip_addr
        self.identifier = identifier
        self.technology = technology
        self.index = index

        # Attributes from the identifier:
        self.usr = re.match('.*usr=([^;]+);.*', self.identifier).group(1)
        self.pwd = re.match('.*pwd=([^;]+);.*', self.identifier).group(1)
        self.ssid_name = re.match('.*ssid_name=([^;]+);.*', self.identifier).group(1)
        self.ssid_pass = re.match('.*ssid_pass=([^;]+);.*', self.identifier).group(1)
        # TODO robustness on identifier processing
        # + feed back errors to the External Agent.
        # TODO non-mandatory identifier attributes.
        # TODO process identifier in order, avoiding ambiguous matches.

        # TODO: use device's shell commands (egrep, cut, sed, awk) to extract
        # info, instead of heavy python-side regex matching.
        self.ppr = re.compile('R: (.*)') # for matching shell results
        self.ppveth = re.compile('.*veth([0-9]+).*') # for matching veth names

        random.seed()

    def _connect(self, ap_ip_addr, usr, pwd):
        client = paramiko.SSHClient()
        client.load_system_host_keys()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self._log('Connecting to the remote device...')
        client.connect(ap_ip_addr, username=usr, password=pwd)
        self.channel = client.invoke_shell()
        self.channel.settimeout(0.5)
        stdin = self.channel.makefile('wb')
        stdout = self.channel.makefile('rb')
        self._log('Connected.')
        return client, stdin, stdout

    def _read_stream_to_list(self, stream):
        """Not very pretty, but allows us to read multi-line"""
        lines  = []
        try:
            for line in stream:
                lines.append(line)
        except socket.timeout:
            pass
        return lines

    def _get_fw_zone_index(self, stdin, stdout, zone):
        stdin.write('''
        get_each_zone() {
          local config="$1"
          local name
          config_get name "$config" name
          echo "R: $name"
        }
        config_load firewall
        config_foreach get_each_zone zone
        ''')
        stdin.flush()
        
        zone_index = 0
        try:
            for line in stdout:
                m = self.ppr.match(line)
                if m:
                    zone_name = m.group(1).strip()
                    if zone_name in (zone, ''):
                        break
                    zone_index+=1
        except socket.timeout:
            pass
        self._read_stream_to_list(stdout) # clear stdout
            
        if zone_name == '':
            self._log('LAN Zone entry could not be found!')
            # TODO: rollback.
            return
        return zone_index

    # TODO: Ditch OVS and veth pairs at the OpenWrt device.
    # Normal EoGRE interfaces attached to each br-vlan####
    # bridge is enough.
    # TODO: Ethernet port support as well, via identifier.
    def attach(self):
        self._log('Attaching to device...')

        gre_key = str(self.index)
    
        client, stdin, stdout = self._connect(self.ap_ip_addr, self.usr, self.pwd)

        # Iterate over all taken VLAN tags:
        stdin.write('''
        . /lib/functions.sh
        get_each_vlan() {
          local config="$1"
          local vlan
          config_get vlan "$config" vlan
          echo "R: $vlan"
        }
        config_load network
        config_foreach get_each_vlan switch_vlan
        ''')
        stdin.flush()

        vlans_taken = []
        try:
            for line in stdout:
                m = self.ppr.match(line)
                if m:
                    vlan = m.group(1).strip()
                    vlans_taken.append(vlan)
        except socket.timeout:
            pass
        self._read_stream_to_list(stdout) # clear stdout

        self._log('VLANs taken: %s', vlans_taken)

        # Find a free VLAN tag.
        while True:
            tag = str(random.randint(2,4095))
            if tag not in vlans_taken: # stop condition
                break
        tag = str(tag)

        self._log("New VLAN to assign: %s", tag)

        # VLAN tag with leading zeros.
        tagzero = tag.zfill(4)

        # Get "lan" firewall zone:
        zone_index = str(self._get_fw_zone_index(stdin, stdout, 'lan'))

        # Get its assigned networks:
        stdin.write('uci get firewall.@zone[' + zone_index + '].network\n')
        stdin.flush()
        results = self._read_stream_to_list(stdout)
        networks = results[-1].strip() #  "lan"
        # Insert new VLAN to firewall zone:
        networks = "%s %s%s" % (networks, 'vlan', tagzero)
        self._log('Networks in lan firewall zone afterwards: %s', networks)

        # Find a free gap of one veth pair, to fill it up.
        stdin.write('ifconfig -a | grep veth | sort\n')
        stdin.flush()
        veth = -1
        try:
            for line in stdout:
                m = self.ppveth.match(line)
                if m:
                    newveth = int(m.group(1))
                    if newveth - veth > 2:
                        break
                    veth = newveth
        except socket.timeout:
            pass
        self._read_stream_to_list(stdout) # clear stdout
        # TODO: add almost impossible case of having all veths exhausted.

        # Now the driver knows it should create veth{veth+1} and veth{veth+2}

        veth1 = str(veth+1)
        veth2 = str(veth+2)

        # TODO: instead of waiting up to 10 seconds, make sure that the whole
        # function gets executed even if the SSH connection
        # goes down: when network is restarted.
        # TODO: do not assume there's only 1 integrated switch

        # This new timeout is to make sure the function executes until
        # the end (network restart takes 5-10 seconds):
        self.channel.settimeout(15.0)
        # Pour configurations:
        self._log('Pouring attachment point configurations into the device...')
        stdin.write('''
        commit_all() {
        ip link add veth''' + veth1 + ''' type veth peer name veth''' + veth2 + '''
                    print("VLAN: ", vlan)
        ip link set up dev veth''' + veth1 + '''
        ip link set up dev veth''' + veth2 + '''
        uci set network.vlan''' + tagzero + '''=interface
        uci set network.vlan''' + tagzero + '''.type=bridge
        uci set network.vlan''' + tagzero + '''.proto=none
        uci set network.vlan''' + tagzero + '''.ifname="eth0.''' + tag
        + ''' veth''' + veth1 + '''"
        uci set network.@switch[0].enable_vlan4k=1
        uci add network switch_vlan
        uci set network.@switch_vlan[-1].device=switch0
        uci set network.@switch_vlan[-1].ports=5t
        uci set network.@switch_vlan[-1].vlan=''' + tag + '''
        uci set firewall.@zone[''' + zone_index + '''].network="''' + networks + '''"
        uci set dhcp.vlan''' + tagzero + '''=dhcp
        uci set dhcp.@dhcp[-1].interface=vlan''' + tagzero + '''
        uci set dhcp.@dhcp[-1].ignore=1
        uci add wireless wifi-iface
        uci set wireless.@wifi-iface[-1].device=radio0
        uci set wireless.@wifi-iface[-1].mode=ap
        uci set wireless.@wifi-iface[-1].ssid=''' + self.ssid_name + '''
        uci set wireless.@wifi-iface[-1].encryption=psk2
        uci set wireless.@wifi-iface[-1].key=''' + self.ssid_pass + '''
        uci set wireless.@wifi-iface[-1].network=vlan''' + tagzero + '''
        uci commit
        rmmod ip_gre
        /etc/init.d/network restart
        /etc/init.d/dnsmasq restart
        /etc/init.d/firewall restart
        ovs-vsctl add-br br-ap''' + tagzero + '''
        ovs-vsctl add-port br-ap''' + tagzero + ''' gre-''' + tagzero + '''
        ovs-vsctl set interface gre-''' + tagzero + ''' type=gre options:remote_ip='''
        + self.os_ip_addr + ''' options:local_ip=''' + self.ap_ip_addr
        + ''' options:key=''' + gre_key + '''
        ovs-vsctl add-port br-ap''' + tagzero + ''' veth''' + veth2 + '''
        }
        commit_all
        exit
        ''')
        stdin.flush()
        self._read_stream_to_list(stdout) # to wait until executed
        self._log('Attachment point attached!')

        # stdin must be before stdout
        stdin.close()
        stdout.close()
        client.close()

    def detach(self):
        self._log('Detaching from device...')

        client, stdin, stdout = self._connect(self.ap_ip_addr, self.usr, self.pwd)

        # Find SSID index to then get the network name:
        stdin.write('''
        . /lib/functions.sh
        get_each_ssid() {
          local config="$1"
          local ssid
          config_get ssid "$config" ssid
          echo "R: $ssid"
        }
        config_load wireless
        config_foreach get_each_ssid wifi-iface
        ''')
        stdin.flush()

        ssid_index = 0
        try:
            for line in stdout:
                m = self.ppr.match(line)
                if m:
                    ssid_name = m.group(1).strip()
                    if ssid_name in (self.ssid_name, ''):
                        break
                    ssid_index+=1
                ssid_name = ''
        except socket.timeout:
            pass
        self._read_stream_to_list(stdout) # clear stdout

        if ssid_name == '':
            self._log('SSID entry could not be found!')
            return
        ssid_index = str(ssid_index)

        stdin.write('uci get wireless.@wifi-iface[' + ssid_index + '].network\n')
        stdin.flush()
        results = self._read_stream_to_list(stdout)
        network_name = results[-1].strip()

        tagzero = re.match('vlan([0-9]+)', network_name).group(1) # VLAN tag of SSID.
        tag = str(int(tagzero)) # VLAN tag without leading zeros.

        # Find DHCP index respective to this network:
        stdin.write('''
        get_each_dhcp() {
          local config="$1"
          local interface
          config_get interface "$config" interface
          echo "R: $interface"
        }
        config_load dhcp
        config_foreach get_each_dhcp dhcp
        ''')
        stdin.flush()

        dhcp_index = 0
        try:
            for line in stdout:
                m = self.ppr.match(line)
                if m:
                    dhcp_name = m.group(1).strip()
                    if dhcp_name in (network_name, ''):
                        break
                    dhcp_index+=1
                dhcp_name = ''
        except socket.timeout:
            pass
        self._read_stream_to_list(stdout) # clear stdout

        if dhcp_name == '':
            self._log('DHCP entry could not be found')
            # TODO: rollback.
            return
        dhcp_index = str(dhcp_index)

        # Find VLAN entry:
        stdin.write('''
        get_each_vlan() {
          local config="$1"
          local vlan
          config_get vlan "$config" vlan
          echo "R: $vlan"
        }
        config_load network
        config_foreach get_each_vlan switch_vlan
        ''')
        stdin.flush()

        vlan_index = 0
        try:
            for line in stdout:
                m = self.ppr.match(line)
                if m:
                    vlan_name = m.group(1).strip()
                    if vlan_name in (tag, ''):
                        break
                    vlan_index+=1
                vlan_name = ''
        except socket.timeout:
            pass
        self._read_stream_to_list(stdout) # clear stdout

        if vlan_name == '':
            self._log('Switch VLAN entry could not be found')
            # TODO: rollback.
            return
        vlan_index = str(vlan_index)

        # Get "lan" firewall zone:
        zone_index = str(self._get_fw_zone_index(stdin, stdout, 'lan'))

        # Remove VLAN from the "lan" firewall zone:
        stdin.write('uci get firewall.@zone[' + zone_index + '].network\n')
        stdin.flush()
        results = self._read_stream_to_list(stdout)
        networks = results[-1].strip()
        networks = networks.replace(' vlan' + tagzero, '')
        self._log('Networks in lan firewall zone afterwards: %s', networks)

        # Find veth interface attached to the OVS, for further (pair) deletion:
        stdin.write('ovs-ofctl show br-ap' + tagzero + ' | egrep veth[0-9]+ -o\n')
        stdin.flush()
        results = self._read_stream_to_list(stdout)
        veth_name = results[-1].strip()

        # TODO: do not assume there's only 1 integrated switch
        self.channel.settimeout(15.0)
        stdin.write('''
        commit_all() {
        ovs-vsctl del-br br-ap''' + tagzero + '''
        ip link del ''' + veth_name + '''
        uci delete wireless.@wifi-iface[''' + ssid_index + ''']
        uci delete dhcp.@dhcp[''' + dhcp_index + ''']
        uci delete network.''' + network_name + '''
        uci delete network.@switch_vlan[''' + vlan_index + ''']
        uci set firewall.@zone[''' + zone_index + '''].network="''' + networks + '''"
        uci commit
        /etc/init.d/network restart
        /etc/init.d/dnsmasq restart
        /etc/init.d/firewall restart
        }
        commit_all
        exit
        ''')
        stdin.flush()
        self._read_stream_to_list(stdout) # to wait until executed
        self._log('Attachment point detached!')

        # TODO: latest detachment only:
        #uci delete network.@switch[0].enable_vlan4k

        # stdin must be before stdout
        stdin.close()
        stdout.close() 
        client.close()
