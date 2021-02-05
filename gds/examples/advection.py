''' Advection of scalar fields '''

import networkx as nx
import numpy as np
import colorcet as cc
import pdb 

import gds

def advection(G, v_field):
	flow_diff = np.zeros(len(G.edges()))
	flow = gds.edge_gds(G)
	flow.set_evolution(dydt=lambda t, y: flow_diff)
	flow.set_initial(y0 = v_field)
	conc = gds.node_gds(G)
	conc.set_evolution(dydt=lambda t, y: -conc.advect(flow))
	return conc, flow

def advection_on_grid():
	n = 5
	G = gds.square_lattice(n, n)
	def v_field(e):
		if e[1][0] >= e[0][0] and e[1][1] >= e[0][1]:
			return 1
		else:
			return -1
	conc, flow = advection(G, v_field)
	conc.set_initial(y0 = lambda x: 1.0 if x == (0, 0) else 0.) # delta initial condition
	return conc, flow

def advection_on_triangles():
	m, n = 20, 20
	G = gds.triangular_lattice(m, n*2)
	def v_field(e):
		if e[1][0] > e[0][0] and e[0][1] == e[1][1]:
			return 1.
		return 0.
	conc, flow = advection(G, v_field)
	conc.set_initial(y0 = lambda x: np.exp(-((x[0]-2)**2 + (x[1]-n/2)**2)/15)) 
	return conc, flow

def advection_on_random_graph():
	m, n = 20, 20
	G = nx.random_geometric_graph(100, 0.225)
	def v_field(e):
		return np.random.choice([-1., 1.])
	conc, flow = advection(G, v_field)
	conc.set_initial(y0 = lambda x: 1.) 
	return conc, flow

def advection_on_circle():
	n = 10
	G = nx.Graph()
	G.add_nodes_from(list(range(n)))
	G.add_edges_from(list(zip(range(n), [n-1] + list(range(n-1)))))
	def v_field(e):
		if e == (n-1, 0) or e == (0, n-1):
			return -1.0
		return 1.0
	conc, flow = advection(G, v_field)
	conc.set_initial(y0 = lambda x: 1.0 if x == 0 else 0.) # delta initial condition
	return conc, flow

def advection_on_torus():
	n = 20
	G = grid_graph(n, n, periodic=True)
	def v_field(e: Edge):
		if e[0][1] == e[1][1]:
			if e[0][0] > e[1][0] or e[1][0] == (e[0][0] - n - 1):
				return 1
			else:
				return -1
		else:
			return 0
	flow_diff = np.zeros(len(G.edges()))
	flow = edge_gds(G, lambda t, self: flow_diff)
	flow.set_initial(y0 = v_field)
	conc = node_gds(G, f = lambda t, self: self.advect(v_field))
	conc.set_initial(y0 = lambda x: 1.0 if x == (10, 10) else None) # delta initial condition
	return couple(conc, flow)

def test():
	G = nx.Graph()
	G.add_nodes_from([1, 2, 3, 4, 5])
	edges = [(1, 2), (3, 2), (4, 3), (5, 4), (1, 5), (1, 3)]
	G.add_edges_from(edges)
	v_field = lambda e: 1.0 if e in edges else -1.0
	conc, flow = advection(G, v_field)
	pdb.set_trace()
	return conc, flow

def vector_advection_circle():
	n = 10
	G = nx.Graph()
	G.add_nodes_from(list(range(n)))
	G.add_edges_from(list(zip(range(n), [n-1] + list(range(n-1)))))
	flow = gds.edge_gds(G)
	flow.set_evolution(dydt=lambda t, y: -flow.advect())
	# flow.set_initial(y0=dict_fun({(2,3): 1.0, (3,4): 1.0}, def_val=0.))
	flow.set_initial(y0=lambda e: 1.0 if e == (2, 3) else 0.1)
	# flow.set_constraints(dirichlet=dict_fun({(2,3): 1.0}))
	return flow

if __name__ == '__main__':
	''' Scalar field advection ''' 

	# conc, flow = advection_on_triangles()
	# sys = gds.couple({
	# 	'conc': conc,
	# 	'flow': flow,
	# })
	# gds.render(sys, canvas=[[[[conc, flow]]]], dynamic_ranges=True, colorbars=False, plot_height=600, node_size=.05, y_rng=(-1.1,0.8), title='Advection of a Gaussian concentration')

	conc, flow = advection_on_random_graph()
	sys = gds.couple({
		'conc': conc,
		'flow': flow,
	})
	gds.render(sys, canvas=[[[[conc, flow]]]], node_rng=(0.5, 1.5), colorbars=False, plot_height=600, node_size=.05, y_rng=(-1.1,1.1), title='Absorbing points of an initially uniform mass')


	''' Vector field advection ''' 

	# flow = vector_advection_circle()
	# gds.render(flow, dynamic_ranges=True)
