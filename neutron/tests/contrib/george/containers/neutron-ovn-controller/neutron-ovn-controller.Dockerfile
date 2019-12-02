FROM registry.centos.org/centos/centos:centos8
ARG RDO_REPO=https://trunk.rdoproject.org/centos8-master/current/delorean.repo
RUN dnf install -y epel-release wget centos-release-openstack-ussuri && wget $RDO_REPO -O /etc/yum.repos.d/delorean.repo && dnf install -y bash openvswitch
RUN dnf install -y autoconf automake libtool gcc patch make git openssl-devel python3 python3-devel nmap-ncat net-tools
RUN git clone https://github.com/openvswitch/ovs.git && cd ovs && ./boot.sh && ./configure --prefix=/usr --localstatedir=/var && make -j$(($(nproc) + 1))
RUN git clone https://github.com/ovn-org/ovn.git && cd ovn && ./boot.sh && ./configure --prefix=/usr --localstatedir=/var --with-ovs-source=/ovs && make -j$(($(nproc) + 1)) && make install && rm -rf ovs ovn && mkdir /var/run/ovn
RUN dnf remove -y autoconf automake libtool gcc patch make git openssl-devel python3-devel
COPY neutron/tests/contrib/george/containers/neutron-ovn-controller/start_services.sh /usr/bin/.
CMD bash /usr/bin/start_services.sh
