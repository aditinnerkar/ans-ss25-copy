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
from ryu.topology import event, switches
from ryu.topology.api import get_switch, get_link, get_host
from ryu.lib import hub

import topo

class SPRouter(app_manager.RyuApp):
    """
    A robust Ryu controller that implements shortest-path routing.
    This version uses proactive flow installation and stable, event-driven
    topology discovery.
    """
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(SPRouter, self).__init__(*args, **kwargs)
        self.topology_graph = {}  # {dpid: {neighbor_dpid: port_no}}
        self.hosts = {}           # {host_ip: (mac, dpid, port_no)}
        self.datapaths = {}       # {dpid: datapath_object}
        self.topology_lock = hub.Semaphore(1)
        self.keep_alive_thread = hub.spawn(self._keep_alive)
        self.link_discovery_thread = hub.spawn(self._periodic_link_discovery)
        self.logger.info("Proactive Shortest Path Router Initialized")

    def _keep_alive(self):
        """A simple greenlet to periodically log a message."""
        while True:
            self.logger.info("RYU-CONTROLLER-ALIVE: Waiting for network events...")
            hub.sleep(15)

    def _periodic_link_discovery(self):
        """Periodically update the topology graph."""
        while True:
            self._update_links()
            hub.sleep(5)  # Update every 5 seconds

    def _update_links(self):
        """
        Queries Ryu for all links and updates the topology graph.
        """
        link_list = get_link(self, None)
        with self.topology_lock:
            # Clear existing links
            for dpid in self.topology_graph:
                self.topology_graph[dpid] = {}
            
            # Add all discovered links
            for link in link_list:
                src, dst = link.src.dpid, link.dst.dpid
                src_port, dst_port = link.src.port_no, link.dst.port_no
                self.topology_graph.setdefault(src, {})[dst] = src_port
                self.topology_graph.setdefault(dst, {})[src] = dst_port
                self.logger.info("Discovered link: %s:%d <-> %s:%d", 
                               src, src_port, dst, dst_port)
            
            # Log the complete topology
            self.logger.info("Link discovery complete. Current topology graph: %s", 
                           self.topology_graph)
            
            # Verify topology completeness
            total_switches = len(self.datapaths)
            switches_with_links = len([dpid for dpid, neighbors in self.topology_graph.items() 
                                     if neighbors])
            self.logger.info("Topology completeness: %d/%d switches have links", 
                           switches_with_links, total_switches)

    @set_ev_cls(event.EventSwitchEnter)
    def _handler_switch_enter(self, ev):
        """
        Handles new switches connecting to the controller.
        """
        dpid = ev.switch.dp.id
        with self.topology_lock:
            self.topology_graph.setdefault(dpid, {})
            self.datapaths[dpid] = ev.switch.dp
        self.logger.info("Switch %s has entered.", dpid)

        # Trigger immediate link discovery
        self._update_links()

    def add_flow(self, datapath, priority, match, actions):
        """Helper to add a flow entry."""
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(datapath=datapath, priority=priority, match=match, instructions=inst)
        datapath.send_msg(mod)

    def get_path(self, src, dst):
        """Calculates shortest path using Dijkstra's algorithm."""
        import heapq
        with self.topology_lock:
            graph = self.topology_graph
            if src not in graph or dst not in graph:
                self.logger.error("Cannot find path: src=%s or dst=%s not in graph", src, dst)
                return []
            
            distance = {node: float('inf') for node in graph}
            previous = {node: None for node in graph}
            distance[src] = 0
            pq = [(0, src)]

            while pq:
                dist, current_node = heapq.heappop(pq)
                if current_node == dst: break
                if dist > distance[current_node]: continue
                
                for neighbor in graph.get(current_node, {}):
                    new_dist = dist + 1
                    if new_dist < distance[neighbor]:
                        distance[neighbor] = new_dist
                        previous[neighbor] = current_node
                        heapq.heappush(pq, (new_dist, neighbor))

        path = []
        curr = dst
        while curr is not None:
            path.append(curr)
            curr = previous.get(curr)
        path.reverse()
        
        if path and path[0] == src:
            self.logger.info("Found path from %s to %s: %s", src, dst, path)
            return path
        else:
            self.logger.error("No valid path found from %s to %s", src, dst)
            return []

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        """Installs the table-miss flow entry."""
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)
        self.logger.info("Installed table-miss flow for switch %s", datapath.id)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        dpid = datapath.id
        in_port = msg.match['in_port']
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        
        # Avoid processing Link Layer Discovery Protocol packets
        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        # --- ARP HANDLING ---
        arp_pkt = pkt.get_protocol(arp.arp)
        if arp_pkt:
            src_ip, dst_ip = arp_pkt.src_ip, arp_pkt.dst_ip
            src_mac = arp_pkt.src_mac

            # Learn host location from ARP packet
            if src_ip not in self.hosts:
                 self.hosts[src_ip] = (src_mac, dpid, in_port)
                 self.logger.info("Discovered host: IP %s, MAC %s, at switch %s port %s", src_ip, src_mac, dpid, in_port)

            # If it's a unicast ARP reply and we know the destination, send it there directly.
            # Otherwise, flood the ARP request.
            if dst_ip in self.hosts:
                dst_mac, dst_dpid, dst_port = self.hosts[dst_ip]
                dst_datapath = self.datapaths[dst_dpid]
                actions = [dst_datapath.ofproto_parser.OFPActionOutput(dst_port)]
                # Use the correct OFPP_CONTROLLER constant from the destination datapath
                out = dst_datapath.ofproto_parser.OFPPacketOut(datapath=dst_datapath,
                                                          buffer_id=0xffffffff,
                                                          in_port=dst_datapath.ofproto.OFPP_CONTROLLER,
                                                          actions=actions, data=msg.data)
                dst_datapath.send_msg(out)
            else:
                actions = [datapath.ofproto_parser.OFPActionOutput(datapath.ofproto.OFPP_FLOOD)]
                out = datapath.ofproto_parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                          in_port=in_port, actions=actions, data=msg.data)
                datapath.send_msg(out)
            return

        # --- IP PACKET HANDLING ---
        ip_pkt = pkt.get_protocol(ipv4.ipv4)
        if ip_pkt:
            src_ip, dst_ip = ip_pkt.src, ip_pkt.dst
            
            # Learn source host if unknown
            if src_ip not in self.hosts:
                self.hosts[src_ip] = (eth.src, dpid, in_port)
                self.logger.info("Discovered host: IP %s, MAC %s, at switch %s port %s", src_ip, eth.src, dpid, in_port)
            
            # If destination is known, install path proactively
            if dst_ip in self.hosts:
                dst_mac, dst_dpid, dst_port = self.hosts[dst_ip]
                path = self.get_path(dpid, dst_dpid)
                
                if not path:
                    self.logger.error("No path from %s to %s", dpid, dst_dpid)
                    return

                self.logger.info("Installing proactive path: %s", path)
                # Install flow rules on all switches along the path
                for i in range(len(path)):
                    current_dpid = path[i]
                    current_dp = self.datapaths[current_dpid]
                    
                    if i < len(path) - 1: # Not the last switch
                        next_dpid = path[i+1]
                        out_port = self.topology_graph[current_dpid][next_dpid]
                    else: # Last switch in the path
                        out_port = dst_port

                    match = current_dp.ofproto_parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP, ipv4_dst=dst_ip)
                    actions = [current_dp.ofproto_parser.OFPActionOutput(out_port)]
                    self.add_flow(current_dp, 1, match, actions)

                # Forward the packet that triggered this process
                # Determine the correct first hop output port
                final_out_port = self.topology_graph[path[0]][path[1]] if len(path) > 1 else dst_port
                actions = [datapath.ofproto_parser.OFPActionOutput(final_out_port)]
                out = datapath.ofproto_parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                                           in_port=in_port, actions=actions, data=msg.data)
                datapath.send_msg(out)
