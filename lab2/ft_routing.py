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

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ipv4, arp, ether_types
from ryu.lib import hub

from ryu.topology import event, switches
from ryu.topology.api import get_switch, get_link

import topo


class FTRouter(app_manager.RyuApp):

    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(FTRouter, self).__init__(*args, **kwargs)
        
        # Initialize the topology with #ports=4
        self.topo_net = topo.Fattree(4)
        self.k = 4 # Number of ports for the fat-tree

        # Data structures for topology and host discovery
        self.topology = {}   # {dpid: {'type': 'core'|'agg'|'edge', 'pod': pod_num, 'pos': pos_in_pod}}
        self.links = {}      # {dpid: {neighbor_dpid: port_no}}
        self.hosts = {}      # {host_ip: (mac, dpid, port)}
        self.datapaths = {}  # {dpid: datapath_object}
        self.is_active = True # Flag to control threads
        self.lock = hub.Semaphore(1) # Lock to prevent race conditions
        
        # Total inter-switch links
        self.total_links = (self.k**3) // 2 
        self.total_switches = len(self.topo_net.switches)

        # Build the static map of what each switch is
        self.build_static_topology_map()
        # Start a thread to poll for network readiness
        self.install_thread = hub.spawn(self._install_proactive_flows_thread)

    def close(self):
        """Cleanup on exit."""
        self.is_active = False
        hub.kill(self.install_thread)
        hub.joinall([self.install_thread])

    def build_static_topology_map(self):
        """Builds the map of switch types, pods, and positions from the topo object."""
        core_switches_count = (self.k // 2)**2
        agg_switches_per_pod = self.k // 2
        edge_switches_per_pod = self.k // 2
        agg_switches_total = self.k * agg_switches_per_pod

        for sw_obj in self.topo_net.switches:
            dpid = sw_obj.id + 1
            if sw_obj.type == 'core':
                self.topology[dpid] = {'type': 'core', 'pod': -1}
            elif sw_obj.type == 'aggregation':
                pod = (sw_obj.id - core_switches_count) // agg_switches_per_pod
                self.topology[dpid] = {'type': 'aggregation', 'pod': pod}
            elif sw_obj.type == 'edge':
                edge_base_id = core_switches_count + agg_switches_total
                pod = (sw_obj.id - edge_base_id) // edge_switches_per_pod
                pos = (sw_obj.id - edge_base_id) % edge_switches_per_pod
                self.topology[dpid] = {'type': 'edge', 'pod': pod, 'pos': pos}

    # Topology discovery
    @set_ev_cls(event.EventLinkAdd)
    def link_add_handler(self, ev):
        """Passively build the link map in a thread-safe manner."""
        with self.lock:
            s1 = ev.link.src
            s2 = ev.link.dst
            self.links.setdefault(s1.dpid, {})[s2.dpid] = s1.port_no
            self.links.setdefault(s2.dpid, {})[s1.dpid] = s2.port_no

    def _install_proactive_flows_thread(self):
        """A separate thread to wait for full topology discovery and then install flows."""
        while self.is_active:
            with self.lock:
                # Count unique links discovered so far inside the lock to get a consistent view
                num_discovered_links = len({tuple(sorted((s, d))) for s in self.links for d in self.links[s]})
            
            # Check if all switches and links are discovered
            if len(self.datapaths) == self.total_switches and num_discovered_links == self.total_links:
                try:
                    self.logger.info("All %d switches and %d links discovered. Installing flows.", len(self.datapaths), num_discovered_links)
                    self.install_all_flow_rules()
                    self.logger.info("Flow installation complete.")
                except Exception as e:
                    self.logger.error("Error during flow installation: %s", e)
                finally:
                    break # End the thread after attempting installation
            
            hub.sleep(1)


    def install_all_flow_rules(self):
        """
        Calculates and installs all necessary flow rules for the two-level
        routing scheme proactively.
        """
        for dpid, dp in self.datapaths.items():
            parser = dp.ofproto_parser
            ofproto = dp.ofproto
            switch_info = self.topology.get(dpid)

            if not switch_info: continue

            # --- Rule installation for EDGE switches ---
            if switch_info['type'] == 'edge':
                # Rule 1 (Highest Priority): Forward to directly connected hosts
                for i in range(self.k // 2):
                    host_ip = f"10.{switch_info['pod']}.{switch_info['pos']}.{i+2}"
                    out_port = i + 1 
                    match = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP, ipv4_dst=host_ip)
                    actions = [parser.OFPActionOutput(out_port)]
                    self.add_flow(dp, 2, match, actions)
                
                # Rule 2 (Lower Priority): Load balance UP to aggregation switches
                agg_actions = [parser.OFPActionOutput(p) for n,p in self.links[dpid].items() if self.topology.get(n,{}).get('type') == 'aggregation']
                if agg_actions:
                    buckets = [parser.OFPBucket(actions=[a]) for a in agg_actions]
                    group_id = dpid
                    req = parser.OFPGroupMod(dp, ofproto.OFPGC_ADD, ofproto.OFPGT_SELECT, group_id, buckets)
                    dp.send_msg(req)
                    match = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP)
                    actions = [parser.OFPActionGroup(group_id)]
                    self.add_flow(dp, 1, match, actions)

            # --- Rule installation for AGGREGATION switches ---
            elif switch_info['type'] == 'aggregation':
                # Rule 1 (Higher Priority): Forward DOWN to specific edge switches for intra-pod traffic
                for n, p in self.links[dpid].items():
                    if self.topology.get(n,{}).get('type') == 'edge':
                        edge_info = self.topology[n]
                        edge_subnet = f"10.{edge_info['pod']}.{edge_info['pos']}.0/24"
                        match = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP, ipv4_dst=edge_subnet)
                        actions = [parser.OFPActionOutput(p)]
                        self.add_flow(dp, 2, match, actions)

                # Rule 2 (Lower Priority): Load balance UP to core switches
                core_actions = [parser.OFPActionOutput(p) for n,p in self.links[dpid].items() if self.topology.get(n,{}).get('type') == 'core']
                if core_actions:
                    buckets = [parser.OFPBucket(actions=[a]) for a in core_actions]
                    group_id = dpid
                    req = parser.OFPGroupMod(dp, ofproto.OFPGC_ADD, ofproto.OFPGT_SELECT, group_id, buckets)
                    dp.send_msg(req)
                    match = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP)
                    actions = [parser.OFPActionGroup(group_id)]
                    self.add_flow(dp, 1, match, actions)

            # --- Rule installation for CORE switches ---
            elif switch_info['type'] == 'core':
                # Forward DOWN to pods based on destination prefix
                for pod in range(self.k):
                    pod_prefix = f"10.{pod}.0.0/16"
                    for n, p in self.links[dpid].items():
                        if self.topology.get(n,{}).get('pod') == pod:
                            match = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP, ipv4_dst=pod_prefix)
                            actions = [parser.OFPActionOutput(p)]
                            self.add_flow(dp, 1, match, actions)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        
        # Store datapath object
        self.datapaths[datapath.id] = datapath

        # Install entry-miss flow entry
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)

    # Add a flow entry to the flow-table
    def add_flow(self, datapath, priority, match, actions):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # Construct flow_mod message and send it
        inst = [parser.OFPInstructionActions(
            ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
                                match=match, instructions=inst)
        datapath.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        dpid = datapath.id
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)

        # Ignore LLDP packets
        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        # Handle ARP packets
        arp_pkt = pkt.get_protocol(arp.arp)
        if arp_pkt:
            src_ip = arp_pkt.src_ip
            dst_ip = arp_pkt.dst_ip
            src_mac = eth.src

            # Learn source host location if not already known
            if src_ip not in self.hosts:
                self.hosts[src_ip] = (src_mac, dpid, in_port)
                self.logger.info("Learned host: IP %s at switch %d, port %d", src_ip, dpid, in_port)

            # If we know the destination host, forward the ARP packet directly to it
            if dst_ip in self.hosts:
                dst_mac, dst_dpid, dst_port = self.hosts[dst_ip]
                dst_datapath = self.datapaths.get(dst_dpid)
                if dst_datapath:
                    self.logger.debug("ARP target %s known. Forwarding directly to s%d-p%d", dst_ip, dst_dpid, dst_port)
                    actions = [parser.OFPActionOutput(dst_port)]
                    out = parser.OFPPacketOut(datapath=dst_datapath,
                                              buffer_id=ofproto.OFP_NO_BUFFER,
                                              in_port=ofproto.OFPP_CONTROLLER,
                                              actions=actions, data=msg.data)
                    dst_datapath.send_msg(out)
                else:
                    self.logger.warning("ARP target switch %d not found.", dst_dpid)
            # If destination is unknown, flood the ARP request to discover it
            else:
                self.logger.debug("ARP target %s unknown. Flooding.", dst_ip)
                actions = [parser.OFPActionOutput(ofproto.OFPP_FLOOD)]
                out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                          in_port=in_port, actions=actions, data=msg.data)
                datapath.send_msg(out)
