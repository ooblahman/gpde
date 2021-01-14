import numpy as np
from typing import Any, Union, Tuple, Callable, NewType, Iterable, Dict
from scipy.integrate import DOP853, LSODA
from abc import ABC, abstractmethod
import pdb
from enum import Enum
import cvxpy as cp

from .types import *
from .utils import *
from .system import *

''' Base class: dynamical system on arbitrary finite domain ''' 

class fds(Observable, Steppable):
	def __init__(self, X: Domain):
		''' 
		Finite-space dynamical system.
		''' 
		Observable.__init__(self, X)
		Steppable.__init__(self, IterationMode.none)

	''' Dynamics ''' 

	def set_evolution(self,
			dydt: Callable[[Time, np.ndarray], np.ndarray]=None, order: int=1, max_step: float=1e-3, solver_args: Dict={},
			cost: Callable[[Time, np.ndarray], np.ndarray]=None, 
			map_fun: Callable[[Time, np.ndarray], np.ndarray]=None, dt: float=1.0,
		): 
		''' Define evolution law for the dynamics.

		Option 1: As a PDE
			dydt: Callable[Time]
				RHS of differential equation [uses LSODA for stiffness detection; falls back to DOP853 if not available]
			order: int
				[optional] Order of time-difference; if greater than one, automatically creates (order*ndim) state vector
			max_step: float
				[optional] Maximum allowed step size in the solver; default 1e-3
			solver_args: Dict
				[optional] Additional arguments to be passed to the solver

		Option 2: As a convex program
			cost: Callable[time]
				RHS of a disciplined-convex cost function (either array-like or scalar)
			solver_args: Dict
				[optional] Additional arguments to be passed to the solver

		Option 3: As a recurrence relation
			map_fun: Callable[time]
				RHS of recurrence relation
			dt: float
				[default 1.0] time delta for stepping 
		'''
		assert oneof([dydt != None, cost != None, fun != None]), 'Exactly one evolution law must be specified'
		self.t0 = 0.
		if dydt != None:
			self.iter_mode = IterationMode.dydt
			self.dydt_fun = dydt
			self.max_step = max_step
			self.order = order
			self.solver_args = self.solver_args
			self.y0 = np.zeros(self.ndim*order)
			try:
				self.integrator = LSODA(self.dydt, self.t0, self.y0, np.inf, max_step=max_step, **solver_args)
			except:
				print('Failed to use LSODA, falling back to DOP853')
				self.integrator = DOP853(lambda t, y: y0, self.t0, self.y0, np.inf, max_step=max_step, **solver_args)
				self.integrator.fun = self.dydt

		elif cost != None:
			self.iter_mode = IterationMode.cvx
			self.cost_fun = cost
			self.solver_args = self.solver_args
			self.y0 = np.zeros(self.ndim)
			self._t = self.t0
			self._y = self.y0.copy()
			self._t_prb = cp.Parameter(nonneg=True)
			self._y_prb = cp.Variable(self._y.size)
			_cost = cost(self._t_prb, self._y_prb)
			if _cost.shape != (): # Cost is not scalar
				_cost = cp.sum(cp.abs(_cost))
			assert _cost.is_dcp(), 'Problem is not disciplined-convex'
			self._prb = cp.Problem(cp.Minimize(_cost), [])

		elif map_fun != None:
			self.iter_mode = IterationMode.map
			self.map_fun = map_fun
			self.y0 = np.zeros(self.ndim)
			self._t = self.t0
			self._n = int(self._t)
			self._y = self.t0.copy()

	def set_initial(self, 
			t0: float=0., 
			y0: Union[Callable[[Point], float], np.ndarray]=lambda _: 0.,
		):
		''' Set initial conditions. 
			t0: float
				Starting time
			y0: Union[Callable[[Point], float], np.ndarray]
				Function or array of points specifying intial condition.

		TODO: support for higher-order initial conditions in differential equations.
		'''
		assert self.iter_mode != IterationMode.none, 'Use set_evolution() before setting initial conditions'
		if type(y0) is np.ndarray:
			y0 = lambda x: y0[self.X[x]]
		self.t0 = t0
		self.y0_fun = y0

		if self.iter_mode is IterationMode.dydt:
			self.integrator.t = t0
		elif self.iter_mode is IterationMode.cvx:
			self._t = t0
		elif self.iter_mode is IterationMode.map:
			self._t = t0
			self._n = int(t0)

		for x in self.X.keys() - self.X_dirichlet:
			i, y = self.X[x], y0(x)
			self.y0[i] = y

			if self.iter_mode is IterationMode.dydt:
				self.integrator.y[i] = y
			elif self.iter_mode is IterationMode.cvx or self.iter_mode is IterationMode.map:
				self._y[i] = y

	def set_constraints(self, 
			dirichlet: Union[Callable[[Time, Point], float], Callable[[Point], float], Dict[Point, float]]={}, 
			neumann: Union[Callable[[Time, Point], float], Callable[[Point], float], Dict[Point, float]]={},
			project: Callable[[np.ndarray], np.ndarray]=lambda x: x,
		):
		''' Impose constraints. Assumes domain boundaries do not change.

		dirichlet: callable or dictionary
			Impose fixed values at boundary; either a function (t, x) or function (x) or static lookup dictionary
		neumann: callable or dictionary:
			Impose fixed fluxes at boundary; either a function (t, x) or function (x) or static lookup dictionary
		project: callable
			Project solutions onto feasible set.
		''' 
		assert self.iter_mode != IterationMode.none, 'Use set_evolution() before setting boundary conditions'
		if type(dirichlet) is dict:
			dirichlet = dict_fun(dirichlet)
		if type(neumann) is dict:
			neumann = dict_fun(neumann)
		self.dirichlet_fun = dirichlet
		self.neumann_fun = neumann
		self.project_fun = project

		# Store whether we will require recalculation
		self.dynamic_dirichlet = fun_ary(dirichlet) > 1 
		self.dynamic_neumann = fun_ary(neumann) > 1

		def populate(fun: Callable, dynamic: bool) -> Tuple[List, np.ndarray, np.ndarray]:
			if dynamic:
				domain = [x for x in self.X if (fun(0., x) is not None)]
				indices = np.array([self.X[x] for x in domain], dtype=np.intp)
				values = np.array([fun(0., x) for x in domain])
				return domain, indices, values
			else:
				domain = [x for x in self.X if (fun(x) is not None)]
				indices = np.array([self.X[x] for x in domain], dtype=np.intp)
				values = np.array([fun(x) for x in domain])
				return domain, indices, values

		# Store domain, indices, and values
		self.X_dirichlet, self.dirichlet_indices, self.dirichlet_values = populate(dirichlet, self.dynamic_dirichlet)
		self.X_neumann, self.neumann_indices, self.neumann_values = populate(neumann, self.dynamic_neumann)

		# Ensure nonoverlapping conditions
		intersect = set(self.X_dirichlet) & set(self.X_neumann)
		assert len(intersect) == 0, f'Dirichlet and Neumann conditions overlap on {intersect}'

		self.y0 = project(replace(self.y0, self.dirichlet_indices, self.dirichlet_values))

		if self.iter_mode is IterationMode.dydt:
			self.integrator.y[self.dirichlet_indices - self.ndim] = self.dirichlet_values
		elif self.iter_mode is IterationMode.cvx:
			self._y = self.y0.copy()
			self._y_cstr = cp.Parameter(self.dirichlet_values.size)
			self._y_cstr.value = self.dirichlet_values
			constr = [self._y_prb[self.dirichlet_indices] == self.y_cstr]
			self._prb = cp.Problem(self._prb.objective, constr)
		elif self.iter_mode is IterationMode.map:
			self._y = self.y0.copy()

	''' Stepping ''' 

	def reset(self):
		''' Reset the system to initial conditions ''' 
		assert self.iter_mode != IterationMode.none
		if self.iter_mode is IterationMode.dydt:
			self.set_evolution(dydt=self.dydt_fun, order=self.order, max_step=self.max_step, solver_args=self.solver_args)
		elif self.iter_mode is IterationMode.cvx:
			self.set_evolution(cost=self.cost_fun, solver_args=self.solver_args)
		elif self.iter_mode is IterationMode.map:
			self.set_evolution(map_fun=self.map_fun)
		self.set_initial(t0=self.t0, y0=self.y0_fun)

	def step(self, dt: float):
		''' Step the system to t+dt ''' 
		if self.iter_mode is IterationMode.none:
			raise Exception('Evolution law not specified')
		elif self.iter_mode is IterationMode.dydt:
			self.step_dydt(dt)
		elif self.iter_mode is IterationMode.cvx:
			self.step_cvx(dt)
		elif self.iter_mode is IterationMode.map:
			self.step_map(dt)
		else:
			raise Exception(f'Unsupported evolution law: {self.iter_mode}')

	''' Differential stepping ''' 

	def step_dydt(self, dt: float):
		self.integrator.t_bound = self.t + dt
		self.integrator.status = 'running'
		while self.integrator.status != 'finished':
			self.integrator.step()
			self.update_constraints(self.t)
			self.set_constraints()

	def dydt(self, t: Time, y: np.ndarray):
		self.update_constraints(t)
		n, order = self.ndim, self.order
		ret = np.zeros_like(y)
		for i in range(order-1):
			ret[n*i:n*(i+1)] = y[n*(i+1):n*(i+2)]
		diff = self.dydt_fun(t, self)
		diff[self.dirichlet_indices] = 0. # Do not modify constrained nodes
		ret[n*(order-1):] = diff
		return ret

	''' Convex stepping ''' 

	def step_cvx(self, dt: float):
		# Update boundary conditions
		self._t += dt
		self._t_prb.value = self.t
		self.update_constraints(self.t)
		self._y_prb.value = self.y
		self._prb.solve(warm_start=True)
		assert self._prb.status == 'optimal', f'CVXPY solve unsuccessful, status is: {self._prb.status}'
		self._y = self._prb.value
		self.set_constraints()

	''' Discrete stepping ''' 

	def step_map(self, dt: float):
		self._t += dt
		if (self._t - self._n) >= 1.0:
			self._n += 1
			self.update_constraints(self.t)
			self._y = self.map_fun(self.y) 
			self.set_constraints()
			self._y[self.dirichlet_indices] = self.dirichlet_values

	''' Constaint setting '''

	def update_constraints(self, t: float):
		''' Update the possibly time-varying state constraints ''' 
		if self.dynamic_dirichlet:
			self.dirichlet_values = np.array([self.dirichlet_fun(t, x) for x in self.X_dirichlet])
			if self.iter_mode is IterationMode.cvx:
				self._y_cstr.value = self.dirichlet_values
		if self.dynamic_neumann:
			self.neumann_values = np.array([self.neumann_fun(t, x) for x in self.X_neumann])

	def set_constraints(self):
		''' Set the state constraints ''' 
		if self.iter_mode is IterationMode.dydt:
			self.integrator.y[self.dirichlet_indices - self.ndim] = self.dirichlet_values
			self.integrator.y = self.project_fun(self.integrator.y)
		elif self.iter_mode is IterationMode.cvx:
			# No need to set boundary conditions since guaranteed by solution
			self._y = self.project_fun(self._y)
		elif self.iter_mode is IterationMode.map:
			self._y[self.dirichlet_indices] = self.dirichlet_values
			self._y = self.project_fun(self._y)

	''' Properties ''' 

	@property
	def y(self):
		if self.iter_mode is IterationMode.dydt:
			return self.integrator.y[:self.ndim]
		elif self.iter_mode is IterationMode.cvx or self.iter_mode is IterationMode.map:
			return self._y

	@property
	def t(self):
		if self.iter_mode is IterationMode.dydt:
			return self.integrator.t
		elif self.iter_mode is IterationMode.cvx or self.iter_mode is IterationMode.map:
			return self._t

	@property 
	def dt(self):
		assert self.iter_mode is IterationMode.dydt, 'Can only get step size of differential stepper'
		return self.max_step if self.stepper.step_size is None else self.stepper.step_size

	def system(self, name: str) -> System:
		return System(self, {name: self})


''' Coupled dynamical systems on the same domain ''' 

class coupled_fds(Integrable):
	''' Coupling multiple fds objects in time, including those with different evolution laws.
	''' 
	def __init__(self, *systems: Tuple[fds]):
		assert len(systems) >= 2, 'Pass two or more systems to couple'
		assert all([sys.t == 0. for sys in systems]), 'All systems must be at zero-time initial conditions.'
		assert all([sys.iter_mode != IterationMode.none for sys in systems]), 'All systems must have evolution laws.'
		self.t0 = 0.
		for sys in systems:
			sys.uuid = shortuuid.uuid() # Hacky..
		self.systems = {
			IterationMode.dydt: list(filter(lambda sys: sys.iter_mode is IterationMode.dydt, systems)),
			IterationMode.cvx: list(filter(lambda sys: sys.iter_mode is IterationMode.cvx, systems)),
			IterationMode.map: list(filter(lambda sys: sys.iter_mode is IterationMode.map, systems)),
		}

		# Common state for discrete systems
		self.discrete_t = self.t0 
		self.discrete_y = {
			sys.uuid: sys.y0 for sys in self.systems[IterationMode.cvx] + self.systems[IterationMode.map]
		}

		# Common state for continuous systems
		self.has_integrator = len(self.systems[IterationMode.dydt]) > 0
		if self.has_integrator:
			dydt_systems = self.systems[IterationMode.dydt]
			self.dydt_max_step = min([sys.max_step for sys in dydt_systems])
			self.dydt_solver_args = merge_dicts([sys.solver_args for sys in dydt_systems])
			self.dydt_y0 = np.concatenate([sys.y0 for sys in self.systems[IterationMode.dydt]])
			self.integrator = LSODA(self.dydt, self.t0, self.dydt_y0, np.inf, max_step=self.dydt_max_step, **self.dydt_solver_args)

		# Attach views to state
		last_index = 0
		for sys in self.systems[IterationMode.dydt]:
			sys.view = slice(last_index, sys.y0.size)
			attach_dyn_props(sys, {'y': lambda sys: self.integrator.y[sys.view], 't': lambda _: self.t})
			last_index += sys.y0.size

		for sys in self.systems[IterationMode.cvx] + self.systems[IterationMode.map]:
			attach_dyn_props(sys, {'y': lambda sys: self.discrete_y[sys.uuid], 't': lambda _: self.t})


	''' Stepping ''' 

	def step(self, dt: float):
		if self.has_integrator:
			self.step_continuous(dt)
		else:
			self.step_discrete(dt)

	def step_continuous(self, dt: float):
		self.integrator.t_bound = self.t + dt
		self.integrator.status = 'running'
		while self.integrator.status != 'finished':
			self.integrator.step()
			# Make final step on discrete systems if necessary
			if self.integrator.t > self.discrete_t:
				self.step_discrete(self.integrator.t - self.discrete_t)
			# Apply constraints to continuous subsystems
			for sys in self.systems[IterationMode.dydt]:
				sys.update_constraints(self.integrator.t)
				self.integrator.y[sys.view][sys.dirichlet_indices - sys.ndim] = sys.dirichlet_values
				self.integrator.y[sys.view] = sys.project_fun(self.integrator.y[sys.view])

	def step_discrete(self, dt: float):
		for sys in self.systems[IterationMode.cvx]:
			sys.step(dt)
		for sys in self.systems[IterationMode.map]:
			sys.step(dt)
		for sys in self.systems[IterationMode.cvx]:
			self.discrete_y[sys.uuid] = sys._y.copy()
		for sys in self.systems[IterationMode.map]:
			self.discrete_y[sys.uuid] = sys._y.copy()
		self.discrete_t += dt

	def dydt(self, t: Time, y: np.ndarray):
		self.step_discrete(t - self.discrete_t) # Interleave discrete system with continuous one
		return np.concatenate([sys.dydt(t, y[sys.view]) for sys in self.systems[IterationMode.dydt]])

	def reset(self):
		if self.has_integrator:
			self.integrator = LSODA(self.dydt, self.t0, self.dydt_y0, np.inf, max_step=self.dydt_max_step, **self.dydt_solver_args)
		for sys in self.systems[IterationMode.cvx] + self.systems[IterationMode.map]:
			sys.reset()
			self.discrete_y[sys.uuid] = sys._y.copy()

	''' Observation ''' 

	def observables(self) -> List[Observable]:
		return flatten(list(self.systems.values()))

	@property
	def t(self):
		if self.has_integrator:
			return self.integrator.t
		else:
			return self.direct_pdes[0].t


def couple(observables: Dict[str, Observable]) -> System:
	''' Couple multiple observables ''' 
	stepper = coupled_fds(*observables.values())
	return System(stepper, observables)