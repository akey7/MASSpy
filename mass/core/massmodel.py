# -*- coding: utf-8 -*-

# Compatibility with Python 2.7
from __future__ import absolute_import

# Import necesary packages
import re
import logging
import pandas as pd
import numpy as np
import sympy as sp
from warnings import warn
from functools import partial
from copy import copy, deepcopy
from scipy.sparse import dok_matrix, lil_matrix
from six import string_types, integer_types, iteritems, iterkeys, itervalues

# from cobra
from cobra.core.object import Object
from cobra.core.dictlist import DictList
from cobra.util.context import HistoryManager, resettable, get_context

# from mass
from mass.util import qcqa
from mass.core import expressions
from mass.core.massmetabolite import MassMetabolite
from mass.core.massreaction import MassReaction

# Class begins
## Set the logger
LOGGER = logging.getLogger(__name__)
## Global symbol for time
t = sp.Symbol("t")
## Precompiled regular expressions for string_to_mass
### For object IDs
_rxn_id_finder = re.compile("^(\w+):")
_met_id_finder = re.compile("^s\[(\S+)[,|\]]")
### For reaction arrows
_reversible_arrow = re.compile("<(-+|=+)>")
_forward_arrow = re.compile("(-+|=+)>")
_reverse_arrow = re.compile("<(-+|=+)")
### For metabolite arguments
_name_arg = re.compile("name=(\w+)")
_formula_arg = re.compile("formula=(\w+)")
_charge_arg = re.compile("charge=(\w+)")
_compartment_finder = re.compile("\](\[[A-Za-z]\])")
_equals = re.compile("=")

# Class definition
class MassModel(Object):
	"""MassModel is a class for storing MassReactions, MassMetabolites, and
	all other information necessary to create a mass model for simulation.

	Parameters
	----------
	id_or_massmodel : MassModel, string
		Either an existing MassModel object in which case a new MassModel
		object is instantiated with the same properties as the original
		massmodel, or an identifier to associate with the massmodel as a string
	matrix_type: {'dense', 'dok', 'lil', 'DataFrame', 'symbolic'} or None
		If None, will utilize the matrix type initialized with the original
		model. Otherwise reconstruct the S matrix with the specified type.
		Types can include 'dense' for a standard  numpy.array, 'dok' or
		'lil' to obtain the scipy matrix of the corresponding type,
		DataFrame for a pandas 'Dataframe' where species (excluding genes)
		are row indicies and reactions are column indicices, and 'symbolic'
		for a sympy.Matrix.
	dtype : data-type
		The desired data-type for the array. If None, defaults to float64

	Attributes
	----------
	reactions : Dictlist
		A DictList where the keys are the reaction identifiers and the values
		are the associated MassReaction objects
	metabolites : DictList
		A DictList where the keys are the metabolite identifiers and the values
		are the associated MassMetabolite objects
	genes : DictList
		A DictList where the keys are the gene identifiers and the values
		are the associated Gene objects
	initial_conditions : dict
		A dictionary to store the initial conditions for the metabolites,
		where keys are metabolite objects and values are initial conditions.
		Can have different initial conditions from the metabolites if desired.
	custom_rates : dict
		A dictionary to store custom rates for specific reactions, where
		keys are reaction objects and values are the custom rate expressions.
		Custom rates will always have preference over rate laws in reactions.
	custom_parameters : dict
		A dictionary to store custom parameters for custom rates,
		keys are parameters and values are the parameter value.
		Custom rates will always have preference over rate laws in reactions.
	fixed_concentrations : dict
		A dictionary to store fixed concentrations for metabolites, where
		keys are metabolite objects or "external metabolites" of exchange
		reactions as strings, and values are the fixed concentrations.
		Fixed concentrations will always have preference over the metabolite
		ODEs representing concentrations.
	modules : set
		A dictionary to store the models/modules associated with this model.
		Keys are model idenfifiers (model.id) and values are MassModel objects.
	compartments : dict
		A dictionary to store the compartment shorthands and their full names.
		Keys are the shorthands and values are the full names.
		Example: {'c': 'cytosol'}
	units : dict
		A dictionary to store the units used in the model for referencing.

		WARNING: Note that the MassModel will not track the units,
		Therefore all unit conversions must be manually in order to ensure
		numerical consistency in the model. It is highly recommended to stick
		with the following units:

		{'N': 'Millimoles', 'Vol': 'Liters', 'Time': 'Hours'}
	"""
	def __init__(self, id_or_massmodel=None, name=None,
				matrix_type=None, dtype=None):
		"""Initialize the MassModel Object"""
		if isinstance(id_or_massmodel, MassModel):
			Object.__init__(self, id_or_massmodel, name=name)
			self.__setstate__(id_or_massmodel.__dict__)
			if not hasattr(self, "name"):
				self.name = None
			self.update_S(matrix_type=matrix_type, dtype=dtype)
		else:
			Object.__init__(self, id_or_massmodel, name=name)
			# A DictList of MassReactions
			self.reactions = DictList()
			# A DictList of MassMetabolites
			self.metabolites = DictList()
			# A DictList of cobra Genes
			self.genes = DictList()
			# A dictionary of initial conditions for MassMetabolites
			self.initial_conditions = dict()
			# For storing of custom rate laws and fixed concentrations
			self._rtype = 1
			self._custom_rates= dict()
			self._custom_parameters = dict()
			self.fixed_concentrations = dict()
			# For storing added models and modules
			self.modules = set()
			# A dictionary of the compartments in the model
			self.compartments = dict()
			# A dictionary to store the units utilized in the model.
			self.units = dict()
			# Internal storage of S matrix and data types for updating S
			self._matrix_type = matrix_type
			self._dtype = dtype
			# For storing the stoichiometric matrix.
			self._S = self._create_stoichiometric_matrix(
									matrix_type=self._matrix_type,
									dtype=self._dtype,
									update_model=True)
			# For storing the HistoryManager contexts
			self._contexts = []

	# Properties
	@property
	def attributes(self):
		"""Get a list of public model attributes and properties"""
		return [s for s in iterkeys(self.__dict__) if s[0] is not '_'] + \
				[p for p in dir(self.__class__)
				if isinstance(getattr(self.__class__ ,p),property)]

	@property
	def S(self):
		"""Get the Stoichiometric Matrix of the MassModel"""
		return self.update_S(matrix_type=self._matrix_type, dtype=self._dtype,
							update_model=False)
	@property
	def rates(self):
		"""Get the rate laws for the reactions as sympy expressions in a
		dictionary where keys are the reaction objects and values are the
		sympy rate law expressions
		"""
		rate_dict =  {rxn: rxn.generate_rate_law(rate_type=self._rtype,
								sympy_expr=True, update_reaction=True)
								for rxn in self.reactions}
		if self.custom_rates != {}:
			rate_dict.update(self.custom_rates)
		return rate_dict

	@property
	def odes(self):
		"""Get the ODEs for the metabolites as sympy expressions where
		keys are the metabolite objects and values are the ODE expressions
		"""
		return {metab: metab.ode for metab in self.metabolites
				if metab not in self.fixed_concentrations}

	@property
	def exchanges(self):
		"""Get the exchange reactions in the MassModel"""
		return [rxn for rxn in self.reactions if rxn.exchange]

	@property
	def get_external_metabolites(self):
		"""Get all 'external' metabolites in the reaction. Primarily used for
		setting fixed concentrations for null sinks and sources"""
		external_set = {rxn.get_external_metabolite for rxn in self.reactions
				if rxn.exchange}
		return list(sorted(external_set))

	@property
	def get_metabolite_compartments(self):
		"""Return all metabolites' compartments

		Identical to the method in cobra.core.model
		"""
		return {metab.compartment for metab in self.metabolites
				if metab.compartment is not None}

	@property
	def get_irreversible_reactions(self):
		"""Return a list of all irreversible reactions in the model."""
		return [rxn for rxn in self.reactions if not rxn.reversible]

	@property
	def steady_state_fluxes(self):
		"""Return all steady state fluxes stored in the model reactions"""
		return {rxn: rxn.ssflux for rxn in self.reactions
				if rxn.ssflux is not None}

	@property
	def custom_rates(self):
		"""Get the sympy custom rate expressions in the MassModel"""
		return self._custom_rates

	@property
	def custom_parameters(self):
		"""Get the custom rate parameters in the MassModel"""
		return self._custom_parameters
	@property
	def parameters(self):
		"""Get all of the parameters associated with a MassModel"""
		parameters = {}
		for rxn in self.reactions:
			parameters.update(rxn.parameters)
			parameters.update(self.fixed_concentrations)
			parameters.update(self.custom_parameters)
		return parameters

	# Methods
	## Public
	def update_S(self, reaction_list=None, matrix_type=None, dtype=None,
				update_model=True):
		"""Update the S matrix of the model.

		NOTE: reaction_list is assumed to be at the end of self.reactions.

		Parameters
		----------
		model : mass.MassModel
			The MassModel object to construct the matrix for
		reaction_list : list of MassReactions, optional
			List of MassReactions to add to the current stoichiometric matrix.
			Reactions must already exist in the model in order to update.
			If None, the entire stoichiometric matrix is reconstructed
		matrix_type: {'dense', 'dok', 'lil', 'DataFrame', 'symbolic'}, optional
			If None, will utilize the matrix type initialized with the original
			model. Otherwise reconstruct the S matrix with the specified type.
			Types can include 'dense' for a standard  numpy.array, 'dok' or
			'lil' to obtain the scipy matrix of the corresponding type,
			DataFrame for a pandas 'Dataframe' where species (excluding genes)
			are row indicies and reactions are column indicices, and 'symbolic'
			for a sympy.MutableDenseMatrix.
		dtype : data-type, optional
			The desired data-type for the array. If None, defaults to float64
		update_model : bool, optional
			If True, will update the stored S matrix in the model with the new
			matrix type and dtype.

		Returns
		-------
		matrix of class 'dtype'
			The stoichiometric matrix for the given MassModel
		"""
		# Check matrix type input if it exists to ensure its a valid matrix type
		if matrix_type is not None:
			if not isinstance(matrix_type, string_types):
				raise TypeError("matrix_type must be a string")
			# Remove case sensitivity
			matrix_type = matrix_type.lower()
			if matrix_type not in {'dense', 'dok', 'lil', 'dataframe',
									'symbolic'}:
				raise ValueError("matrix_type must be of one of the following"
						" {'dense', 'dok', 'lil', 'dataframe', 'symbolic'}")
		else:
			matrix_type = self._matrix_type

		# Use the model's stored datatype if the datatype is not specified
		if dtype is None:
			dtype = self._dtype

		# Check input of update model
		if not isinstance(update_model, bool):
			raise TypeError("update_model must be a bool")

		# If there is no change to the reactions, just reconstruct the model
		if self._S is None or reaction_list is None:
			s_matrix = self._create_stoichiometric_matrix(matrix_type, dtype,
														update_model)
		else:
			s_matrix = self._update_stoichiometry(reaction_list,
											matrix_type=matrix_type)

		if update_model:
			self._update_model_s(s_matrix, matrix_type, dtype)

		return s_matrix

	def add_metabolites(self, metabolite_list, add_initial_conditons=False):
		"""Will add a list of metabolites to the MassModel object and add
		the MassMetabolite initial conditions accordingly.

		The change is reverted upon exit when using the MassModel as a context.

		Parameters
		----------
		metabolite_list : list
			A list of MassMetabolite objects to add to the MassModel
		add_initial_conditons : bool, optional
			If True, will also add the initial conditions associated with each
			metabolite to the model. Otherwise just add metabolites without
			their intial conditions
		"""
		# If the metabolite list is not a list
		if not hasattr(metabolite_list, '__iter__'):
			metabolite_list = [metabolite_list]
		metabolite_list = DictList(metabolite_list)
		if len(metabolite_list) == 0:
			return None

		# Check whether a metabolite is a MassMetabolite object. Then check if
		# metabolites already exist in the massmodel, and ignore those that do
		for metab in metabolite_list:
			if not isinstance(metab, MassMetabolite):
				warn("Skipping %s, not a MassMetabolite" % metab)
				metabolite_list.remove(metab)
		existing_metabs = [metab for metab in metabolite_list
							if metab.id in self.metabolites]
		for metab in existing_metabs:
			LOGGER.info("Skipped MassMetabolite %s as it already exists"
						" in MassModel" % metab.id)
		metabolite_list = [metab for metab in metabolite_list
							if metab.id not in self.metabolites]

		# Have metabolites point to model object
		for metab in metabolite_list:
			metab._model = self
		# Add metabolites, and add initial conditions if True
		self.metabolites += metabolite_list
		if add_initial_conditons:
			self.set_initial_conditions(metabolite_list)

		context = get_context(self)
		if context:
			context(partial(self.metabolites.__isub__, metabolite_list))
			for metab in metabolite_list:
				context(partial(setattr, metab, '_model', None))

	def remove_metabolites(self, metabolite_list, destructive=False):
		"""Remove a list of metabolites from the MassModel object, and
		its associated initial condition

		The change is reverted upon exit when using the MassModel as a context.

		Parameters
		----------
		metabolite_list : list
			A list of MassMetabolite objects to remove from the MassModel.
		destructive : bool, optional
			If False, then the MassMetabolite and its initial condition are
			removed from the associated MassReactions. If True, also remove
			the associated MassReactions and their rate laws from the MassModel
		"""
		# If the metabolite list is not a list
		if not hasattr(metabolite_list, '__iter__'):
			metabolite_list = [metabolite_list]
		metabolite_list = DictList(metabolite_list)
		if len(metabolite_list) == 0:
			return None

		# Check whether a metabolite already exists in the massmodel, and
		# ignore those that do not
		metabolite_list = [metab for metab in metabolite_list
							if metab.id in self.metabolites]

		# Remove assoication to model
		for metab in metabolite_list:
			metab._model = None
			if not destructive:
				# Remove metabolites from reactions
				for rxn in list(metab._reaction):
					coefficient = rxn._metabolites[metab]
					rxn.subtract_metabolites({metab : coefficient})
			else:
				# Remove associated reactions if destructive
				for rxn in list(metab._reaction):
					rxn.remove_from_model()

		# Remove initial conditions and then metabolites
		self.remove_initial_conditions(metabolite_list)
		self.metabolites -= metabolite_list

		context = get_context(self)
		if context:
			context(partial(self.metabolites.__iadd__, metabolite_list))
			for metab in metabolite_list:
				context(partial(setattr, metab, '_model', self))

	def set_initial_conditions(self, metabolite_list=None):
		"""Set the initial conditions for a list of metabolites in the model.

		The metabolite must already exist in the model in order to set its
		initial condition. Initial conditions stored in the metabolite are
		accessed and added to the model. Any existing initial condition for
		a metabolite in the model is replaced.

		The change is reverted upon exit when using the MassModel as a context.

		Parameters
		----------
		metabolite_list : list, optional
			A list of MassMetabolite objects. If None, will use all metabolites
			in the model
		"""
		if metabolite_list is None:
			metabolite_list = self.metabolites
		# If the metabolite list is not a list
		elif not hasattr(metabolite_list, '__iter__'):
			metabolite_list = DictList([metabolite_list])
		else:
			metabolite_list = DictList(metabolite_list)
		if len(metabolite_list) == 0:
			return None

		# Check whether a metabolite already exists in the massmodel, and
		# ignore those that do not
		metabolite_list = [metab for metab in metabolite_list
							if metab.id in self.metabolites]
		# Add the initial conditions
		self.update_initial_conditions({metab: metab.ic
										for metab in metabolite_list})

	def remove_initial_conditions(self, metabolite_list):
		"""Remove initial conditions for a list of metabolites in the model.

		The change is reverted upon exit when using the MassModel as a context.

		Parameters
		----------
		metabolite_list : list
			A list of MassMetabolite objects
		"""
		# If the metabolite list is not a list
		if not hasattr(metabolite_list, '__iter__'):
			metabolite_list = [metabolite_list]
		metabolite_list = DictList(metabolite_list)
		if len(metabolite_list) == 0:
			return None

		# Check whether a metabolite already exists in the massmodel, and
		# ignore those that do not
		metabolite_list = [metab for metab in metabolite_list
							if metab.id in self.metabolites]

		# Keep track of existing initial conditions for HistoryManager
		context = get_context(self)
		if context:
			existing_ics = {metab : self.initial_conditions[metab]
							for metab in metabolite_list
							if metab in self.initial_conditions}
		# Remove the initial conditions
		for metab in metabolite_list:
			del self.initial_conditions[metab]

		if context:
			context(partial(self.initial_conditions.update, existing_ics))

	def update_initial_conditions(self, ic_dict, update_metabolites=False):
		"""Update the initial conditions in the model using a dictionary where
		MassMetabolites are keys and the initial conditions are the values.

		The metabolite must already exist in the model in order to set its
		initial condition. If a metabolites initial conditions already exists
		in the model, it is replaced by the new initial condition.

		The change is reverted upon exit when using the MassModel as a context.

		Parameters
		----------
		ic_dict : dict
			A dictionary where MassMetabolites are keys and the
			initial conditions are the values.
		update_metabolites : bool, optional
			If True, will update the initial conditions in the MassMetabolite
			objects as well. Otherwise, only update the model initial conditons
		"""
		if not isinstance(ic_dict, dict):
			raise TypeError("Input must be a dictionary where keys are the "
						"MassMetabolites, and values are initial conditions")
		if len(ic_dict) == 0:
			return None

		# Check whether a metabolite already exists in the massmodel, and
		# ignore those that do not
		ic_dict = {metab : ic for metab, ic in iteritems(ic_dict)
					if metab in self.metabolites and ic is not None}

		# Keep track of existing initial conditions for HistoryManager
		context = get_context(self)
		if context:
			existing_ics = {metab : self.initial_conditions[metab]
					for metab in ic_dict if metab in self.initial_conditions}

		# Update initial conditions
		self.initial_conditions.update(ic_dict)
		if update_metabolites:
			# Update the initial condition stored in the MassMetabolite.
			for metab, ic_value in iteritems(ic_dict):
				metab._initial_condition = ic_value

		if context:
			for key in iterkeys(ic_dict):
				if key not in iterkeys(existing_ics):
					context(partial(self.initial_conditions.pop, key))
				context(partial(self.initial_conditions.update, existing_ics))
			if update_metabolites:
				for metab, ic_value in iteritems(ic_dict):
					context(partial(setattr, metab, '_initial_condition',
									existing_ics[metab]))

	def add_reactions(self, reaction_list, update_stoichiometry=False):
		"""Add MassReactions and their rates to the MassModel.

		MassReactions with identifiers identical to a reaction already in the
		MassModel are ignored.

		The change is reverted upon exit when using the MassModel as a context.

		Similar to the method in cobra.core.model

		Parameters
		----------
		reaction_list : list
			A list of MassReaction objects to add to the MassModel
		update_stoichiometry : bool, optional
			If True, will update the matrix after adding the new reactions.
		"""
		# If the reaction list is not a list
		if not hasattr(reaction_list, '__iter__'):
			reaction_list = [reaction_list]
		reaction_list = DictList(reaction_list)
		if len(reaction_list) == 0:
			return None

		# Check whether a reaction is a MassReaction object. Then check if
		# reactions already exist in the massmodel, and ignore those that do
		for rxn in reaction_list:
			if not isinstance(rxn, MassReaction):
				warn("Skipping %s, not a MassReaction" % rxn)
				reaction_list.remove(rxn)
		existing_rxns = [rxn for rxn in reaction_list
						if rxn.id in self.reactions]
		for rxn in existing_rxns:
			LOGGER.info("Skipped MassReaction %s as it already exists"
						" in MassModel" % rxn.id)
		reaction_list = [rxn for rxn in reaction_list
							if rxn.id not in self.reactions]

		context = get_context(self)

		# Add reactions, and have reactions point to the model
		for rxn in reaction_list:
			rxn._model = self
			# Loop through metabolites in a reaction
			for metab in list(iterkeys(rxn._metabolites)):
				# If metabolite doesn't exist in the model, add it
				# with its associated initial condition
				if metab not in self.metabolites:
					self.add_metabolites(metab, add_initial_conditons=True)
					metab._reaction.add(rxn)
					if context:
						context(partial(metab._reaction.remove, rxn))
				# Otherwise have the reaction point to the metabolite
				# in the model.
				else:
					coefficient = rxn._metabolites.pop(metab)
					model_metab = self.metabolites.get_by_id(metab.id)
					rxn._metabolites[model_metab] = coefficient
					model_metab._reaction.add(rxn)
					if context:
						context(partial(model_metab._reaction.remove, rxn))

			# Loop through genes associated with a reaction
			for gene in list(rxn._genes):
				# If gene is not in the model, add and have it point to model
				if not self.genes.has_id(gene.id):
					self.genes += [gene]
					gene._model = self

					if context:
						context(partial(self.genes.__isub__, [gene]))
						context(partial(setattr, gene, '_model', None))
				# Otherwise, make the gene point to the one in the model
				else:
					model_gene = self.genes.get_by_id(gene.id)
					if model_gene is not gene:
						rxn._dissociate_gene(gene)
						rxn._associate_gene(model_gene)

		# Add reactions to the model
		self.reactions += reaction_list
		if update_stoichiometry:
			self.update_S(reaction_list=reaction_list, update_model=True)

		if context:
			context(partial(self.reactions.__isub__, reaction_list))
			for rxn in reaction_list:
				context(partial(setattr, rxn, '_model', None))
			if update_stoichiometry:
				context(partial(self.update_S, None, None, None, True))


	def remove_reactions(self, reaction_list, remove_orphans=False,
						update_stoichiometry=False):
		"""Remove MassReactions from the MassModel

		The change is reverted upon exit when using the MassModel as a context.

		Parameters
		----------
		reaction_list : list
			A list of MassReaction objects to remove from the MassModel.
		remove_orphans : bool, optional
			Remove orphaned genes and MassMetabolites from the
			MassModel as well.
		update_stoichiometry : bool, optional
			If True, will update the matrix after adding the new reactions.
		"""
		# If the reaction list is not a list
		if not hasattr(reaction_list, '__iter__'):
			reaction_list = [reaction_list]
		reaction_list = DictList(reaction_list)
		if len(reaction_list) == 0:
			return None

		# Check whether a reaction already exists in the massmodel, and
		# ignore those that do not
		reaction_list = [rxn for rxn in reaction_list
							if rxn.id in self.reactions]

		context = get_context(self)

		# Remove model association
		for rxn in reaction_list:
			rxn._model = None
			# Remove metabolite association
			for metab in rxn._metabolites:
				if rxn in metab._reaction:
					metab._reaction.remove(rxn)
					# Remove orphaned metabolites and their initial conditions
					if remove_orphans and len(metab._reaction) == 0:
						self.remove_metabolites(metab)
					if context:
						context(partial(metab._reaction.add, rxn))

			# Remove gene association
			for gene in rxn._genes:
				if rxn in gene._reaction:
					gene._reaction.remove(rxn)
					# Remove orphaned genes
					if remove_orphans and len(gene._reaction) == 0:
						self.genes.remove(gene)
						if context:
							context(partial(self.genes.add, gene))
					if context:
						context(partial(gene._reaction.add, rxn))
			if context:
				context(partial(setattr, rxn, '_model', self))

		# Remove reactions from the model
		self.reactions -= reaction_list
		if update_stoichiometry:
			self.update_S(reaction_list=None, update_model=True)

		if context:
			context(partial(self.reactions.__iadd__, reaction_list))
			for rxn in reaction_list:
				context(partial(setattr, rxn, '_model', self))
			if update_stoichiometry:
				context(partial(self.update_S, reaction_list,
							None, None, True))

	def add_exchange(self, metabolite, exchange_type="exchange",
						external_concentration=0.,
						update_stoichiometry=True):
		"""Add an exchange reaction for a given metabolite using the
		pre-defined exchange types "exchange" for reversibly into or exiting
		the compartment, "source" for irreversibly into the compartment,
		and "demand" for irreversibly exiting the compartment.

		The change is reverted upon exit when using the MassModel as a context.

		Parameters
		----------
		metabolite : MassMetabolite
			Any given metabolite to create an exchange for.
		exchange_type : string, {"demand", "source", "exchange"}, optional
			The type of exchange reaction to create are not case sensitive.
		external_concentration : float, optional
			The concentration to set for the external species.
		reversible : bool, optional
			If True, exchange is reversible. When using a user-defined type,
			must specify the reversiblity
		update_stoichiometry : bool, optional
			If True, will update the matrix after adding the new reactions.

		Returns
		-------
		mass.MassReaction
			The new MassReaction object representing the exchange reaction
			generated by the function

		"""
		# Check whether metabolite is a MassMetabolite object
		if not isinstance(metabolite, MassMetabolite):
			raise TypeError("metabolite must be a MassMetabolite object")

		type_dict = {"source":["S", 1, False],
					"demand":["DM", -1, False],
					"exchange":["EX", -1, True]}

		# Set the type of exchange
		if not isinstance(exchange_type, string_types):
			raise TypeError("exchange_type must be a string")
		else:
			exchange_type = exchange_type.lower()

		if exchange_type in type_dict:
			values = type_dict[exchange_type]
			rxn_id = "{}_{}".format(values[0], metabolite.id)
			_c = re.search("^\w*\S(?!<\_)(\_\S+)$", metabolite.id)
			if _c is not None and not re.search("\_L$|\_D$", _c.group(1)):
				rxn_id = re.sub(_c.group(1), "_e", rxn_id)
			if rxn_id in self.reactions:
				warn("Reaction %s already exists in model" % rxn_id)
				return None
			c = values[1]
			reversible = values[2]
		else:
			raise ValueError("Exchange type must be either "
							"'exchange', 'source',  or 'sink'")
		rxn_name = "{} {}".format(metabolite.name, exchange_type)

		rxn = MassReaction(id=rxn_id, name=rxn_name,
					subsystem="Transport/Exchange",reversible=reversible)
		rxn.add_metabolites({metabolite: c})
		self.add_reactions([rxn], update_stoichiometry)
		self.add_fixed_concentrations(fixed_conc_dict={
			rxn.get_external_metabolite : external_concentration})

		return rxn

	def generate_rate_laws(self, reaction_list=None, rate_type=1,
							sympy_expr=False, update_reactions=False):
		"""Get the rate laws for a list of reactions in a MassModel and return
		them as human readable strings or as sympy expressions for simulations.

		The type determines which rate law format to return.
		For example: A <=> B

		type=1: kf*(A - B/Keq)
		type=2: kf*A - kr*B
		type=3: kr*(Keq*A - B)

		Parameters
		----------
		reaction_list : list, optional
			The list of reactions to obtain the rates for. If none specified,
			will return the rates for all reactions in the MassModel
		rate_type : int {1, 2, 3}, optional
			The type of rate law to display. Must be 1, 2, of 3.
			type 1 will utilize kf and Keq,
			type 2 will utilize kf and kr,
			type 3 will utilize kr and Keq.
		sympy_expr : bool, optional
			If True, will output a sympy expression, otherwise
			will output a human readable string.

		Returns
		-------
		dict of reaction rates where keys are reaction identifiers and
			values are the strings or sympy expressions
		"""
		# Check inputs
		if not isinstance(rate_type, (integer_types, float)):
			raise TypeError("rate_type must be an int or float")
		elif not isinstance(sympy_expr, bool):
			raise TypeError("sympy_expr must be a bool")
		else:
			rate_type = int(rate_type)
			if rate_type not in {1, 2, 3}:
				raise ValueError("rate_type must be 1, 2, or 3")

		# Use massmodel reactions if no reaction list is given
		if reaction_list is None:
			reaction_list = self.reactions
		# If the reaction list is not a list
		elif not hasattr(reaction_list, '__iter__'):
			reaction_list = DictList([reaction_list])
		else:
			reaction_list = DictList(reaction_list)

		if len(reaction_list) == 0:
			return None
		if update_reactions:
			self._rtype = rate_type
		# Get the rates
		rates = {rxn :
				rxn.generate_rate_law(rate_type, sympy_expr, update_reactions)
				for rxn in reaction_list}
		if self.custom_rates != {}:
			rates.update(self.custom_rates)
		return rates

	def get_mass_action_ratios(self, reaction_list=None,sympy_expr=False):
		"""Get the mass action ratios for a list of reactions in a MassModel
		and return them as human readable strings or as sympy expressions
		for simulations

		Parameters
		----------
		reaction_list : list of MassReaction, optional
			The list of MassReactions to obtain the disequilibrium ratios for.
			If None, will return the rates for all reactions in the MassModel
		sympy_expr : bool, optional
			If True, will output sympy expressions, otherwise
			will output a human readable strings.
		Returns
		-------
		dict of disequilibrium ratios where keys are reaction identifiers and
			values are mass action ratios as strings or sympy expressions
		"""
		# Use massmodel reactions if no reaction list is given
		if reaction_list is None:
			reaction_list = self.reactions
		# If the reaction list is not a list
		elif not hasattr(reaction_list, '__iter__'):
			reaction_list = DictList([reaction_list])
		else:
			reaction_list = DictList(reaction_list)

		if len(reaction_list) == 0:
			return None
		# Get the mass action ratios
		return {rxn : rxn.get_mass_action_ratio(sympy_expr)
				for rxn in reaction_list}

	def get_disequilibrium_ratios(self, reaction_list=None, sympy_expr=False):
		"""Get the disequilibrium ratios for a list of reactions in a MassModel
		and return them as human readable strings or as sympy expressions
		for simulations

		Parameters
		----------
		reaction_list : list of MassReactions, optional
			The list of MassReactions to obtain the disequilibrium ratios for.
			If None, will return the rates for all reactions in the MassModel
		sympy_expr : bool, optional
			If True, will output sympy expressions, otherwise
			will output a human readable strings.
		Returns
		-------
		dict of disequilibrium ratios where keys are reaction identifiers and
			values are disequilibrium ratios as strings or sympy expressions
		"""
		# Use massmodel reactions if no reaction list is given
		if reaction_list is None:
			reaction_list = self.reactions
		# If the reaction list is not a list
		elif not hasattr(reaction_list, '__iter__'):
			reaction_list = DictList([reaction_list])
		else:
			reaction_list = DictList(reaction_list)

		if len(reaction_list) == 0:
			return None
		# Get the disequilibrium ratios
		return {rxn : rxn.get_disequilibrium_ratio(sympy_expr)
				for rxn in reaction_list}

	def add_custom_rate(self, reaction, custom_rate,
						custom_parameters=None):
		"""Add a custom rate to the MassModel for a reaction.

		Note: Metabolites must already be in the MassReaction

		The change is reverted upon exit when using the MassModel as a context.

		Parameters
		----------
		reaction : mass.MassReaction
			The MassReaction which the custom rate associated with
		custom_rate_law :  string
			The custom rate law as a string. The string representation of the
			custom rate lawwill be used to create a sympy expression that
			represents the custom rate law
		custom_parameters :  dictionary of strings
			A dictionary of where keys are custom parameters in the custom rate
			as strings, and values are their numerical value. The string
			representation of the custom parameters will be used to create the
			symbols in the sympy expressions of the custom rate law.
			If None, parameters are assumed to be already in the MassModel,
			or one of the MassReaction rate or equilibrium constants.
		"""
		# Get the custom parameters
		if custom_parameters is not None:
			custom_param_list = list(iterkeys(custom_parameters))
		else:
			custom_parameters = {}
			custom_param_list = []
		# Use existing ones if they are in the rate law
		existing_customs = self.custom_parameters
		if len(existing_customs) != 0:
			for custom_param in iterkeys(existing_customs):
				if re.search(custom_param, custom_rate) and \
					custom_param not in custom_param_list:
					custom_param_list.append(custom_param)

		custom_rate_expression = expressions.create_custom_rate(reaction,
												custom_rate, custom_param_list)

		self._custom_rates.update({reaction : custom_rate_expression})
		self._custom_parameters.update(custom_parameters)

		context = get_context(self)
		if context:
			context(partial(self._custom_rates.pop, reaction))
			for key in custom_param_list:
				if key in iterkeys(self._custom_parameters):
					context(partial((self._custom_parameters.pop, key)))
			context(partial(self._custom_parameters.update, existing_customs))


	def remove_custom_rate(self, reaction):
		"""Remove a custom rate to the MassModel for a reaction If no other
		custom rates rely on those custom parameters, remove those custom
		parameters from the model as well.

		The change is reverted upon exit when using the MassModel as a context.

		Parameters
		----------
		reaction : mass.MassReaction
			The MassReaction which the custom rate associated with
		"""
		# Remove the custom rate law
		custom_rate_to_remove = self.custom_rates[reaction]
		del self.custom_rates[reaction]

		# Remove custom parameters if they are not associated with any other
		# custom rate expression
		symbols = custom_rate_to_remove.atoms(sp.Symbol)
		if len(self.custom_rates) != 0:
			other_syms = set()
			for custom_rate in itervalues(self.custom_rates):
				for sym in list(custom_rate.atoms(sp.Symbol)):
					other_syms.add(sym)
			for sym in other_syms:
				if sym in symbols.copy():
					symbols.remove(sym)

		context = get_context(self)
		if context:
			existing = dict((str(sym), self._custom_parameters[str(sym)])
							for sym in symbols)

		for sym in symbols:
			del self._custom_parameters[str(sym)]

		if context:
			context(partial(self._custom_rates.update, {reaction:
											custom_rate_to_remove}))
			context(partial(self._custom_parameters.update, existing))

	def reset_custom_rates(self):
		"""Reset all custom rate laws and parameters in a model.

		Warnings
		--------
		Will remove all custom rates and custom rate parameters in the
		MassModel. To remove a specific rate(s) without affecting the others,
		use the remove_custom_rate method instead.
		"""
		self._custom_rates = {}
		self._custom_parameters = {}
		print("Reset all custom rate laws")

	def get_elemental_matrix(self, matrix_type=None, dtype=None):
		"""Get the elemental matrix of a model

		Parameters
		----------
		matrix_type: string {'dense', 'dok', 'lil', 'DataFrame'}, optional
			If None, will utilize the matrix type initialized with the original
			model. Otherwise reconstruct the S matrix with the specified type.
			Types can include 'dense' for a standard  numpy.array, 'dok' or
			'lil' to obtain the scipy sparse matrix of the corresponding type,
			DataFrame for a pandas 'DataFrame' where species (excluding genes)
			are row indicies and reactions are column indicices, and 'symbolic'
			for a sympy.Matrix'.
		dtype : data-type, optional
			The desired data-type for the array. If None, defaults to float

		Returns
		-------
		matrix of class 'dtype'
			The elemental matrix for the given MassModel
		"""
		# Set defaults for the elemental matrix
		if matrix_type is None:
			matrix_type = 'dataframe'
		if dtype is None:
			dtype = np.int64

		# No need to construct a matrix if there are no metabolites
		if len(self.metabolites) == 0:
			return None

		CHOPNSq = ['C', 'H', 'O', 'P', 'N', 'S', 'q' ]

		(matrix_constructor, dtype) = self._setup_matrix_constructor(
												matrix_type, dtype)

		e_matrix = matrix_constructor((len(CHOPNSq),len(self.metabolites)),
									dtype=dtype)
		# Get index for elements and metabolites
		e_ind = CHOPNSq.index
		m_ind = self.metabolites.index

		# Build the matrix
		for metab in self.metabolites:
			for element in CHOPNSq:
				if element in iterkeys(metab.elements):
					amount = metab.elements[element]
				elif element == 'q' and metab.charge is not None:
					amount = metab.charge
				else:
					amount = 0
				e_matrix[e_ind(element), m_ind(metab)] = amount
		# Convert matrix to dataframe if matrix type is a dataframe
		if matrix_type == 'dataframe':
			metab_ids = [metab.id for metab in self.metabolites]
			e_matrix = pd.DataFrame(e_matrix, index=CHOPNSq, columns=metab_ids)
		if matrix_type == 'symbolic':
			e_matrix = sp.Matrix(e_matrix)

		return e_matrix

	def add_fixed_concentrations(self, fixed_conc_dict=None):
		"""Add fixed concentrations for metabolites, setting their ODEs
		to a constant value during simulation of the MassModel.

		The metabolites must already exist in the model or be an
		"external" metabolite for an exchange reaction"

		Parameters
		----------
		fixed_conc_dict : dictionary
			A dictionary of fixed concentrations where
			metabolites are keys and fixed concentrations are values
		"""
		# Check inputs
		if fixed_conc_dict is None:
			return None
		if not isinstance(fixed_conc_dict, dict):
			raise TypeError("fixed_conc_dict must be a dictionary")
		for metab, fixed_conc in iteritems(fixed_conc_dict):
			if metab not in self.get_external_metabolites and \
				metab not in self.metabolites:
				raise ValueError("Did not find %s in model metabolites"
								" or exchanges" % metab)
			if not isinstance(fixed_conc, (integer_types, float)):
				raise TypeError("Fixed concentration must be an int or float")
			elif fixed_conc < 0.:
				raise ValueError("External concentration must be non-negative")
			else:
				fixed_conc = float(fixed_conc)


		# Keep track of existing initial conditions for HistoryManager
		context = get_context(self)
		if context:
			existing_ics = {metab : self.fixed_concentrations[metab]
							for metab in fixed_conc_dict
							if metab in self.fixed_concentrations}

		self.fixed_concentrations.update(fixed_conc_dict)

		if context:
			for key in iterkeys(fixed_conc_dict):
				if key not in iterkeys(existing_ics):
					context(partial(self.fixed_concentrations.pop, key))
				context(partial(self.fixed_concentrations.update,
								existing_ics))

	def remove_fixed_concentrations(self, metabolites=None):
		"""Remove a fixed concentration for a specific metabolite

		Parameters
		----------
		metabolites : list of metabolites identifiers
			A list containing MassMetabolites or their identifiers. Can also
			be an "external" metabolite for an exchange reaction
		"""
		# Check inputs
		if metabolites is None:
			return None
		if not hasattr(metabolites, '__iter__'):
			metabolites = [metabolites]

		for metab in metabolites:
			if metab not in self.get_external_metabolites and \
				metab not in self.metabolites:
				raise ValueError("Did not find %s in model metabolites"
								" or exchanges" % metab)

		# Keep track of existing initial conditions for HistoryManager
		context = get_context(self)
		if context:
			existing_ics = {metab : self.fixed_concentrations[metab]
							for metab in metabolites
							if metab in self.fixed_concentrations}

		for metab in metabolites:
			del self.fixed_concentrations[metab]

		if context:
			context(partial(self.fixed_concentrations.update, existing_ics))

	def repair(self, rebuild_index=True, rebuild_relationships=True):
		"""Update all indexes and pointers in a MassModel

		Identical to the method in cobra.core.model

		Parameters
		----------
		rebuild_index : bool, optional
			If True, rebuild the indecies kept in reactions,
			metabolites and genes.
		rebuild_relationships : bool, optional
			If True, reset all associations between the reactions, metabolites,
			genes, and the MassModel and re-add them
		"""
		if not isinstance(rebuild_index, bool) or \
			not isinstance(rebuild_relationships, bool):
			raise TypeError("rebuild_index and rebuild_relationships "
							"must be True or False")
		# Rebuild DictList indicies
		if rebuild_index:
			self.reactions._generate_index()
			self.metabolites._generate_index()
			self.genes._generate_index()
		# Rebuild relationships between reactions and their associated
		# genes and metabolites
		if rebuild_relationships:
			for metab in self.metabolites:
				metab._reaction.clear()
			for gene in self.genes:
				gene._reaction.clear()
			for rxn in self.reactions:
				for metab in rxn.metabolites:
					metab._reaction.add(rxn)
				for gene in rxn.genes:
					gene._reaction.add(rxn)
		# Make all objects point to model
		for dictlist in (self.reactions, self.genes, self.metabolites):
			for item in dictlist:
				item._model = self

	def copy(self):
		"""Provides a partial 'deepcopy' of the MassModel. All of
		the MassMetabolite, MassReaction and Gene objects, the
		initial conditions, custom rates, and the S matrix are created anew
		but in a faster fashion than deepcopy
		"""
		# Define a new model
		new_model = self.__class__()
		# Define items to not copy by their references
		do_not_copy_by_ref = {"metabolites", "reactions", "genes",
							"initial_conditions","_custom_rates",
							"_custom_parameters", "_S",
							"notes", "annotations"}
		for attr in self.__dict__:
			if attr not in do_not_copy_by_ref:
				new_model.__dict__[attr] = self.__dict__[attr]
		new_model.notes = deepcopy(self.notes)
		new_model.annotation = deepcopy(self.annotation)

		# Copy metabolites
		new_model.metabolites = DictList()
		do_not_copy_by_ref = {"_reaction", "_model"}
		for metab in self.metabolites:
			new_metab = metab.__class__()
			for attr, value in iteritems(metab.__dict__):
				if attr not in do_not_copy_by_ref:
					new_metab.__dict__[attr] = copy(
							value) if attr == "formula" else value
			new_metab._model = new_model
			new_model.metabolites.append(new_metab)
			# Copy the initial condition
			if metab in iterkeys(self.initial_conditions) :
				ic = self.initial_conditions[metab]
				new_model.initial_conditions[new_metab] = ic

		# Copy the genes
		new_model.genes = DictList()
		for gene in self.genes:
			new_gene = gene.__class__(None)
			for attr, value in iteritems(gene.__dict__):
				if attr not in do_not_copy_by_ref:
					new_gene.__dict__[attr] = copy(
							value) if attr == "formula" else value
			new_gene._model = new_model
			new_model.genes.append(new_gene)

		# Copy the reactions
		new_model.reactions = DictList()
		do_not_copy_by_ref = {"_model", "_metabolites", "_genes"}
		for rxn in self.reactions:
			new_rxn = rxn.__class__()
			for attr, value in iteritems(rxn.__dict__):
				if attr not in do_not_copy_by_ref:
					new_rxn.__dict__[attr] = copy(value)
			new_rxn._model = new_model
			new_model.reactions.append(new_rxn)
			# Copy the custom rates
			if rxn in iterkeys(self.custom_rates):
				new_model.custom_rates[new_rxn] = self.custom_rates[rxn]
			# Update awareness
			for metab, stoic in iteritems(rxn._metabolites):
				new_metab = new_model.metabolites.get_by_id(metab.id)
				new_rxn._metabolites[new_metab] = stoic
				new_metab._reaction.add(new_rxn)
			for gene in rxn._genes:
				new_gene = new_model.genes.get_by_id(gene.id)
				new_rxn._genes.add(new_gene)
				new_gene._reaction.add(new_rxn)

		# Copy custom parameters if there are custom rates
		if len(new_model.custom_rates) != 0:
			new_model._custom_parameters = self._custom_parameters

		# Create the new stoichiometric matrix for the model
		new_model._S = self._create_stoichiometric_matrix(
						matrix_type=self._matrix_type,
						dtype=self._dtype, update_model=True)


		# Refresh contexts for the new model copy
		new_model._contexts = []
		return new_model

	def merge(self, second_model, prefix_existing=None, inplace=False,
					new_model_id=None):
		"""Merge two massmodels to create one MassModel object with
		the reactions and metabolites from both massmodels.

		Initial conditions, custom rate laws, and custom rate parameters will
		also be added from the second model into the first model. However,
		initial conditions and custom rate laws are assumed to be the same if
		they have the same identifier and therefore will not be added.

		Parameters
		----------
		second_model : MassModel
			The other MassModel to add reactions and metabolites from
		prefix_existing : string, optional
			Use the string to prefix the reaction identifier of a reaction
			in the second_model if that reaction already exists within
			the first model.
		inplace : bool, optional
			If True, add the contents directly into the first model.
			If False, a new MassModel object is created and the first model is
			left untouched. When done within the model as context, changes to
			the models are reverted upon exit.
		new_model_id : String or None, optional
			Will create a new model ID for the merged model if a string
			is given. Otherwise will just use the model IDs of the first model
			if inplace is True or create a combined ID if inplace is false.
		"""
		# Check inputs to ensure they are correct types
		if not isinstance(second_model, MassModel):
			raise TypeError("The second model to merge must be a MassModel")
		if not isinstance(prefix_existing, (string_types, type(None))):
			raise TypeError("prefix_existing must be a string or none")
		if not isinstance(inplace, bool):
			raise TypeError("inplace must be a bool")
		if not isinstance(new_model_id, (string_types, type(None))):
			raise TypeError("new_model_id must be a string or none")

		if inplace:
			merged_model = self
		else:
			merged_model = self.copy()

		# Set the model ID
		if new_model_id is None:
			if inplace:
				new_model_id = self.id
			else:
				new_model_id = "{} & {}".format(self.id, second_model.id)
		merged_model.id = new_model_id

		# Add the reactions of the second model to the first model
		new_reactions = deepcopy(second_model.reactions)
		if prefix_existing is not None:
			existing_reactions = new_reactions.query(
				lambda rxn: rxn.id in self.reactions)
			for rxn in existing_reactions:
				rxn.id = "{}_{}".format(prefix_existing, rxn.id)
		merged_model.add_reactions(new_reactions, True)
		merged_model.repair()
		# Add custom rates, custom parameters, and initial conditions
		existing_ics =[m.id for m in iterkeys(merged_model.initial_conditions)]
		for m, ic in iteritems(second_model.initial_conditions):
			if m.id not in existing_ics:
				merged_model.update_initial_conditions({m : ic})

		existing_cr = [r.id for r in iterkeys(merged_model._custom_rates)]
		for r, rate in iteritems(second_model._custom_rates):
			if r.id not in existing_cr:
				merged_model._custom_rates.update({r : rate})

		existing_cp = [p for p in iterkeys(merged_model._custom_parameters)]
		for p, val in iteritems(second_model._custom_parameters):
			if p not in existing_cp:
				merged_model._custom_parameters.update({p : val})
		# Add old models to the module set
		if second_model.id not in merged_model.modules:
			merged_model.modules.add(second_model.id)
		if not inplace:
			merged_model.modules.add(self.id)
		return merged_model

	def calc_PERCS(self, steady_state_concentrations=None,
					steady_state_fluxes=None, at_equilibrium_default=100000.,
					update_reactions=False):
		"""Calculate the pseudo rate constants (rxn.forward_rate_constant)
		for reactions in the MassModel using steady state concentrations and
		steady state fluxes.

		Parameters
		----------
		steady_state_concentrations : dict, optional
			A dictionary of steady state concentrations where MassMetabolites
			are keys and the concentrations are the values. If None, will
			utilize the initial conditions in the MassModel.
		steady_state_fluxes : dict or None
			A dictionary of steady state fluxes where MassReactions are keys
			and fluxes are the values. If None, will utilize the steady state
			reactions stored in each reaction in the model.
		at_equilibrium_default : float, optional
			The value to set the pseudo order rate constant if the reaction is
			at equilibrium. Will default to 100,000
		update_parameters : bool, optional
			Whether to update the forward rate constants in the MassReactions.
			If True, will update the forward rate constants inside the
			MassReactions with the calculated pseudo order rate constants
		"""
		# Check inputs
		if steady_state_concentrations is None:
			steady_state_concentrations = self.initial_conditions
		if not isinstance(steady_state_concentrations, dict):
			raise TypeError("Steady state concentrations must be a dictionary"
							"where keys are MassMetabolites and values are "
							"concentrations")

		if not isinstance(steady_state_fluxes, (dict, type(None))):
			raise TypeError("Steady state fluxes must be a dictionary where"
							" keys are MassReactions and values are fluxes")

		if not isinstance(at_equilibrium_default, (integer_types, float)):
			raise TypeError("at_equilibrium_default must be an int or float")

		if not isinstance(update_reactions, bool):
			raise TypeError("update_reactions must be a bool")

		# Use model steady state fluxes and check for missing parameters
		if steady_state_fluxes is None:
			steady_state_fluxes = self.steady_state_fluxes
			missing_params = qcqa.get_missing_parameters(self, Keq=True,
										ssflux=True, custom_parameters=True)
		# Use the given steady state fluxes and check for missing parameters
		else:
			missing_params = qcqa.get_missing_parameters(self, Keq=True,
										ssflux=False, custom_parameters=True)
			for rxn in self.reactions:
				if rxn not in iterkeys(steady_state_fluxes):
					if rxn in iterkeys(missing_params):
						missing = missing_params[rxn]
						missing.append( "ssflux")
						missing_params[rxn] = missing
					else:
						missing_params[rxn] = ["ssflux"]

		# Use model initial conditions for the steady state concentratiosn
		# and check for missing initial conditions
		if steady_state_concentrations is None:
			missing_concs = qcqa.get_missing_initial_conditions(self)
		# Use the given steady state concentrations and
		# check for missing concentrations
		else:
			missing_concs = [m for m in self.metabolites
							if m not in iterkeys(steady_state_concentrations)]

		# If parameters or concentrations are missing, print a warning,
		# inform what values are missing, and return none
		if len(missing_params) != 0 or len(missing_concs) != 0:
			warn("\nCannot calculate PERCs due to missing values")
			reports = qcqa._qcqa_summary([missing_concs, missing_params])
			for report in reports:
				print("%s\n" % report)
			return None

		#  Group symbols in rate_laws
		if self._rtype != 1:
			self._rtype = 1
		odes, rates, symbols = expressions._sort_symbols(self)
		metabolites = symbols[0]
		rate_params = symbols[1]
		fixed_concs = symbols[2]
		custom_params = symbols[3]

		# Strip the time dependency
		rates = expressions.strip_time(rates)
		percs_dict = {}
		# Get values to subsitute into equation.
		for rxn, rate in iteritems(rates):
			values = {}
			symbols = rate.atoms(sp.Symbol)
			for sym in symbols:
				if sym in rate_params:

					if re.search("Keq", str(sym)):
						values.update({sym : rxn.Keq})
					else:
						perc = sym
				elif sym in custom_params:
					values.update({sym : self.custom_parameters[str(sym)]})
				elif sym in fixed_concs:
					values.update({sym : self.fixed_concentrations[str(sym)]})
				else:
					metab = self.metabolites.get_by_id(str(sym))
					values.update({sym : self.initial_conditions[metab]})

			flux = steady_state_fluxes[rxn]

			# Set equilbrium default if no flux
			if flux == 0:
				sol = {float(at_equilibrium_default)}
			# Otherwise calculate the PERC
			else:
				equation = sp.Eq(steady_state_fluxes[rxn], rate.subs(values))
				sol = set(sp.solveset(equation, perc, domain=sp.S.Reals))
			percs_dict.update({str(perc): float(sol.pop())})

			if update_reactions:
				rxn.kf = percs_dict[str(perc)]

		return percs_dict

	def string_to_mass(self, reaction_strings, term_split="+"):
		"""Create reactions and metabolite objects from strings.

		To correctly parse a string, it must be in the following format:
			"RID: s[ID, **kwargs] + s[ID, **kwargs] <=>  s[ID, **kwargs]

		where kwargs can be the metabolite attributes 'name', 'formula',
		'charge'. For example:
			"v1: s[x1, name=xOne, charge=2] <=> s[x2, formula=X]"

		To add a compartment for a species, add "[c]" where c is a letter
		representing the compartment for the species. For example:
			"v1: s[x1][c] <=> s[x2][c]"

		When creating bound enzyme forms, it is recommended to use '&' in the
		species ID to represent the bound enzyme-metabolite. For example:
			"E1: s[ENZYME][c] + s[metabolite][c] <=> s[ENZYME&metabolite][c]"

		Note that a reaction ID and a metabolite ID are always required

		Parameters
		----------
		reaction_strings : string or list of strings
			String or list of strings representing the reaction. Reversibility
			is inferred from the arrow, and metabolites in the model are used
			if they exist or created if they do not.
		term_split : string, optional
			dividing individual metabolite entries
		"""
		if not isinstance(reaction_strings, list):
			reaction_strings = [reaction_strings]

		for rxn_string in reaction_strings:
			if not isinstance(rxn_string, string_types):
				raise TypeError("reaction_strings must be a string or "
								"list of strings")

		_metab_arguments = [_name_arg, _formula_arg, _charge_arg]

		for rxn_string in reaction_strings:
			try:
				res = _rxn_id_finder.search(rxn_string)
				rxn_id = res.group(1)
				rxn_string = rxn_string[res.end():]
			except:
				ValueError("Could not find an ID for '%s'" % rxn_string)
			# Determine reversibility
			if _reversible_arrow.search(rxn_string):
				arrow_loc = _reversible_arrow.search(rxn_string)
				reversible = True
				# Reactants left of the arrow, products on the right
				reactant_str = rxn_string[:arrow_loc.start()].strip()
				product_str = rxn_string[arrow_loc.end():].strip()
			elif _forward_arrow.search(rxn_string):
				arrow_loc = _forward_arrow.search(rxn_string)
				reversible = False
				# Reactants left of the arrow, products on the right
				reactant_str = rxn_string[:arrow_loc.start()].strip()
				product_str = rxn_string[arrow_loc.end():].strip()
			elif _reverse_arrow.search(rxn_string):
				arrow_loc = _reverse_arrow.search(rxn_string)
				reversible = False
				# Reactants right of the arrow, products on the left
				reactant_str = rxn_string[arrow_loc.end():].strip()
				product_str = rxn_string[:arrow_loc.start()].strip()
			else:
				raise ValueError("Unrecognized arrow for '%s'" % rxn_string)
			new_reaction = MassReaction(rxn_id, reversible=reversible)

			for substr, factor in ((reactant_str, -1), (product_str, 1)):
				if len(substr) == 0:
					continue
				for term in substr.split(term_split):
					term = term.strip()
					if term.lower() == "nothing":
						continue
					# Find compartment if it exists
					if _compartment_finder.search(term):
						compartment = _compartment_finder.search(term).group(1)
						compartment = compartment.strip("[|]")
						term = _compartment_finder.sub("]",term)
					else:
						compartment = None
					# Get the metabolite to make and the cofactor
					if re.search("\d ", term):
						num = float(re.search("(\d) ", term).group(1))*factor
						metab_to_make = term[re.search("(\d) ", term).end():]
					else:
						num = factor
						metab_to_make = term

					# Find the metabolite ID
					try:
						met_id = _met_id_finder.search(metab_to_make).group(1)
					except:
						raise ValueError("Could not locate metab ID")
					# Use the metabolite in the model if it exists
					try:
						metab = self.metabolites.get_by_id(met_id)
					# Otherwise create a new metabolite
					except KeyError:
						metab = MassMetabolite(met_id)

					# Set attributes for the metabolite
					for arg in _metab_arguments:
						if arg.search(metab_to_make):
							attr = _equals.split(arg.pattern)[0]
							val = arg.search(metab_to_make).group(1)
							metab.__dict__[attr] = val
					new_reaction.add_metabolites({metab:num})
			self.add_reactions(new_reaction)

	## Internal
	def _create_stoichiometric_matrix(self, matrix_type=None, dtype=None,
									update_model=True):
		"""Return the stoichiometrix matrix for a given massmodel

		The rows represent the chemical species and the columns represent the
		reactions. S[i, j] therefore contain the quantity of species 'i'
		produce (positive) or consumed (negative) by reaction 'j'.

		Matrix types can include 'dense' for a standard  numpy.array, 'dok' or
		'lil' to obtain the scipy matrix of the corresponding type, DataFrame
		for a pandas 'Dataframe' where species (excluding genes) are row
		indicies and reactions are column indicices, and 'symbolic' for a
		sympy.Matrix.

		Parameters
		----------
		model : mass.MassModel
			The MassModel object to construct the matrix for
		matrix_type: {'dense', 'dok', 'lil', 'dataframe', 'symbolic'}, optional
		   Construct the S matrix with the specified matrix type. If None, will
		   utilize the matrix type in the massmodel. If massmodel does not have
		   a specified matrix type, will default to 'dense'
		   Not case sensitive
		dtype : data-type, optional
			Construct the S matrix with the specified data type. If None, will
			utilize  the data type in the massmodel. If massmodel does not have
			a specified data type, will default to float64
		update_model : bool, optional
			If True, will update the stored S matrix in the model with the new
			matrix type and dtype.

		Returns
		-------
		matrix of class 'dtype'
			The stoichiometric matrix for the given MassModel
		"""
		# Check input of update model
		if not isinstance(update_model, bool):
			raise TypeError("update_model must be a bool")

		# Set up for matrix construction if matrix types are correct.
		(matrix_constructor, dtype) = self._setup_matrix_constructor(
											matrix_type, dtype)
		n_metabolites = len(self.metabolites)
		n_reactions = len(self.reactions)

		# No need to construct a matrix if there are no metabolites or species
		if n_metabolites == 0 or n_reactions == 0:
			return None

		else:
			# Construct the stoichiometric matrix
			s_matrix = matrix_constructor((n_metabolites, n_reactions),
											dtype=dtype)
			# Get index for metabolites and reactions
			m_ind = self.metabolites.index
			r_ind = self.reactions.index

			# Build matrix
			for rxn in self.reactions:
				for metab, stoic in iteritems(rxn.metabolites):
					s_matrix[m_ind(metab), r_ind(rxn)] = stoic

			# Convert matrix to dataframe if matrix type is a dataframe
			if matrix_type == 'dataframe':
				metabolite_ids =[metab.id for metab in self.metabolites]
				reaction_ids = [rxn.id for rxn in self.reactions]
				s_matrix = pd.DataFrame(s_matrix, index = metabolite_ids,
												columns = reaction_ids)
			if matrix_type == 'symbolic':
				s_matrix = sp.Matrix(s_matrix)

			# Update the model's stored matrix data if True
		if update_model:
			self._update_model_s(s_matrix, matrix_type, dtype)

		return s_matrix

	def _setup_matrix_constructor(self, matrix_type=None, dtype=None):
		"""Internal use. Check inputs and create a constructor for the
		specified matrix type.

		Parameters
		----------
		model : mass.MassModel
			The MassModel object to construct the matrix for
		matrix_type: {'dense', 'dok', 'lil', 'dataframe', 'symbolic'}, optional
		   Construct the matrix with the specified matrix type. If None, will
		   utilize  the matrix type in the massmodel. If massmodel does not
		   have a specified matrix type, will default to 'dense'
		   Not case sensitive
		dtype : data-type, optional
			Construct the S matrix with the specified data type. If None, will
			utilize  the data type in the massmodel. If massmodel does not have
			a specified data type, will default to float64
		Returns
		-------
		matrix of class 'dtype'
		"""
		# Dictionary for constructing the matrix
		matrix_constructor = {'dense': np.zeros, 'dok': dok_matrix,
								'lil': lil_matrix, 'dataframe': np.zeros,
								'symbolic': np.zeros}

		# Check matrix type input if it exists
		if matrix_type is not None:
			if not isinstance(matrix_type, string_types):
				raise TypeError("matrix_type must be a string")
			# Remove case sensitivity
			matrix_type = matrix_type.lower()
		else:
			# Use the models stored matrix type if None is specified
			if self._matrix_type is not None:
				matrix_type = self._matrix_type.lower()
			# Otherwise use the default type, 'dense'
			else:
				matrix_type = 'dense'
				self._matrix_type = 'dense'

		# Check to see if matrix type is one of the defined types
		if matrix_type not in matrix_constructor:
			raise ValueError("matrix_type must be a string of one of the "
							"following types: {'dense', 'dok', 'lil', "
							"'dataframe', 'symbolic'}")

		# Set the data-type if it is none
		if dtype is None:
			# Use the models stored data type if available
			if self._dtype is not None:
				dtype = self._dtype
			# Otherwise use the default type, np.float64
			else:
				dtype = np.float64
				self._dtype = np.float64

		constructor = matrix_constructor[matrix_type]
		return (constructor, dtype)

	def _update_stoichiometry(self, reaction_list, matrix_type=None):
		"""For internal uses only. To update the stoichometric matrix with
		additional reactions and metabolites efficiently by converting to
		a dok matrix, updating the dok matrix, and converting back to the
		desired type

		Parameters
		----------
		massmodel : mass.MassModel
			The massmodel to update
		reaction_list: list of MassReactions
			The reactions to add to the matrix
		matrix_type: {'dense', 'dok', 'lil', 'DataFrame', 'symbolic'}, optional
			The type of matrix

		Warnings
		--------
		This method is intended for internal use only. To safely update a
		matrix, use the massmodel.update_S method.
		"""
		# Set defaults
		shape = (len(self.metabolites), len(self.reactions))
		if matrix_type is None:
			matrix_type = 'dense'

		# Get the S matrix as a dok matrix
		s_matrix = self._convert_S('dok')
		# Resize the matrix
		s_matrix.resize(shape)

		# Update the matrix
		coefficient_dictionary = {}
		for rxn in reaction_list:
			rxn_index = self.reactions.index(rxn.id)
			for metab, coeff in rxn._metabolites.items():
				coefficient_dictionary[(self.metabolites.index(metab.id),
										rxn_index)] = coeff
		s_matrix.update(coefficient_dictionary)

		# Convert the matrix to the desired type
		s_matrix = self._convert_S(matrix_type)
		if matrix_type == 'dataframe':
			metabolite_ids =[metab.id for metab in self.metabolites]
			reaction_ids = [rxn.id for rxn in self.reactions]
			s_matrix = pd.DataFrame(s_matrix, index = metabolite_ids,
											columns = reaction_ids)
		if matrix_type == 'symbolic':
			s_matrix = sp.Matrix(s_matrix)

		return s_matrix

	def _convert_S(self, matrix_type):
		"""For internal uses only. To convert a matrix to a different type.

		Parameters
		----------
		s_matrix : matrix of class "dtype"
			The S matrix for conversion
		matrix_type: {'dense', 'lil', 'dok', 'DataFrame', 'symbolic'}
			The type of matrix to convert to

		Warnings
		--------
		This method is intended for internal use only. To safely convert a
		matrixto another type of matrix, use the massmodel.update_S method.
		"""
		s_matrix = self._S
		def _to_dense(s_mat=s_matrix):
			if isinstance(s_mat, np.ndarray):
				return s_mat
			elif isinstance(s_mat, pd.DataFrame):
				return s_mat.as_matrix()
			elif isinstance(s_mat, sp.Matrix):
				return np.array(s_mat)
			else:
				return s_mat.toarray()

		def _to_lil(s_mat=s_matrix):
			if isinstance(s_mat, sp.Matrix):
				s_mat = np.array(s_mat)
			return lil_matrix(s_mat)

		def _to_dok(s_mat=s_matrix):
			if isinstance(s_mat, sp.Matrix):
				s_mat = np.array(s_mat)
			return dok_matrix(s_mat)

		matrix_conversion = {'dense': _to_dense,
							'lil' : _to_lil,
							'dok' : _to_dok,
							'dataframe' : _to_dense,
							'symbolic' : _to_dense}

		s_matrix = matrix_conversion[matrix_type](s_mat=s_matrix)
		return s_matrix

	def _update_model_s(self, s_matrix, matrix_type, dtype):
		"""For internal use only. Update the model storage of the s matrix,
		matrix type, and data type

		Warnings
		--------
		This method is intended for internal use only. To safely convert a
		matrix to another type of matrix, use the massmodel.update_S method.
		"""
		self._S = s_matrix
		self._matrix_type = matrix_type
		self._dtype = dtype

	def _repr_html_(self):
		try:
			dim_S="{}x{}".format(self.S.shape[0],self.S.shape[1])
			rank=np.linalg.matrix_rank(self.S)
		except:
			dim_S = "0x0"
			rank = 0
		return """
			<table>
				<tr>
					<td><strong>Name</strong></td><td>{name}</td>
				</tr><tr>
					<td><strong>Memory address</strong></td><td>{address}</td>
				</tr><tr>
					<td><strong>Stoichiometric Matrix</strong></td>
					<td>{dim_S_matrix}</td>
				</tr><tr>
					<td><strong>Matrix Type</strong></td>
					<td>{S_type}</td>
				</tr><tr>
					<td><strong>Number of Metabolites</strong></td>
					<td>{num_metabolites}</td>
				</tr><tr>
					<td><strong>Number of Reactions</strong></td>
					<td>{num_reactions}</td>
				</tr><tr>
					<td><strong>Number of Genes</strong></td>
					<td>{num_genes}</td>
				</tr><tr>
					<td><strong>Number of Parameters</strong></td>
					<td>{num_param}</td>
				</tr><tr>
					<td><strong>Number of Initial Conditions</strong></td>
					<td>{num_ic}</td>
				</tr><tr>
					<td><strong>Number of Exchanges</strong></td>
					<td>{num_exchanges}</td>
				</tr><tr>
					<td><strong>Number of Fixed Concentrations</strong></td>
					<td>{num_fixed}</td>
				</tr><tr>
					<td><strong>Number of Irreversible Reactions</strong></td>
					<td>{num_irreversible}</td>
				</tr><tr>
					<td><strong>Matrix Rank</strong></td>
					<td>{mat_rank}</td>
				</tr><tr>
					<td><strong>Number of Custom Rates</strong></td>
					<td>{num_custom_rates}</td>
				</tr><tr>
					<td><strong>Modules</strong></td>
					<td>{modules}</td>
				</tr><tr>
					<td><strong>Compartments</strong></td>
					<td>{compartments}</td>
				</tr><tr>
					<td><strong>Units</strong></td>
					<td>{units}</td>
				</tr>
			</table>
		""".format(name=self.id, address='0x0%x' % id(self),
					dim_S_matrix=dim_S,
					S_type="{}, {}".format(self._matrix_type,
									 self._dtype.__name__),
					num_metabolites=len(self.metabolites),
					num_reactions=len(self.reactions),
					num_genes=len(self.genes),
					num_param=len(self.parameters),
					num_ic= len(self.initial_conditions),
					num_exchanges=len(self.exchanges),
					num_fixed=len(self.fixed_concentrations),
					num_irreversible=len(self.get_irreversible_reactions),
					mat_rank=rank,
					num_custom_rates=len(self.custom_rates),
					modules=", ".join([str(m) for m in self.modules
										if m is not None]),
					compartments=", ".join(v if v else k for \
										k,v in iteritems(self.compartments)),
					units=", ".join(v if v else k for \
										k,v in iteritems(self.units)))

	# Module Dunders
	def __enter__(self):
		"""Record all future changes to the MassModel, undoing them when a
		call to __exit__ is received

		Identical to the method in cobra.core.model
		"""
		# Create a new context and add it to the stack
		try:
			self._contexts.append(HistoryManager())
		except AttributeError:
			self._contexts = [HistoryManager()]

		return self

	def __exit__(self, type, value, traceback):
		"""Pop the top context manager and trigger the undo functions

		Identical to the method in cobra.core.model
		"""
		context = self._contexts.pop()
		context.reset()

	def __setstate__(self, state):
		"""Make sure all Objects in the MassModel point to the model

		Similar to the method in cobra.core.model
		"""
		self.__dict__.update(state)
		for attr in ['reactions', 'metabolites', 'genes']:
			for x in getattr(self, attr):
				x._model = self
		if not hasattr(self, "name"):
			self.name = ""

	def __getstate__(self):
		"""Get the state for serialization.

		Ensures that the context stack is cleared prior to serialization,
		since partial functions cannot be pickled reliably

		Identical to the method in cobra.core.model
		"""
		odict = self.__dict__.copy()
		odict['_contexts'] = []
		return odict
