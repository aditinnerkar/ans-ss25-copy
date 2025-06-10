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

# Class for an edge in the graph
class Edge:
	def __init__(self):
		self.lnode = None
		self.rnode = None
	
	def remove(self):
		self.lnode.edges.remove(self)
		self.rnode.edges.remove(self)
		self.lnode = None
		self.rnode = None

# Class for a node in the graph
class Node:
	def __init__(self, id, type):
		self.edges = []
		self.id = id
		self.type = type

	# Add an edge connected to another node
	def add_edge(self, node):
		edge = Edge()
		edge.lnode = self
		edge.rnode = node
		self.edges.append(edge)
		node.edges.append(edge)
		return edge

	# Remove an edge from the node
	def remove_edge(self, edge):
		self.edges.remove(edge)

	# Decide if another node is a neighbor
	def is_neighbor(self, node):
		for edge in self.edges:
			if edge.lnode == node or edge.rnode == node:
				return True
		return False

class HostNode(Node):
    """
    A specialized Node for hosts to store pod, switch, and ID info
    """
    def __init__(self, id, type, pod, sw, hid):
        super().__init__(id, type)
        self.pod = pod
        self.sw = sw
        self.hid = hid

class Fattree:
    """
    This class generates the fat-tree topology graph
    """
    def __init__(self, num_ports):
        self.servers = []
        self.switches = []
        self.generate(num_ports)

    def generate(self, num_ports):
        """
        Generates the fat-tree topology
        k = num_ports
        """
        k = num_ports
        if k % 2 != 0:
            raise ValueError("Number of ports (k) must be an even number.")

        num_pods = k
        num_core_switches = (k // 2) ** 2
        switches_per_pod = k
        num_agg_switches = num_edge_switches = k // 2
        hosts_per_edge_switch = k // 2
        
        # To keep track of device IDs
        core_id_start = 0
        agg_id_start = num_core_switches
        edge_id_start = agg_id_start + (num_pods * num_agg_switches)
        host_id_start = 0

        # Create Core Switches
        core_switches = []
        for i in range(num_core_switches):
            core_sw = Node(id=core_id_start + i, type='core')
            core_switches.append(core_sw)
        self.switches.extend(core_switches)

        # Create Pods (Aggregation, Edge, Hosts)
        for p in range(num_pods):
            agg_switches_in_pod = []
            edge_switches_in_pod = []

            # Create Aggregation and Edge switches for the pod
            for i in range(num_agg_switches):
                # Aggregation Switches
                agg_sw_id = agg_id_start + (p * num_agg_switches) + i
                agg_sw = Node(id=agg_sw_id, type='aggregation')
                agg_switches_in_pod.append(agg_sw)

                # Edge Switches
                edge_sw_id = edge_id_start + (p * num_edge_switches) + i
                edge_sw = Node(id=edge_sw_id, type='edge')
                edge_switches_in_pod.append(edge_sw)
            
            self.switches.extend(agg_switches_in_pod)
            self.switches.extend(edge_switches_in_pod)
            
            # Link Edge switches to Hosts
            for i, edge_sw in enumerate(edge_switches_in_pod):
                for j in range(hosts_per_edge_switch):
                    host_id = host_id_start
                    host_id_start += 1
                    # IP scheme: 10.pod.switch.id (e.g., 10.0.0.2)
                    host = HostNode(id=host_id, type='host', pod=p, sw=i, hid=j + 2)
                    self.servers.append(host)
                    host.add_edge(edge_sw)
            
            # Link Edge switches to Aggregation switches in the same pod
            for agg_sw in agg_switches_in_pod:
                for edge_sw in edge_switches_in_pod:
                    agg_sw.add_edge(edge_sw)

            # Link Aggregation switches to Core switches
            for i, agg_sw in enumerate(agg_switches_in_pod):
                for j in range(num_core_switches // num_agg_switches):
                    core_sw_index = i * (k // 2) + j
                    agg_sw.add_edge(core_switches[core_sw_index])
