''' Operations on pde's ''' 

from .core import *

def couple(*pdes: Tuple[pde]) -> System:
	return coupled_pde(*pdes).system()

def project_cycle_basis(p: pde) -> System:
	pass