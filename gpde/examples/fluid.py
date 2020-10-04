import networkx as nx
import numpy as np
import pdb
from itertools import count
import colorcet as cc

from gpde import *
from gpde.utils import set_seed
from gpde.render.bokeh import *

''' Definitions ''' 

def incompressible_flow(G: nx.Graph, viscosity=1.0, density=1.0) -> (vertex_pde, edge_pde):
	velocity = edge_pde(G, dydt=lambda t, self: None)
	pressure = vertex_pde(G, 
		lhs=lambda t, self: -self.gradient.T@velocity.advect_self() + self.laplacian()/density,
		gtol=1e-8
	)
	velocity.dydt_fun = lambda t, self: -self.advect_self() - pressure.grad()/density + viscosity*self.laplacian()/density
	return pressure, velocity

def compressible_flow(G: nx.Graph, viscosity=1.0) -> (vertex_pde, edge_pde):
	pass

''' Systems ''' 

def fluid_on_grid():
	G = nx.grid_2d_graph(9, 8)
	pressure, velocity = incompressible_flow(G)
	def pressure_values(t, x):
		if x == (2,2):
			return 1.0
		if x == (6,5):
			return -1.0
		return None
	pressure.set_boundary(dirichlet=pressure_values, dynamic=False)
	return pressure, velocity

def fluid_on_circle():
	n = 10
	G = nx.Graph()
	G.add_nodes_from(list(range(n)))
	G.add_edges_from(list(zip(range(n), [n-1] + list(range(n-1)))))
	pressure, velocity = incompressible_flow(G)
	def pressure_values(t, x):
		if x == 0:
			return 1.0
		if x == n-1:
			return -1.0
		return None
	pressure.set_boundary(dirichlet=pressure_values, dynamic=False)
	return pressure, velocity

def differential_inlets():
	G = nx.Graph()
	G.add_nodes_from([1,2,3,4,5,6])
	G.add_edges_from([(1,2),(2,3),(4,3),(2,5),(3,5),(5,6)])
	pressure, velocity = incompressible_flow(G)
	def pressure_values(t, x):
		if x == 1: return 0.2
		if x == 4: return 0.1
		if x == 6: return -0.3
		return None
	pressure.set_boundary(neumann=pressure_values, dynamic=False)
	return pressure, velocity

def poiseuille():
	m, n = 10, 20
	G = nx.grid_2d_graph(n, m)
	pressure, velocity = incompressible_flow(G)
	def pressure_values(t, x):
		if x[0] == 0: return 1.0
		if x[0] == n-1: return -1.0
		return None
	pressure.set_boundary(dirichlet=pressure_values, dynamic=False)
	def no_slip(t, x):
		if x[0][1] == x[1][1] == 0 or x[0][1] == x[1][1] == m-1:
			return 0.
		return None
	velocity.set_boundary(dirichlet=no_slip, dynamic=False)
	return pressure, velocity

def fluid_on_sphere():
	pass

def von_karman():
	w, h = 20, 10
	G = nx.grid_2d_graph(w, h)
	obstacle = [ # Introduce occlusion
		(6, 4), (6, 5), 
		(7, 4), (7, 5), 
		(8, 4),
	]
	G.remove_nodes_from(obstacle)
	pressure, velocity = incompressible_flow(G)
	def pressure_values(t, x):
		if x[0] == 0: return 1.0
		if x[0] == w-1: return -1.0
		return None
	pressure.set_boundary(dirichlet=pressure_values, dynamic=False)
	return pressure, velocity

def random_graph():
	set_seed(1001)
	n = 30
	eps = 0.3
	G = nx.random_geometric_graph(n, eps)
	pressure, velocity = incompressible_flow(G)
	def pressure_values(t, x):
		if x == 4: return 1.0
		elif x == 21: return -1.0 
		return None
	pressure.set_boundary(dirichlet=pressure_values, dynamic=False)
	return pressure, velocity

''' Experimentation / observation ''' 

class TurbulenceObservable(Observable):
	def __init__(self, velocity: edge_pde):
		self.velocity = velocity
		self.metrics = {
			'n': 0,
			'v_mu': 0.,
			'v_M2': 0.,
			'v_sigma': 0,
		}
		# Warning: do not allow rendered metrics to be None, or Bokeh won't render it
		self.rendered = ['v_sigma',]
		self.cycle_indices = {}
		self.cycle_signs = {}
		for cycle in nx.cycle_basis(velocity.G):
			n = len(cycle)
			id = f'{n}-cycle flow'
			self.metrics[id] = 0.
			G_cyc = nx.Graph()
			nx.add_cycle(G_cyc, cycle)
			cyc_orient = {}
			for i in range(n):
				if i == n-1:
					cyc_orient[(cycle[i], cycle[0])] = 1
					cyc_orient[(cycle[0], cycle[i])] = -1
				else:
					cyc_orient[(cycle[i], cycle[i+1])] = 1
					cyc_orient[(cycle[i+1], cycle[i])] = -1
			indices = [velocity.edges[e] for e in G_cyc.edges()]
			signs = np.array([velocity.orientation[e]*cyc_orient[e] for e in G_cyc.edges()])
			if id in self.cycle_indices:
				self.cycle_indices[id].append(indices)
				self.cycle_signs[id].append(signs)
			else:
				self.cycle_indices[id] = [indices]
				self.cycle_signs[id] = [signs]
		self.rendered += list(self.cycle_indices.keys())
		super().__init__({})

	def observe(self):
		y = self.velocity.y
		if self['n'] == 0:
			self['v_mu'] = y
			self['v_M2'] = np.zeros_like(y)
			self['v_sigma'] = 0.
		else:
			n = self['n'] + 1
			new_mu = self['v_mu'] + (y - self['v_mu']) / n
			self['v_M2'] += (y - self['v_mu']) * (y - new_mu)
			self['v_sigma'] = np.sqrt((self['v_M2'] / n).sum())
			self['v_mu'] = new_mu
		self['n'] += 1
		for id, cycles in self.cycle_indices.items():
			self[id] = sum([(y[cyc] ** 2).sum() for cyc in cycles])
		return self.y

	def __getitem__(self, idx):
		return self.metrics.__getitem__(idx)

	def __setitem__(self, idx, val):
		return self.metrics.__setitem__(idx, val)

	@property 
	def t(self):
		return self.velocity.t

	@property
	def y(self):
		ret = {k: [self.metrics[k]] for k in self.rendered}
		ret['t'] = [self.t]
		return ret
	
from bokeh.plotting import figure
from bokeh.models import ColumnDataSource
from bokeh.layouts import column
import colorcet as cc

class FluidRenderer(Renderer):
	def __init__(self, pressure: vertex_pde, velocity: edge_pde, **kwargs):
		self.pressure = pressure
		self.velocity = velocity
		self.turbulence = TurbulenceObservable(velocity)
		sys = couple(pressure, velocity)
		super().__init__(sys, **kwargs)

	def setup_canvas(self):
		return [
			[[[self.pressure, self.velocity]], [[self.turbulence]]]
		]

	def create_plot(self, items: List[Observable]):
		if len(items) == 1 and items[0] is self.turbulence:
			cats = list(self.turbulence.rendered)
			src = ColumnDataSource({cat: [] for cat in ['t'] + cats})
			plots = []
			for i, cat in enumerate(cats):
				plot = figure(title=cat, tooltips=[(cat, '@'+cat)])
				if i == 0:
					plot.toolbar_location = 'above'
					plot.x_range.follow = 'end'
					plot.x_range.follow_interval = 10.0
					plot.x_range.range_padding = 0
				else:
					plot.toolbar_location = None
					plot.x_range = plots[0].x_range
				plot.line('t', cat, line_color='black', source=src)
				# plot.varea(x='t', y1=0, y2=cat, fill_color=cc.glasbey[i], alpha=0.6, source=src)
				plots.append(plot)
			self.turbulence.src = src
			return column(plots, sizing_mode='stretch_both')
		else:
			return super().create_plot(items)

	def draw(self):
		self.turbulence.src.stream(self.turbulence.observe(), 200)
		super().draw()

if __name__ == '__main__':
	# p, v = poiseuille()
	# d = v.project(GraphDomain.vertices, lambda v: v.div())
	# pv = couple(p, v)
	# sys = System(pv, [p, v, d], ['pressure', 'velocity', 'div_velocity'])
	# sys.solve_to_disk(10., 1e-3, 'poiseuille')

	sys = System.from_disk('poiseuille')
	p, v, d = sys.observables['pressure'], sys.observables['velocity'], sys.observables['div_velocity']

	renderer = LiveRenderer(sys, [[[[p, v]], [[d]]]], node_palette=cc.rainbow, node_rng=(-1,1), edge_max=0.3, n_spring_iters=2000, node_size=0.06)
	renderer.start()
