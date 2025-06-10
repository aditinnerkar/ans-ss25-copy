"""
 Copyright (c) 2025 Computer Networks Group @ UPB

 Permission is hereby granted, free of charge, to any person obtaining a copy of
 this software and associated documentation files (the "Software"), to deal in
 the Software without restriction, including without limitation the rights to
 use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
 the Software, and to permit persons to whom the Software is furnished to do so,
 subject to the following conditions:

 The above copyright notice and this permission notice shall be included in all
 copies or substantial portions of the Software.

 THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
 FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
 COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
 IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
 CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
 """

#!/usr/bin/env python3

import os
import subprocess
import time

import mininet
import mininet.clean
from mininet.net import Mininet
from mininet.cli import CLI
from mininet.log import lg, info
from mininet.link import TCLink
from mininet.node import Node, OVSKernelSwitch, RemoteController
from mininet.topo import Topo
from mininet.util import waitListening, custom

from topo import Fattree
import topo


class FattreeNet(Topo):
    """
    Create a fat-tree network in Mininet from a Fattree graph object.
    """

    def __init__(self, ft_topo):

        Topo.__init__(self)

        # A mapping from topo.Node objects to their Mininet names
        node_map = {}
        host_count = 0

        # Define link properties
        link_opts = dict(bw=15, delay='5ms')

        # Add hosts
        for host_node in ft_topo.servers:
            host_count += 1
            # Simple host naming: h1, h2, ...
            host_name = f'h{host_count}'
            # IP address based on the paper's scheme: 10.pod.switch.ID
            # The subnet mask /8 is used to place all hosts in the same subnet
            ip_addr = f'10.{host_node.pod}.{host_node.sw}.{host_node.hid}/8'
            h = self.addHost(host_name, ip=ip_addr)
            node_map[host_node] = h
            
        # Add switches with descriptive names
        for switch_node in ft_topo.switches:
            # Descriptive naming: c for core, a for aggregation, e for edge
            type_char = switch_node.type[0]
            switch_name = f'{type_char}{switch_node.id + 1}'
            s = self.addSwitch(switch_name)
            node_map[switch_node] = s
            
        # Add links by iterating through the edges of the graph
        added_edges = set()
        all_nodes = ft_topo.servers + ft_topo.switches
        for node in all_nodes:
            for edge in node.edges:
                # Ensure each link is only added once
                if edge not in added_edges:
                    node1 = edge.lnode
                    node2 = edge.rnode
                    
                    mn_node1 = node_map[node1]
                    mn_node2 = node_map[node2]
                    
                    self.addLink(mn_node1, mn_node2, **link_opts)
                    added_edges.add(edge)


def make_mininet_instance(graph_topo):
    """
    Creates a Mininet instance with a remote controller.
    """
    net_topo = FattreeNet(graph_topo)
    net = Mininet(topo=net_topo, controller=None, autoSetMacs=True, switch=OVSKernelSwitch)
    net.addController('c0', controller=RemoteController,
                      ip="127.0.0.1", port=6653)
    return net


def run(graph_topo):
    """
    Starts the Mininet network and runs the CLI.
    """
    # Run the Mininet CLI with a given topology
    lg.setLogLevel('info')
    mininet.clean.cleanup()
    net = make_mininet_instance(graph_topo)

    info('*** Starting network ***\n')
    net.start()
    info('*** Running CLI ***\n')
    CLI(net)
    info('*** Stopping network ***\n')
    net.stop()


if __name__ == '__main__':
    # For this lab, we build a k=4 fat-tree
    ft_topo = topo.Fattree(4)
    run(ft_topo)
