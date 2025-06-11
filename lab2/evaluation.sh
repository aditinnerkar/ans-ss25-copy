#!/bin/bash

# ==============================================================================
# All-to-all iperf test to measure the
# aggregate bisection bandwidth under a random traffic pattern.
#
# Usage:
# 1. Start Ryu controller (e.g., ryu-manager ft_routing.py)
# 2. Make this script executable: chmod +x run_evaluation.sh
# 3. Run with sudo:           
#     sudo ./run_evaluation.sh
# ==============================================================================

set -e

# Ensure we run with root privileges for Mininet
if [ "$EUID" -ne 0 ]; then
  echo "Please run this script with sudo"
  exit
fi


echo "-> Starting Fat-Tree Bandwidth Test..."

# Use a "here document" to pass the entire Python script to the python3 interpreter.
# This avoids needing a separate .py file for the test logic.
sudo python3 - <<EOF

import sys
import os
import time
import random
import re
from mininet.net import Mininet
from mininet.log import setLogLevel, info
from mininet.node import RemoteController
from mininet.clean import cleanup
from mininet.topo import Topo

# Add the current directory to the Python path to allow importing local modules
sys.path.insert(0, os.getcwd())

# Import the Fattree class from your topo.py file
from topo import Fattree

# --- Inlined FattreeNet Class ---
# The FattreeNet class is copied here directly from fat-tree.py file.
# This avoids the ModuleNotFoundError
class FattreeNet(Topo):
    """
    Create a fat-tree network in Mininet from a Fattree graph object.
    """
    def __init__(self, ft_topo):
        Topo.__init__(self)
        node_map = {}
        host_count = 0
        link_opts = dict(bw=15, delay='5ms')

        for host_node in ft_topo.servers:
            host_count += 1
            host_name = f'h{host_count}'
            ip_addr = f'10.{host_node.pod}.{host_node.sw}.{host_node.hid}/8'
            h = self.addHost(host_name, ip=ip_addr)
            node_map[host_node] = h
            
        for switch_node in ft_topo.switches:
            type_char = switch_node.type[0]
            switch_name = f'{type_char}{switch_node.id + 1}'
            s = self.addSwitch(switch_name)
            node_map[switch_node] = s
            
        added_edges = set()
        all_nodes = ft_topo.servers + ft_topo.switches
        for node in all_nodes:
            for edge in node.edges:
                if edge not in added_edges:
                    node1 = edge.lnode
                    node2 = edge.rnode
                    mn_node1 = node_map[node1]
                    mn_node2 = node_map[node2]
                    self.addLink(mn_node1, mn_node2, **link_opts)
                    added_edges.add(edge)
# --- End of Inlined Class ---


def run_performance_test():
    """
    Sets up the fat-tree network, runs a comprehensive iperf test,
    and reports the aggregate bandwidth.
    """
    
    cleanup()
    setLogLevel('info')

    k = 4
    fat_tree_topo = Fattree(k)
    # Use the inlined FattreeNet class defined above
    net = Mininet(topo=FattreeNet(fat_tree_topo), controller=None, autoSetMacs=True)
    net.addController('c0', controller=RemoteController, ip="127.0.0.1", port=6653)

    try:
        net.start()
        info("\n*** Network started. Waiting 15 seconds for controller to stabilize...\n")
        time.sleep(15)

        info("*** Verifying network reachability with pingall...\n")
        if net.pingAll() > 0:
            info("!!! Some hosts are unreachable. Aborting bandwidth test. !!!\n")
            return

        info("\n*** Reachability confirmed. Starting bandwidth measurement.\n")
        
        hosts = net.hosts
        host_names = [h.name for h in hosts]
        
        destinations = list(host_names)
        random.shuffle(destinations)

        traffic_pairs = []
        for i in range(len(host_names)):
            src = host_names[i]
            dst = destinations[i]
            if src == dst:
                swap_idx = (i + 1) % len(host_names)
                destinations[i], destinations[swap_idx] = destinations[swap_idx], destinations[i]
            traffic_pairs.append((src, destinations[i]))
        
        info("*** Starting iperf servers on all hosts...\n")
        for h in hosts:
            h.cmd('iperf -s &')
        
        time.sleep(2)

        info("*** Starting iperf clients for all pairs simultaneously...\n")
        client_processes = {}
        for src_name, dst_name in traffic_pairs:
            src_host = net.get(src_name)
            dst_host = net.get(dst_name)
            cmd = f'iperf -c {dst_host.IP()} -t 10 -y C'
            client_processes[f"{src_name}->{dst_name}"] = src_host.popen(cmd)

        info("*** Running iperf for 12 seconds...\n")
        time.sleep(12)

        info("*** Parsing iperf results...\n")
        total_bandwidth = 0.0
        for label, process in client_processes.items():
            process.wait()
            output = process.stdout.read().decode('utf-8').strip()
            
            parts = output.split(',')
            if len(parts) == 9:
                try:
                    bandwidth_bits = float(parts[8])
                    bandwidth_mbps = bandwidth_bits / 1e6
                    info(f"    {label}: {bandwidth_mbps:.2f} Mbps\n")
                    total_bandwidth += bandwidth_mbps
                except (ValueError, IndexError):
                    info(f"    {label}: FAILED (Could not parse bandwidth from output: {output})\n")
            else:
                info(f"    {label}: FAILED (iperf command produced no valid output)\n")
        
        print("-" * 50)
        info(f"Total Aggregate Bandwidth: {total_bandwidth:.2f} Mbps\n")
        print("-" * 50)

    except Exception as e:
        info(f"An error occurred: {e}\n")
    finally:
        info("*** Stopping network and cleaning up.\n")
        if net:
            for h in net.hosts:
                h.cmd('kill %iperf')
            net.stop()
        cleanup()

if __name__ == '__main__':
    run_performance_test()

EOF

echo "-> Bandwidth test completed."
