FROM fedora:36

VOLUME [ "/var/router" ]

WORKDIR /opt/dnsmasq

# Dependencies and other goodies
RUN dnf install -y dnsmasq iproute bind-utils curl vim