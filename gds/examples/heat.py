''' Heat equation ''' 

import numpy as np
import networkx as nx
import pdb

from gpde import *
from gpde.render.bokeh import *

def heat_grid(n = 10, steady_state=False) -> vertex_pde:
	G = nx.grid_2d_graph(n, n)
	if steady_state:
		''' Steady-state version (for comparison) ''' 
		return vertex_pde(G, lhs=lambda self, t, y: self.laplacian(y))
	else:
		return vertex_pde(G, dydt=lambda t, self: self.laplacian())

def grid_const_boundary(steady_state=False) -> vertex_pde:
	n = 7
	temperature = heat_grid(n=n, steady_state=steady_state)
	temperature.set_boundary(dirichlet = lambda x: 1.0 if (0 in x or (n-1) in x) else None)
	return temperature

def grid_mixed_boundary(steady_state=False) -> vertex_pde:
	n = 10
	temperature = heat_grid(n=n, steady_state=steady_state)
	def dirichlet(t, x):
		if x[0] == 0 or x[0] == n-1:
			return 0.5
		elif x[1] == 0:
			return 1.0
		return None
	def neumann(t, x):
		if x[1] == n-1 and x[0] not in (0, n-1):
			return -0.1
		return None
	temperature.set_boundary(dirichlet=dirichlet, neumann=neumann)
	return temperature

def grid_timevarying_boundary(steady_state=False) -> vertex_pde:
	n = 10
	temperature = heat_grid(n=n, steady_state=steady_state)
	temperature.set_boundary(
		dirichlet = lambda t, x: np.sin(t/5)**2 if (0 in x or (n-1) in x) else None
	)
	return temperature

def grid_linear(steady_state=False) -> vertex_pde:
	n = 10
	temperature = heat_grid(n=n, steady_state=steady_state)
	def dirichlet(x):
		if x[0] == 0:
			return 1.0
		elif x[0] == n-1:
			return 0.
		return None
	temperature.set_boundary(dirichlet=dirichlet)
	return temperature

if __name__ == '__main__':
	# Use coupling to visualize multiple PDEs simultaneously
	p1 = grid_linear()
	p2 = grid_linear(steady_state=True)
	sys = System(couple(p1, p2), {
		'heat1': p1,
		'heat2': p2
	})
	LiveRenderer(sys, grid_canvas([p1, p2])).start()