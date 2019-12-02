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

import fixtures


class ContainerNamespaceFixture(fixtures.Fixture):
    def __init__(self, container, name):
        self.container = container
        self.name = name

    def _setUp(self):
        super(ContainerNamespaceFixture, self)._setUp()
        self.addCleanup(self._cleanup)
        self.container.execute(['ip', 'net', 'add', self.name])

    def _cleanup(self):
        self.container.execute(['ip', 'net', 'del', self.name])

    def execute(self, cmd):
        cmd = ['ip', 'net', 'e', self.name] + cmd
        return self.container.execute(cmd)
