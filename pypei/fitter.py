from . import util
import casadi as ca
import numpy as np

class Solver():
    def __init__(self, config=None):
        self.solver = None
        self.objective_function = None
        self.constraints = None
        self.decision_vars = None
        self.parameters = None

        self.__default_solve_opts__ =  {
            'ipopt': {
                'print_level': 5,
                'print_frequency_iter': 50,
            }
        }
        self.solve_opts = self.__default_solve_opts__

        self.profilers = []

        if config:
            self.make(config)

    def make(self, config):
        self.decision_vars = config['x']
        self.parameters = config['p']
        self.objective_function = config['f']
        self.constraints = config['g']

        if 'o' in config:
            self.solve_opts = config['o']

        self.solver = ca.nlpsol('solver', 'ipopt',
            {
                'x': self.decision_vars,
                'f': self.objective_function,
                'g': self.constraints,
                'p': self.parameters,
            },
            self.solve_opts
        )

    def __call__(self, *args, **kwargs):
        return self.solver(*args, **kwargs)

    @staticmethod
    def make_config(model, objective):
        """ Generates the default solver configuration

        x, Decision variables: [c, p] which are the spline coefficients and model parameters
        f, Objective Function: from objective object
        g, Constraints: On the state variables (e.g. for non-negativity)
        p, Parameters: L matrices and data
        """
        return {
            'x': ca.vcat([*model.cs, *model.ps]),
            'f': objective.objective_function,
            'g': model.xs.reshape((-1,1)),
            'p': ca.vcat(util.flat_squash(*objective.Ls,*objective.y0s))
        }

    def prep_p_former(self, objective):
        self._p_former = ca.Function('p_former', objective.Ls + objective.y0s, 
                                     [ca.vcat(util.flat_squash(*objective.Ls,*objective.y0s))])

    def form_p(self, Ls, y0s):
        """ Combines inputs for L matrices and data for use in the solver
        """
        return self._p_former(*Ls, *y0s)

    @staticmethod
    def proto_x0(model):
        """ Generates initial iterates for the decision variables x = [c, p]

        This returns all ones of the correct shape, which can be further manipulated.
        """
        return {
            'x0': np.ones(ca.vcat([*model.cs, *model.ps]).shape),
            'c0': np.ones(ca.vcat(model.cs).shape),
            'p0': np.ones(ca.vcat(model.ps).shape)
        }

    @staticmethod
    def make_profiler_configs(model):
        return [{'g+': p} for p in model.ps]

    def make_profilers(self, configs):
        for config in configs:
            profile_constraint = ca.vcat([self.constraints, config['g+']])
            self.profilers.append(
                ca.nlpsol('solver', 'ipopt',
                        {
                            'x': self.decision_vars,
                            'f': self.objective_function,
                            'g': profile_constraint,
                            'p': self.parameters,
                        },
                        self.solve_opts)
            )

    @staticmethod
    def profile_bound_range(profiler, mle):
        pass

    @staticmethod
    def profile_bounds(profiler_fn, bnd_value, lbg_v=-np.inf, ubg_v=np.inf):
        gsz = profiler_fn.size_in(2) # exploiting structure of Casadi.IpoptInterface
        lbg = np.ones(gsz)*lbg_v
        ubg = np.ones(gsz)*ubg_v
        lbg[-1] = bnd_value
        ubg[-1] = bnd_value
        return lbg, ubg


    def get_parameters(self, solution, model):
        return ca.Function('pf', [self.decision_vars], model.ps)(solution['x'])

    def get_state(self, solution, model):
        return ca.Function('xf', [self.decision_vars], [model.xs])(solution['x'])
