# -*- coding: utf-8 -*-
"""
Define the global configuration values through the :class:`MassConfiguration`.

Attributes for model construction:
    * :attr:`~MassBaseConfiguration.boundary_compartment`
    * :attr:`~MassBaseConfiguration.default_compartment`
    * :attr:`~MassBaseConfiguration.irreversible_Keq`
    * :attr:`~MassBaseConfiguration.irreversible_kr`
    * :attr:`~MassBaseConfiguration.exclude_metabolites_from_rates`
    * :attr:`~MassBaseConfiguration.model_creator`

Attributes for model simulation:
    * :attr:`~MassBaseConfiguration.decimal_precision`
    * :attr:`~MassBaseConfiguration.steady_state_threshold`

Attributes for flux balance analysis (FBA):
    * :attr:`~MassBaseConfiguration.optimization_solver`
    * :attr:`~MassBaseConfiguration.optimization_tolerance`
    * :attr:`~MassBaseConfiguration.processes`
    * :attr:`~MassBaseConfiguration.lower_bound`
    * :attr:`~MassBaseConfiguration.upper_bound`
    * :attr:`~MassBaseConfiguration.bounds`

Notes
-----
The :class:`MassConfiguration` is synchronized with the
:class:`~.Configuration`. However, in addition to the optimization solvers
from cobrapy, masspy utilizes ODE solvers. This may lead to confusion when
trying to change solver options such as tolerances, since an optimization
solver may need to utilize a different tolerance than the ODE solver.

Therefore, the :attr:`~.BaseConfiguration.solver` and
:attr:`~.BaseConfiguration.tolerance` attributes of the
:class:`~.Configuration` class are renamed to
:attr:`~MassBaseConfiguration.optimization_solver` and
:attr:`~MassBaseConfiguration.optimization_tolerance` in the
:class:`MassConfiguration` class to help prevent confusion.

"""
from cobra.core.configuration import Configuration
from cobra.core.singleton import Singleton
from cobra.util.solver import interface_to_str

from six import integer_types, iteritems, string_types

COBRA_CONFIGURATION = Configuration()


class MassBaseConfiguration:
    """Define global configuration values honored by :mod:`mass` functions.

    Notes
    -----
    The :class:`MassConfiguration` should be always be used over the
    :class:`MassBaseConfiguration` in order for global configuration to work
    as intended.

    Attributes
    ----------
    boundary_compartment : dict
        A dictionary containing the identifier of the boundary compartment
        mapped to the name of the boundary compartment.

        Default value is ``{"b": "boundary"}``.
    default_compartment : dict
        A dictionary containing the identifier of the default compartment
        mapped to the name of the desired name of default compartment.
        Primarily used in writing models to SBML when there are no set
        compartments in the model.

        Default value is ``{"default": "default_compartment"}``.
    irreversible_Keq : float
        The default value to assign to equilibrium constants (Keq) for
        irreversible reactions. Must be a non-negative value.

        Default value is ``float("inf")``.
    irreversible_kr : float
        The default value to assign to equilibrium constants (Keq) for
        irreversible reactions. Must be a non-negative value.

        Default value is the ``0.``
    exclude_metabolites_from_rates : dict
        A dict where keys should correspond to a metabolite attrubute to
        utilize for filtering, and values are lists that contain the items to
        exclude that would be returned by the metabolite attribute. Does not
        apply to boundary reactions.

        Default is ``dict("elements", [{"H": 2, "O": 1}, {"H": 1}])`` to
        remove the hydrogen and water metabolites using the
        :attr:`~.MassMetabolite.elements` attribute to filter out the hydrogen
        and water in all rates except the hydrogen and water exchange
        reactions on the boundary.
    include_compartments_in_rates : bool
        Whether to include the compartment volumes in rate expressions.
        The boundary compartment will always excluded.

        Default is ``False``.
    model_creator : dict
        A dict containing the information about the model creator where keys
        are SBML creator fields and values are strings. Valid keys include:

        * ``'familyName'``
        * ``'givenName'``
        * ``'organization'``
        * ``'email'``

        To successfully export a model creator, all keys must have non-empty
        string values.
    decimal_precision : int or None
        An integer indicating the decimal precision to use for rounding
        numerical values. Positive numbers indicated digits to the right of the
        decimal place, negative numbers indicate digits to the left of the
        decimal place. If ``None`` provided, no solutions will be rounded.

        Default is ``None``.
    steady_state_threshold : float
        A threshold for determining whether the RoadRunner steady state solver
        is at steady state. The steady state solver returns a value indicating
        how close the solution is to the steady state, where smaller values
        are better. Values less than the threshold indicate steady state.

        Default is ``1e-6``.
    optimization_solver : str
        The default optimization solver. The solver choices are the ones
        provided by `optlang` and solvers installed in your environment.
        Valid solvers typically include: ``"glpk"``, ``"cplex"``, ``"gurobi"``
    optimization_tolerance : float
        The default tolerance for the optimization solver being used.

        Default value is ``1e-7``.
    lower_bound : float
        The standard lower bound for reversible reactions.

        Default value is ``-1000.``
    upper_bound : float
        The standard upper bound for all reactions.

        Default value is ``1000.``
    bounds : tuple of floats
        The default reaction bounds for newly created reactions. The bounds
        are in the form of lower_bound, upper_bound.

        Default values are ``(-1000.0, 1000.0)``.
    processes : int
        A default number of processes to use where multiprocessing is
        possible. The default number corresponds to the number of available
        cores (hyperthreads).

    """

    # pylint: disable=too-many-instance-attributes
    def __init__(self):
        """Initialize MassBaseConfiguration."""
        # Model construction configuration options
        self._boundary_compartment = {"b": "boundary"}
        self._default_compartment = {"compartment": "default_compartment"}
        self._irreversible_Keq = float("inf")
        self._irreversible_kr = 0
        self.exclude_metabolites_from_rates = {
            "elements": [{"H": 2, "O": 1}, {"H": 1}]}
        self.include_compartments_in_rates = False
        self._model_creator = {
            "familyName": "",
            "givenName": "",
            "organization": "",
            "email": ""}

        # Model simulation options
        self._decimal_precision = None
        self._steady_state_threshold = 1e-6

        # For cobra configuration synchronization
        self._shared_state = COBRA_CONFIGURATION.__dict__

    @property
    def boundary_compartment(self):
        """Get or set the default value for the boundary compartment.

        Parameters
        ----------
        compartment_dict : dict
            A dictionary containing the identifier of the boundary compartment
            mapped to the name of the boundary compartment.

        """
        return getattr(self, "_boundary_compartment")

    @boundary_compartment.setter
    def boundary_compartment(self, compartment_dict):
        """Set the default value for the boundary compartment."""
        setattr(self, "_boundary_compartment", compartment_dict)

    @property
    def default_compartment(self):
        """Get or set the default value for the default compartment.

        Parameters
        ----------
        compartment_dict : dict
            A dictionary containing the identifier of the default compartment
            mapped to the name of the default compartment.

        """
        return getattr(self, "_default_compartment")

    @default_compartment.setter
    def default_compartment(self, compartment_dict):
        """Set the default value for the default compartment."""
        setattr(self, "_default_compartment", compartment_dict)

    @property
    def irreversible_Keq(self):
        """Get or set the default 'Keq' value of an irreversible reaction.

        Notes
        -----
        Equilibrium constants cannot be negative.

        Parameters
        ----------
        value : float
            A non-negative number for the equilibrium constant (Keq)
            of the reaction.

        Raises
        ------
        ValueError
            Occurs when trying to set a negative value.

        """
        return getattr(self, "_irreversible_Keq")

    @irreversible_Keq.setter
    def irreversible_Keq(self, value):
        """Set the default value for Keq of an irreversible reaction."""
        if not isinstance(value, (integer_types, float)):
            raise TypeError("Must be an int or float")
        if value < 0.:
            raise ValueError("Must be a non-negative number")
        setattr(self, "_irreversible_Keq", value)

    @property
    def irreversible_kr(self):
        """Get or set the default 'kr' value of an irreversible reaction.

        Notes
        -----
        Reverse rate constants cannot be negative.

        Parameters
        ----------
        value : float
            A non-negative number for the reverse rate constant (kr)
            of the reaction.

        Raises
        ------
        ValueError
            Occurs when trying to set a negative value.

        """
        return getattr(self, "_irreversible_kr")

    @irreversible_kr.setter
    def irreversible_kr(self, value):
        """Set the default value for kr of an irreversible reaction."""
        if not isinstance(value, (integer_types, float)):
            raise TypeError("Must be an int or float")
        if value < 0.:
            raise ValueError("Must be a non-negative number")
        setattr(self, "_irreversible_kr", value)

    @property
    def model_creator(self):
        """Get or set the values for the dict representing the model creator.

        Notes
        -----
        A read-only copy of the dict is returned.

        Parameters
        ----------
        creator_dict : dict
            A dict containing the model creator information. Keys can only
            be the following:

            * 'familyName'
            * 'givenName'
            * 'organization'
            * 'email'

            Values must be strings or ``None``.

        """
        return self._model_creator.copy()

    @model_creator.setter
    def model_creator(self, creator_dict):
        """Set the information in the dict representing the model creator."""
        valid = {'familyName', 'givenName', 'organization', 'email'}
        for k, v in iteritems(creator_dict):
            if k not in valid:
                raise ValueError("Invalid key '{0}'. Keys can only be the"
                                 " following: {1:r}".format(k, str(valid)))
            if v is not None and not isinstance(v, string_types):
                raise TypeError("'{0}' not a string. Values must be strings or"
                                " None.".format(str(v)))

        self._model_creator.update(creator_dict)

    @property
    def decimal_precision(self):
        """Get or set the default decimal precision when rounding.

        Notes
        -----
        The :attr:`decimal_precison` is applied as follows::

            new_value = round(value, decimal_precison)

        Parameters
        ----------
        precision : int or None
            An integer indicating how many digits from the decimal should
            rounding occur. If ``None``, no rounding will occur.

        """
        return getattr(self, "_decimal_precision")

    @decimal_precision.setter
    def decimal_precision(self, precision):
        """Set the default decimal precision when rounding."""
        if precision is not None and not isinstance(precision, integer_types):
            raise TypeError("precision must be an int.")

        setattr(self, "_decimal_precision", precision)

    @property
    def steady_state_threshold(self):
        """Get or set the steady state threshold when using roadrunner solvers.

        Notes
        -----
        * With simulations. the absolute difference between the last two points
          must be less than the steady state threshold.
        * With steady state solvers, the sum of squares of the steady state
          solution must be less than the steady state threshold.
        * Steady state threshold values cannot be negative.

        Parameters
        ----------
        threshold : float
            The threshold for determining whether a steady state occurred.

        Raises
        ------
        ValueError
            Occurs when trying to set a negative value.

        """
        return getattr(self, "_steady_state_threshold")

    @steady_state_threshold.setter
    def steady_state_threshold(self, threshold):
        """Set the default decimal precision when rounding."""
        if not isinstance(threshold, (integer_types, float)):
            raise TypeError("Must be an int or float")
        if threshold < 0.:
            raise ValueError("Must be a non-negative number")
        setattr(self, "_steady_state_threshold", threshold)

    @property
    def optimization_solver(self):
        """Get or set the solver utilized for optimization.

        Parameters
        ----------
        solver : str
            The solver to utilize in optimizations. Valid solvers typically
            include:

                * ``"glpk"``
                * ``"cplex"``
                * ``"gurobi"``

        Raises
        ------
        :class:`cobra.exceptions.SolverNotFound`
            Occurs for invalid solver values.

        """
        return COBRA_CONFIGURATION.solver

    @optimization_solver.setter
    def optimization_solver(self, solver):
        """Set the solver utilized for optimization."""
        # pylint: disable=no-self-use
        COBRA_CONFIGURATION.solver = solver

    @property
    def optimization_tolerance(self):
        """Get or set the tolerance value utilized by the optimization solver.

        Parameters
        ----------
        tol : float
            The tolerance value to set.

        """
        return COBRA_CONFIGURATION.tolerance

    @optimization_tolerance.setter
    def optimization_tolerance(self, tol):
        """Set the tolerance value utilized by the optimization solver."""
        # pylint: disable=no-self-use
        COBRA_CONFIGURATION.tolerance = tol

    @property
    def lower_bound(self):
        """Get or set the default value of the lower bound for reactions.

        Parameters
        ----------
        bound : float
            The default bound value to set.

        """
        return COBRA_CONFIGURATION.lower_bound

    @lower_bound.setter
    def lower_bound(self, bound):
        """Set the default value of the lower bound for reactions."""
        # pylint: disable=no-self-use
        COBRA_CONFIGURATION.lower_bound = bound

    @property
    def upper_bound(self):
        """Get or set the default value of the lower bound for reactions.

        Parameters
        ----------
        bound : float
            The default bound value to set.

        """
        return COBRA_CONFIGURATION.upper_bound

    @upper_bound.setter
    def upper_bound(self, bound):
        """Set the default value of the lower bound for reactions."""
        # pylint: disable=no-self-use
        COBRA_CONFIGURATION.upper_bound = bound

    @property
    def bounds(self):
        """Get or set the default lower and upper bounds for reactions.

        Parameters
        ----------
        bounds : tuple of floats
            A tuple of floats to set as the new default bounds in the form
            of ``(lower_bound, upper_bound)``.

        Raises
        ------
        AssertionError
            Occurs when lower bound is greater than the upper bound.

        """
        return COBRA_CONFIGURATION.bounds

    @bounds.setter
    def bounds(self, bounds):
        """Set the default lower and upper bounds for reactions."""
        # pylint: disable=no-self-use
        COBRA_CONFIGURATION.bounds = bounds

    @property
    def processes(self):
        """Return the default number of processes to use when possible."""
        return COBRA_CONFIGURATION.processes

    @property
    def shared_state(self):
        """Return a read-only dict for shared configuration attributes."""
        shared_state = {}
        for k, v in iteritems(self._shared_state):
            if k in ["_solver", "tolerance"]:
                k = "optimization_" + k.strip("_")
            shared_state[k] = v

        return shared_state

    def _repr_html_(self):
        """Return the HTML representation of the MassConfiguration.

        Warnings
        --------
        This method is intended for internal use only.

        """
        return """
        <table>
            <tr><tr>
                <td><strong>Boundary Compartment</strong></td>
                <td>{boundary_compartment}</td>
            </tr><tr>
                <td><strong>Default Compartment</strong></td>
                <td>{default_compartment}</td>
            </tr><tr>
                <td><strong>Irreversible Reaction Keq</strong></td>
                <td>{irreversible_Keq}</td>
            </tr><tr>
                <td><strong>Irreversible Reaction kr</strong></td>
                <td>{irreversible_kr}</td>
            </tr><tr>
                <td><strong>Compartments in rates</strong></td>
                <td>{include_compartments_in_rates}</td>
            </tr><tr>
                <td><strong>Decimal precision</strong></td>
                <td>{decimal_precision}</td>
            </tr><tr>
                <td><strong>Steady state threshold</strong></td>
                <td>{steady_state_threshold}</td>
            </tr>
                <td><strong>Optimization solver</strong></td>
                <td>{optimization_solver}</td>
            </tr><tr>
                <td><strong>Optimization solver tolerance</strong></td>
                <td>{optimization_tolerance}</td>
            </tr><tr>
                <td><strong>Lower bound</strong></td>
                <td>{lower_bound}</td>
            </tr><tr>
                <td><strong>Upper bound</strong></td>
                <td>{upper_bound}</td>
            </tr><tr>
                <td><strong>Processes</strong></td>
                <td>{processes}</td>
            </tr>
        </table>""".format(
            boundary_compartment=[
                "{0}: {1}".format(k, v) if v else k for k, v in iteritems(
                    self.boundary_compartment)][0],
            default_compartment=[
                "{0}: {1}".format(k, v) if v else k for k, v in iteritems(
                    self.default_compartment)][0],
            irreversible_Keq=self.irreversible_Keq,
            irreversible_kr=self.irreversible_kr,
            include_compartments_in_rates=self.include_compartments_in_rates,
            decimal_precision=self.decimal_precision,
            steady_state_threshold=self.steady_state_threshold,
            optimization_solver=interface_to_str(self.optimization_solver),
            optimization_tolerance=self.optimization_tolerance,
            lower_bound=self.lower_bound,
            upper_bound=self.upper_bound,
            processes=self.processes)

    def __repr__(self):
        """Override default :func:`repr` for the MassConfiguration.

        Warnings
        --------
        This method is intended for internal use only.

        """
        return """MassConfiguration:
        boundary compartment: {boundary_compartment}
        default compartment: {default_compartment}
        irreversible reaction Keq: {irreversible_Keq}
        irreversible reaction kr: {irreversible_kr}
        include_compartments_in_rates: {include_compartments_in_rates}
        decimal_precision: {decimal_precision}
        steady_state_threshold: {steady_state_threshold}
        optimization solver: {optimization_solver}
        optimization solver tolerance: {optimization_tolerance}
        lower_bound: {lower_bound}
        upper_bound: {upper_bound}
        processes: {processes}""".format(
            boundary_compartment=[
                "{0} ({1})".format(v, k) if v else k for k, v in iteritems(
                    self.boundary_compartment)][0],
            default_compartment=[
                "{0} ({1})".format(v, k) if v else k for k, v in iteritems(
                    self.default_compartment)][0],
            irreversible_Keq=self.irreversible_Keq,
            irreversible_kr=self.irreversible_kr,
            include_compartments_in_rates=self.include_compartments_in_rates,
            decimal_precision=self.decimal_precision,
            steady_state_threshold=self.steady_state_threshold,
            optimization_solver=interface_to_str(self.optimization_solver),
            optimization_tolerance=self.optimization_tolerance,
            lower_bound=self.lower_bound,
            upper_bound=self.upper_bound,
            processes=self.processes)


class MassConfiguration(MassBaseConfiguration, metaclass=Singleton):
    """Define the configuration to be :class:`.Singleton` based."""


__all__ = ("MassConfiguration", "MassBaseConfiguration",)
