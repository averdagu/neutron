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

import os

import fixtures
from oslo_log import log as logging
from oslo_serialization import jsonutils
from oslo_utils import uuidutils

from neutron.agent.linux import ip_lib
from neutron.agent.linux import utils as n_utils
from neutron.tests.common.exclusive_resources import ip_network

CNI_NETWORK_DIR = '/etc/cni/net.d'

LOG = logging.getLogger(__name__)


class IptablesAcceptGatewayFixture(fixtures.Fixture):
    def __init__(self, cidr, gateway, uuid):
        self.cidr = cidr
        self.gateway = gateway
        self.uuid = uuid
        self.chain_name = ('GEORGE_%s' % self.uuid)[:28]

    def _flush_table(self):
        self.call_iptables(['-F', self.chain_name])

    def _delete_rule(self):
        self.call_iptables(['-D', 'INPUT', '-s', self.cidr,
                            '-j', self.chain_name])

    def _delete_table(self):
        self.call_iptables(['-X', self.chain_name])

    def _setUp(self):
        self.add_chain(self.chain_name)
        try:
            self.call_iptables(['-I', 'INPUT', '-s', self.cidr,
                                '-j', self.chain_name])
            self.addCleanup(self._delete_rule)
        except RuntimeError:
            pass
        self.allow_traffic_to_gateway()

    def add_chain(self, chain_name):
        try:
            self.call_iptables(['-N', self.chain_name])
            self.addCleanup(self._delete_table)
        except RuntimeError:
            pass

    def call_iptables(self, rule):
        n_utils.execute(
            ['iptables'] + rule, run_as_root=True, check_exit_code=True)

    def allow_traffic_to_gateway(self):
        """Allow traffic from all containers to the gateway.

        cidr: string - IP Network cidr
        gateway: string - IP Address of the gateway
        """
        try:
            self.call_iptables(
                ['-I', self.chain_name, '-s', self.cidr,
                 '-d', self.gateway, '-j', 'ACCEPT'])
            self.addCleanup(self._flush_table)
        except RuntimeError:
            pass


class Network(fixtures.Fixture):
    def __init__(self, name, gateway=False, priority=50):
        self.name = name
        self.gateway = gateway
        self.gateway_ip = None
        self.priority = priority
        self.uuid = uuidutils.generate_uuid()
        self.br_name = "br-%s" % self.uuid[:11]
        self.filepath = os.path.join(CNI_NETWORK_DIR, '%s-%s-%s.conflist' % (
            priority, name, self.uuid))

    def _setUp(self):
        self.addCleanup(self._cleanup)
        self.network = self.useFixture(
            ip_network.ExclusiveIPNetwork(
                '192.168.0.0', '192.168.250.0', '24')).network
        config = self._make_config()
        self._write_config(config)
        if self.gateway:
            self.useFixture(
                IptablesAcceptGatewayFixture(
                    str(self.network.cidr), self.gateway_ip, self.uuid))

    def _make_config(self):
        subnet = {'subnet': str(self.network.cidr)}
        if self.gateway:
            self.gateway_ip = str(self.network[1])
            subnet['gateway'] = self.gateway_ip

        config = {"cniVersion": "0.4.0",
                  "name": self.uuid,
                  "plugins": [
                      {"type": "bridge",
                       "bridge": self.br_name,
                       "isGateway": self.gateway,
                       "ipMasq": True,
                       "ipam": {"type": "host-local",
                                "routes": [{"dst": "0.0.0.0/0"}],
                                "ranges": [[subnet]]}},
                      {"type": "portmap",
                       "capabilities": {"portMappings": True}},
                      {"type": "firewall",
                       "backend": "iptables"}]}
        LOG.debug("Created CNI network %s", config)
        return config

    def _write_config(self, config):
        with open(self.filepath, 'w') as configfile:
            jsonutils.dump(config, configfile, indent=2)

    def _cleanup(self):
        LOG.debug("Running cleanup for network %s with bridge %s",
                  self.name, self.br_name)
        os.remove(self.filepath)
        bridge = ip_lib.IPDevice(self.br_name, kind='bridge')
        bridge.link.delete()
