''' Graph utilities ''' 
import networkx as nx
import numpy as np
import pdb
import matplotlib.pyplot as plt

''' Graph generators ''' 

def grid_graph_layout(G: nx.Graph):
	m, n = 0, 0
	nodes = set(G.nodes())
	for node in nodes:
		n = max(node[0], n)
		m = max(node[1], m)
	m += 1
	n += 1
	layout = dict()
	dh = 1/max(m, n)
	x0 = -n/max(m, n)
	y0 = -m/max(m, n)
	for i in range(n):
		for j in range(m):
			if (i, j) in nodes:
				layout[(i, j)] = np.array([2*i*dh + x0, 2*j*dh + y0])
	return layout

def square_lattice(m: int, n: int, diagonals=False, with_boundaries=False, **kwargs) -> nx.Graph:
	G = nx.grid_2d_graph(n, m, **kwargs)
	if diagonals:
		for i in range(n-1):
			for j in range(m-1):
				G.add_edges_from([((i, j), (i+1, j+1)), ((i, j+1), (i+1, j))])
	pos = grid_graph_layout(G)
	nx.set_node_attributes(G, pos, 'pos')
	if with_boundaries:
		l = G.subgraph([(0, i) for i in range(m)])
		r = G.subgraph([(n-1, i) for i in range(m)])
		t = G.subgraph([(j, m-1) for j in range(n)])
		b = G.subgraph([(j, 0) for j in range(n)])
		return G, (l, r, t, b)
	else:
		return G

def lattice45(m: int, n: int) -> nx.Graph:
	''' Creates 45-degree rotated square lattice; make n odd for symmetric boundaries '''
	G = nx.Graph()
	layout = dict()
	dy = 2/(m-1)
	dx = 2/(n-1)
	for i in range(n):
		if i % 2 == 0:
			for j in range(m-1):
				G.add_node((i, j))
				layout[(i, j)] = np.array([-1+i*dx, -1+dy/2+j*dy])
				if i > 0:
					G.add_edges_from([((i-1, j), (i, j)), ((i-1, j+1), (i, j))])
		else:
			for j in range(m):
				G.add_node((i, j))
				layout[(i, j)] = np.array([-1+i*dx, -1+j*dy])
				if j > 0:
					G.add_edges_from([((i-1, j-1), (i, j-1)), ((i-1, j-1), (i, j))])
	nx.set_node_attributes(G, layout, 'pos')
	return G

def triangular_lattice(m, n, with_boundaries=False, **kwargs) -> nx.Graph:
	''' Sanitize networkx properties for Bokeh consumption ''' 
	if 'periodic' in kwargs:
		kwargs['with_positions'] = False
		G = nx.triangular_lattice_graph(m, n, **kwargs)
		nx.set_node_attributes(G, None, 'contraction')
		return G
	else:
		G = nx.triangular_lattice_graph(m, n, **kwargs)
		if with_boundaries:
			l = G.subgraph([(0, i) for i in range(m+1)])
			r_nodes = [(n//2, 2*i+1) for i in range(m//2+1)]
			if n % 2 == 1:
				r_nodes += [(n//2+1, i) for i in range(m+1)]
			else:
				r_nodes += [(n//2, 2*i) for i in range(m//2+1)]
			r = G.subgraph([x for x in r_nodes if x in G.nodes])
			t = G.subgraph([(j, m) for j in range(n)])
			b = G.subgraph([(j, 0) for j in range(n)])
			return G, (l.copy(), r.copy(), t.copy(), b.copy())
		else:
			return G

def hexagonal_lattice(*args, **kwargs) -> nx.Graph:
	''' Sanitize networkx properties for Bokeh consumption ''' 
	if 'periodic' in kwargs:
		kwargs['with_positions'] = False
		G = nx.hexagonal_lattice_graph(*args, **kwargs)
		nx.set_node_attributes(G, None, 'contraction')
		return G
	else:
		return nx.triangular_lattice_graph(*args, **kwargs)


def get_planar_boundary(G: nx.Graph) -> (nx.Graph, nx.Graph, nx.Graph, nx.Graph, nx.Graph):
	''' Get boundary of planar graph using layout coordinates. ''' 
	nodes = set(G.nodes())
	edges = set(G.edges())
	pos = nx.get_node_attributes(G, 'pos')
	xrng, yrng = list(set([pos[n][0] for n in nodes])), list(set([pos[n][1] for n in nodes]))
	xmin = dict(zip(yrng, [min([pos[n][0] for n in nodes if pos[n][1]==y]) for y in yrng]))
	ymin = dict(zip(xrng, [min([pos[n][1] for n in nodes if pos[n][0]==x]) for x in xrng]))
	xmax = dict(zip(yrng, [max([pos[n][0] for n in nodes if pos[n][1]==y]) for y in yrng]))
	ymax = dict(zip(xrng, [max([pos[n][1] for n in nodes if pos[n][0]==x]) for x in xrng]))
	dG, dG_L, dG_R, dG_T, dG_B = nx.Graph(), nx.Graph(), nx.Graph(), nx.Graph(), nx.Graph()
	for n in nodes:
		x, y = pos[n]
		if x == xmin[y]:
			dG_L.add_node(n)
			dG.add_node(n)
		if x == xmax[y]:
			dG_R.add_node(n)
			dG.add_node(n)
		if y == ymin[x]:
			dG_B.add_node(n)
			dG.add_node(n)
		if y == ymax[x]:
			dG_T.add_node(n)
			dG.add_node(n)
	for _dG in (dG, dG_L, dG_R, dG_T, dG_B):
		for n in _dG.nodes():
			for m in _dG.nodes():
				# Preserve implicit orientation
				if (n, m) in edges:
					_dG.add_edge(n, m)
				elif (m, n) in edges:
					_dG.add_edge(m, n)
	return (dG, dG_L, dG_R, dG_T, dG_B)

def clear_attributes(G):
	ns = list(G.nodes(data=True))
	es = list(G.edges(data=True))
	if len(ns) > 0:
		n = ns[0]
		for attr in n[-1].keys():
			nx.set_node_attributes(G, None, attr)
	if len(es) > 0:
		e = es[0]
		for attr in e[-1].keys():
			nx.set_node_attributes(G, None, attr)
	return G

if __name__ == '__main__':
	# G = lattice45(4, 6)
	G = square_lattice(10, 10)
	G_ = nx.line_graph(G)
	G__ = nx.line_graph(G_)

	plt.figure()
	nx.draw_spectral(G)
	plt.figure()
	nx.draw_spectral(G_)
	plt.figure()
	nx.draw_spectral(G__)

	plt.show()