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

from concurrent import futures
import os
import random

from oslo_utils import uuidutils

from neutron.tests.george import base
from neutron.tests.george.resources import machine


class SameNetworkTestBase(base.BaseGeorgeTestCase):
    def _prepare_network(self, tenant_uuid):
        network = self.safe_client.create_network(tenant_uuid)
        self.safe_client.create_subnet(
            tenant_uuid, network['id'], '20.0.0.0/24')

        return network

    def _prepare_vms_in_single_network(self):
        tenant_uuid = uuidutils.generate_uuid()
        network = self._prepare_network(tenant_uuid)
        return self._prepare_vms_in_net(tenant_uuid, network)

    def _prepare_vms_on_each_node(self):
        tenant_id = uuidutils.generate_uuid()
        network = self._prepare_network(tenant_id)
        with futures.ThreadPoolExecutor(max_workers=15) as executor:
            future = [executor.submit(
                self.useFixture,
                machine.FakeMachine(
                    host,
                    network['id'],
                    tenant_id,
                    self.safe_client))
                for host in self.computes]
        vms = [vm.result() for vm in future]
        import ipdb; ipdb.set_trace()
        for vm in vms:
            vm.wait_until_boot()

        return vms


class TestConnectivityTwoNodes(SameNetworkTestBase):
    COMPUTES_NUM = 2

    def test_conn(self):
        vms = self._prepare_vms_on_each_node()
        results = []
        with futures.ThreadPoolExecutor(
                max_workers=2000) as executor:
            while len(vms) > 1:
                src_vm = random.choice(vms)
                dst_vm = random.choice(vms)
                if src_vm != dst_vm:
                    results.append(executor.submit(
                        src_vm.block_until_ping, dst_vm.ip_address))
                    vms.pop()

        for result in results:
            result.result()


class TestConnectivityThreeNodes(TestConnectivityTwoNodes):
    COMPUTES_NUM = 3


class TestConnectivityTwoNodes2(TestConnectivityTwoNodes):
    COMPUTES_NUM = 2


class TestConnectivityScale(TestConnectivityTwoNodes):
    COMPUTES_NUM = int(os.getenv('GRG_COMPUTE', 0))

    def setUp(self):
        if not self.COMPUTES_NUM:
            self.skipTest("Scale test is disabled.")
