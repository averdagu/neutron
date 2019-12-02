FROM localhost/neutron-ovn-controller:latest
ADD . /neutron
RUN dnf install -y net-tools nmap-ncat python3-pip python3-devel gcc git && cd /neutron && pip3 install . && pip3 install pymysql && dnf remove -y gcc python3-devel
COPY neutron/tests/contrib/george/containers/neutron-server-ovn/start_services.sh /usr/bin/.
EXPOSE 6641/tcp
EXPOSE 6642/tcp
EXPOSE 9696/tcp
CMD bash /usr/bin/start_services.sh
