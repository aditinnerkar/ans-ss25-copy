#!/usr/bin/env python3

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ipv4, arp, ether_types
from ryu.topology import event, switches
from ryu.topology.api import get_switch, get_link
from ryu.lib import hub # Import hub for greenlet-aware threading primitives

import topo

class SPRouter(app_manager.RyuApp):
    """
    A Ryu controller application that implements shortest-path routing
    on a fat-tree topology with fixes for stability and intra-switch routing.
    """
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(SPRouter, self).__init__(*args, **kwargs)
        # Adjacency list for the switch topology: {dpid: {neighbor_dpid: port_no}}
        self.topology_graph = {}
        # Discovered host locations: {host_ip: (dpid, port_no)}
        self.hosts = {}
        # Use a Semaphore as a lock to prevent race conditions
        self.topology_lock = hub.Semaphore(1)
        self.logger.info("Shortest Path Router Application Initialized")

    @set_ev_cls(event.EventSwitchEnter, [MAIN_DISPATCHER, CONFIG_DISPATCHER])
    def get_topology_data(self, ev):
        """
        Event handler for when switches enter the network.
        This function discovers the switch and link topology and builds a graph.
        It is now protected by a lock to prevent race conditions.
        """
        self.logger.info("Switch event detected, attempting to rebuild topology graph...")

        # Acquire the lock to ensure safe modification of the graph
        with self.topology_lock:
            self.logger.info("Lock acquired, rebuilding topology.")
            # Get the list of all switches and links from Ryu's topology API
            switch_list = get_switch(self, None)
            link_list = get_link(self, None)

            # Clear the old graph and rebuild it
            self.topology_graph.clear()
            for sw in switch_list:
                dpid = sw.dp.id
                self.topology_graph[dpid] = {}

            # For each link, add an entry to the adjacency list for both directions
            for link in link_list:
                src_dpid = link.src.dpid
                src_port = link.src.port_no
                dst_dpid = link.dst.dpid
                dst_port = link.dst.port_no
                
                # Since links are bidirectional, we add entries for both source and destination
                if src_dpid in self.topology_graph and dst_dpid in self.topology_graph[src_dpid]:
                    continue
                if dst_dpid in self.topology_graph and src_dpid in self.topology_graph[dst_dpid]:
                    continue

                self.topology_graph.setdefault(src_dpid, {})[dst_dpid] = src_port
                self.topology_graph.setdefault(dst_dpid, {})[src_dpid] = dst_port


        self.logger.info("Topology graph successfully built: %s", self.topology_graph)

    def add_flow(self, datapath, priority, match, actions):
        """
        A helper function to add a flow entry to a switch's flow table.
        """
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # Construct the flow modification message
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
                                match=match, instructions=inst)
        datapath.send_msg(mod)

    def get_path(self, src, dst):
        """
        Calculates the shortest path between two switches using Dijkstra's algorithm.
        The graph is unweighted, so we are finding the path with the fewest hops.
        """
        import heapq
        
        if src not in self.topology_graph or dst not in self.topology_graph:
            return []

        distance = {node: float('inf') for node in self.topology_graph}
        previous = {node: None for node in self.topology_graph}
        distance[src] = 0
        pq = [(0, src)] 

        while pq:
            dist, current_node = heapq.heappop(pq)
            if current_node == dst:
                break
            if dist > distance[current_node]:
                continue
            for neighbor in self.topology_graph.get(current_node, {}):
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
        return path if path and path[0] == src else []

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        """
        Initial handler for a switch connection. Installs a low-priority
        "table-miss" flow entry that sends any unmatched packets to the controller.
        """
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)
        self.logger.info("Installed table-miss flow entry on switch %s", datapath.id)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        """
        The main packet handling logic. This is called when a packet arrives
        at the controller due to the table-miss entry.
        """
        msg = ev.msg
        datapath = msg.datapath
        dpid = datapath.id
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)

        if eth.ethertype == ether_types.ETH_TYPE_ARP:
            arp_pkt = pkt.get_protocol(arp.arp)
            src_ip = arp_pkt.src_ip
            if src_ip not in self.hosts:
                self.hosts[src_ip] = (dpid, in_port)
                self.logger.info("Discovered host %s at switch %s, port %s", src_ip, dpid, in_port)
            
            actions = [parser.OFPActionOutput(ofproto.OFPP_FLOOD)]
            out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                      in_port=in_port, actions=actions, data=msg.data)
            datapath.send_msg(out)
            return

        if eth.ethertype == ether_types.ETH_TYPE_IP:
            ip_pkt = pkt.get_protocol(ipv4.ipv4)
            dst_ip = ip_pkt.dst
            src_ip = ip_pkt.src

            if src_ip not in self.hosts:
                self.hosts[src_ip] = (dpid, in_port)
                self.logger.info("Discovered host %s at switch %s, port %s", src_ip, dpid, in_port)
            
            if dst_ip not in self.hosts:
                self.logger.warning("Destination host %s unknown. Dropping packet.", dst_ip)
                return

            dst_dpid, dst_port = self.hosts[dst_ip]

            out_port = None
            # Acquire lock to safely read the graph
            with self.topology_lock:
                # Case 1: Source and Destination hosts are on the SAME switch
                if dpid == dst_dpid:
                    self.logger.info("Source and Destination on same switch %s. Routing to host port.", dpid)
                    out_port = dst_port
                # Case 2: Source and Destination hosts are on DIFFERENT switches
                else:
                    self.logger.info("Source and Destination on different switches. Calculating path.")
                    path = self.get_path(dpid, dst_dpid)
                    if not path or len(path) < 2:
                        self.logger.warning("No path found from %s to %s", dpid, dst_dpid)
                        return
                    next_hop_dpid = path[1]
                    out_port = self.topology_graph[dpid][next_hop_dpid]
            
            if out_port is not None:
                # Install Flow Rule and Forward Packet
                match = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP, ipv4_dst=dst_ip)
                actions = [parser.OFPActionOutput(out_port)]
                self.add_flow(datapath, 1, match, actions)
                self.logger.info("Installing flow on switch %s: IP dst %s -> port %s", dpid, dst_ip, out_port)

                out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                          in_port=in_port, actions=actions, data=msg.data)
                datapath.send_msg(out)
