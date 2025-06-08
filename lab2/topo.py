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


class Fattree:
	"""
	Fat-tree topology is defined using a single parameter k, which determines the number of pods, number of
	hosts, switches and links
	"""

	def __init__(self, num_ports):
		self.servers = []
		self.switches = []
		self.generate(num_ports)


		
  
	def generate(self, num_ports):
     
		# ToDo: code for generating the fat-tree topology
		self.num_ports = num_ports
		num_pods = num_ports
		num_core_switches = (num_ports // 2)**2
		num_agg_switches_per_pod = num_ports // 2
		num_edge_switches_per_pod = num_ports // 2
		num_hosts_per_edge_switch = num_ports // 2
		
		node_id_counter = 0
		core_switches = []
		agg_switches_by_pod = []
		edge_switches_by_pod = []

		# 1. Create Core Switches
		for i in range(num_core_switches):
			node_id_counter += 1
			switch = Node(node_id_counter, 'core')
			core_switches.append(switch)
			self.switches.append(switch)

		# 2. Create Pods (Aggregation, Edge, Hosts)
		for p in range(num_pods):
			pod_agg_switches = []
			pod_edge_switches = []
			
			for s in range(num_agg_switches_per_pod):
				node_id_counter += 1
				switch = Node(node_id_counter, 'agg')
				switch.pod = p
				# Store logical switch index within the pod's aggregation layer
				switch.sw = s
				pod_agg_switches.append(switch)
				self.switches.append(switch)
			
			for s in range(num_edge_switches_per_pod):
				node_id_counter += 1
				switch = Node(node_id_counter, 'edge')
				switch.pod = p
				# Store logical switch index within the pod's edge layer
				switch.sw = s
				pod_edge_switches.append(switch)
				self.switches.append(switch)

				# 3. Create Hosts and connect to Edge switches
				for h in range(num_hosts_per_edge_switch):
					node_id_counter += 1
					host = Node(node_id_counter, 'server')
					host.pod = p
					host.sw = s # Edge switch logical index
					# Per paper, host IDs are 2 to k/2+1
					host.hid = h + 2
					self.servers.append(host)
					# Connect host to its edge switch
					switch.add_edge(host)
			
			agg_switches_by_pod.append(pod_agg_switches)
			edge_switches_by_pod.append(pod_edge_switches)

		# 4. Connect Edge switches to Aggregation switches (within a pod)
		for p in range(num_pods):
			for edge_switch in edge_switches_by_pod[p]:
				for agg_switch in agg_switches_by_pod[p]:
					edge_switch.add_edge(agg_switch)

		# 5. Connect Aggregation switches to Core switches
		for p in range(num_pods):
			for s in range(num_agg_switches_per_pod):
				agg_switch = agg_switches_by_pod[p][s]
				for port in range(num_agg_switches_per_pod):
					core_switch_index = s * (num_ports // 2) + port
					core_switch = core_switches[core_switch_index]
					agg_switch.add_edge(core_switch)

