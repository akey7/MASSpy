# -*- coding: utf-8 -*-

# Compatibility with Python 2.7
from __future__ import absolute_import

# Import necesary packages
import re
import sympy as sp
from six import iterkeys, iteritems, integer_types

# from cobra
from cobra.core.dictlist import DictList

# from mass
from mass.core import massmetabolite
from mass.core import massreaction
from mass.core import massmodel

# Class begins
## global symbol for time
t = sp.Symbol('t')

# Public
def generate_rate_law(reaction, rate_type=1, sympy_expr=False,
					update_reaction=False):
	"""Generates the rate law for the reaction as a human readable string.
	or as a sympy expression for simulation.

	The type determines which rate law format to return.
	For example: A <=> B

	type=1: kf*(A - B/Keq)
	type=2: kf*A - kr*B
	type=3: kr*(Keq*A - B)

	Parameters
	----------
	rate_type : int {1, 2, 3}
		The type of rate law to display. Must be 1, 2, of 3.
		type 1 will utilize kf and Keq,
		type 2 will utilize kf and kr,
		type 3 will utilize kr and Keq.
	sympy_expr : bool
		If True, will output a sympy expression, otherwise
		will output a human readable string.
	update_reaction : bool
		If True, will update the MassReaction in addition to returning the
		rate law. Otherwise just return the rate law.

	Returns
	-------
	string representation or sympy expression of the rate law
	"""
	# Check inputs
	if not isinstance(reaction, massreaction.MassReaction):
		raise TypeError("reaction must be a MassReaction")
	elif not isinstance(rate_type, (integer_types, float)):
		raise TypeError("rate_type must be an int or float")
	elif not isinstance(sympy_expr, bool):
		raise TypeError("sympy_expr must be a bool")
	elif not isinstance(update_reaction, bool):
		raise TypeError("update_reaction must be a bool")
	else:
		rate_type = int(rate_type)

	if len(reaction.metabolites) == 0:
		return None

	rxn = _ignore_h_and_h2o(reaction)
	rate_constructor = {
		1 : [_generate_rate_type_1, _generate_rate_expr_type_1],
		2 : [_generate_rate_type_2, _generate_rate_expr_type_2],
		3 : [_generate_rate_type_3, _generate_rate_expr_type_3]}

	if rate_type not in iterkeys(rate_constructor):
		raise ValueError("rate_type must be 1, 2, or 3")

	# Construct the rate law
	rate_law = rate_constructor[rate_type][0](rxn)
	rate_law_expr = rate_constructor[rate_type][1](rxn)

	if update_reaction:
		reaction._rate_expr = rate_law_expr
		reaction._rate_law = rate_law
		reaction._rtype = rate_type

	if sympy_expr:
		return rate_law_expr
	else:
		return rate_law

def get_mass_action_ratio(reaction, sympy_expr=False):
	"""Generate the mass action ratio for the reaction as
	a human readable string or a sympy expression for simulation.

	Parameters
	----------
	sympy_expr : bool
		If True, will output a sympy expression, otherwise
		will output a human readable string.

	Returns
	-------
	string representation or sympy expression of the mass action ratio
	"""
	if not isinstance(reaction, massreaction.MassReaction):
		raise TypeError("reaction must be a MassReaction")
	if not isinstance(sympy_expr, bool):
		raise TypeError("sympy_expr must be a bool")

	rxn = _ignore_h_and_h2o(reaction)
	ma_r = _get_mass_action_ratio_expr(rxn)
	if sympy_expr:
		return ma_r
	else:
		return str(ma_r)

def get_disequilibrium_ratio(reaction, sympy_expr=False):
	"""Generate the disequilibrium ratio for the reaction as
	a human readable string or a sympy expression for simulation.

	Parameters
	----------
	sympy_expr : bool
		If True, will output a sympy expression, otherwise
		will output a human readable string.

	Returns
	-------
	string representation or sympy expression of the disequilibrium ratio
	"""
	if not isinstance(reaction, massreaction.MassReaction):
		raise TypeError("reaction must be a MassReaction")
	if not isinstance(sympy_expr, bool):
		raise TypeError("sympy_expr must be a bool")
	rxn = _ignore_h_and_h2o(reaction)

	de_r = sp.Mul(_get_mass_action_ratio_expr(rxn),
							sp.Pow(sp.var(rxn._sym_Keq), -1))
	if sympy_expr:
		return de_r
	else:
		return str(de_r)


def generate_ode(metabolite):
	if not isinstance(metabolite, massmetabolite.MassMetabolite):
		raise TypeError("metabolite must be a MassMetabolite")

	if len(metabolite._reaction) == 0:
		return None

	metabolite._ode = sp.S.Zero
	for rxn in metabolite._reaction:
		if rxn._model is not None and rxn in rxn._model.custom_rates:
			print("FIXME: IMPLEMENT CUSTOM RATES")
			return None
		else:
			rate_law_expr = rxn.rate_expression

		if metabolite in rxn.reactants:
			rate_law_expr = sp.Mul(-1, rate_law_expr)
		metabolite._ode = sp.Add(metabolite._ode, rate_law_expr)
	return metabolite._ode

def strip_time(sympy_expr_dict):
	"""Strip the time dependency in sympy expresssions. Returns a dictionary
	with the expressions updated for each entry

	Parameters
	----------
	sympy_expr_dict : dict
		A dictionary of sympy expressions.
	"""
	for item, expression in iteritems(sympy_expr_dict):

		metab_funcs= expression.atoms(sp.Function)
		metab_syms = list(sp.Symbol(str(m_func)[:-3])
							for m_func in metab_funcs)
		metab_func_to_sym = dict((m_func, metab_syms[i])
								for i, m_func in enumerate(list(metab_funcs)))
		sympy_expr_dict[item] = expression.subs(metab_func_to_sym)
	return sympy_expr_dict

## Internal
def _generate_rate_type_1(reaction):
	"""Internal use. Generates the type 1 rate law for the reaction as
	a human readable string.

	To safely generate a rate law, use the generate_rate_law method.
	"""
	# Generate forward rate
	rate_law = ""
	# For exchange reactions
	if reaction.exchange and len(reaction.reactants) == 0:
		rate_law += "*%s(t)" % reaction.get_external_metabolite
	# For all other reactions
	else:
		for metab in reaction.reactants:
			coeff = abs(reaction.get_coefficient(metab.id))
			if coeff == 1:
				rate_law += "*%s(t)" % metab.id
			else:
				rate_law += "*%s(t)**%s" % (metab.id, coeff)

	# Return rate if reaction is irreversible
	if not reaction._reversible:
		return reaction._sym_kf + rate_law

	# Generate reverse rate
	rate_law = "%s*(%s - " % (reaction._sym_kf, rate_law.lstrip("*"))
	# For exchange reactions
	if reaction.exchange and len(reaction.products) == 0:
		rate_law += "*%s(t)" % reaction.get_external_metabolite
	# For all other reactions
	else:
		for metab in reaction.products:
			coeff = abs(reaction.get_coefficient(metab.id))
			if coeff == 1:
				rate_law += "%s(t)*" % metab.id
			else:
				rate_law += "%s(t)**%s*" % (metab.id, coeff)

	rate_law = "%s / %s)" % (rate_law.rstrip("*"), reaction._sym_Keq)
	return rate_law

def _generate_rate_type_2(reaction):
	"""Internal use. Generates the type 2 rate law for the reaction as
	a human readable string.

	To safely generate a rate law, use the generate_rate_law method.
	"""
	# Generate forward rate
	rate_law = ""
	# For exchange reactions
	if reaction.exchange and len(reaction.reactants) == 0:
		# Generate an "external" metabolite for exchanges
		rate_law += "*%s(t)" % reaction.get_external_metabolite
	# For all other reactions
	else:
		for metab in reaction.reactants:
			coeff = abs(reaction.get_coefficient(metab.id))
			if coeff == 1:
				rate_law += "*%s(t)" % metab.id
			else:
				rate_law += "*%s(t)**%s" % (metab.id, coeff)
	# Return rate if reaction is irreversible
	if not reaction._reversible:
		return reaction._sym_kf + rate_law

	# Generate reverse rate
	rate_law = "%s%s - %s" % (reaction._sym_kf, rate_law, reaction._sym_kr)
	if reaction.exchange and len(reaction.products) == 0:
		# Generate an "external" metabolite for exchanges
		rate_law += "*%s(t)" % reaction.get_external_metabolite
	# For all other reactions
	else:
		for metab in reaction.products:
			coeff = abs(reaction.get_coefficient(metab.id))
			if coeff == 1:
				rate_law += "*%s(t)" % metab.id
			else:
				rate_law += "*%s(t)**%s" % (metab.id, coeff)

	return rate_law

def _generate_rate_type_3(reaction):
	"""Internal use. Generates the type 3 rate law for the reaction as
	a human readable string.

	To safely generate a rate law, use the generate_rate_law method.
	"""
	# Generate forward rate
	rate_law = ""
	# For exchange reactions
	if reaction.exchange and len(reaction.reactants) == 0:
		# Generate an "external" metabolite for exchanges
		rate_law += "*%s(t)" % reaction.get_external_metabolite
	# For all other reactions
	else:
		for metab in reaction.reactants:
			coeff = abs(reaction.get_coefficient(metab.id))
			if coeff == 1:
				rate_law += "*%s(t)" % metab.id
			else:
				rate_law += "*%s(t)**%s" % (metab.id, coeff)
	# Return rate if reaction is irreversible
	if not reaction._reversible:
		return "%s*%s%s" % (reaction._sym_kr, reaction._sym_Keq, rate_law)

	# Generate reverse rate
	rate_law = '%s*(%s%s - ' % (reaction._sym_kr, reaction._sym_Keq, rate_law)
	# For exchange reactions
	if reaction.exchange and len(reaction.products) == 0:
		# Generate an "external" metabolite for exchanges
		rate_law += "%s(t)*" % reaction.get_external_metabolite
	# For all other reactions
	else:
		for metab in reaction.products:
			coeff = abs(reaction.get_coefficient(metab.id))
			if coeff == 1:
				rate_law += "%s(t)*" % metab.id
			else:
				rate_law += "%s(t)**%s*" % (metab.id, coeff)
	rate_law = rate_law.rstrip("*") + ')'
	return rate_law

def _generate_rate_expr_type_1(reaction):
	"""Internal use. Generates the type 1 rate law for the reaction as
	a sympy expression for simulation.

	To safely generate a rate law, use the generate_rate_law method.
	"""
	# Generate forward rate
	rate_law_f = sp.S.One
	# For exchange reactions
	if reaction.exchange and len(reaction.reactants) == 0:
		# Generate an "external" metabolite for exchanges
		metab_ode = sp.Symbol(reaction.get_external_metabolite,
								nonnegative=True)
		rate_law_f = sp.Mul(rate_law_f, metab_ode)
	# For all other reactions
	else:
		for metab in reaction.reactants:
			metab_ode = sp.Symbol(metab.id, nonnegative=True)(t)
			coeff = abs(reaction.get_coefficient(metab.id))
			if coeff == 1:
				rate_law_f = sp.Mul(rate_law_f, metab_ode)
			else:
				rate_law_f = sp.Mul(rate_law_f, sp.Pow(metab_ode, coeff))

	# Return rate if reaction is irreversible
	if not reaction._reversible:
		return sp.Mul(sp.var(reaction._sym_kf), rate_law_f)

	# Generate reverse rate
	rate_law_r = sp.Pow(sp.var(reaction._sym_Keq), -1)
	# For exchange reactions
	if reaction.exchange and len(reaction.products) == 0:
		metab_ode = sp.Symbol(reaction.get_external_metabolite,
								nonnegative=True)
		rate_law_r = sp.Mul(rate_law_r, metab_ode)
	# For all other reactions
	else:
		for metab in reaction.products:
			metab_ode = sp.Symbol(metab.id, nonnegative=True)(t)
			coeff = abs(reaction.get_coefficient(metab.id))
			if coeff == 1:
				rate_law_r = sp.Mul(rate_law_r, metab_ode)
			else:
				rate_law_r = sp.Mul(rate_law_r, sp.Pow(metab_ode, coeff))

	# Combine forward and reverse rates, and return rate law
	return sp.Mul(sp.var(reaction._sym_kf), sp.Add(rate_law_f,
												sp.Mul(-1, rate_law_r)))

def _generate_rate_expr_type_2(reaction):
	"""Internal use. Generates the type 2 rate law for the reaction as
	a sympy expression for simulation.

	To safely generate a rate law, use the generate_rate_law method.
	"""
	# Generate forward rate
	rate_law_f = sp.var(reaction._sym_kf)
	# For exchange reactions
	if reaction.exchange and len(reaction.reactants) == 0:
		# Generate an "external" metabolite for exchanges
		metab_ode = sp.Symbol(reaction.get_external_metabolite,
								nonnegative=True)
		rate_law_f = sp.Mul(rate_law_f, metab_ode)
	# For all other reactions
	else:
		for metab in reaction.reactants:
			metab_ode = sp.Symbol(metab.id, nonnegative=True)(t)
			coeff = abs(reaction.get_coefficient(metab.id))
			if coeff == 1:
				rate_law_f = sp.Mul(rate_law_f, metab_ode)
			else:
				rate_law_f = sp.Mul(rate_law_f, sp.Pow(metab_ode, coeff))

	# Return rate if reaction is irreversible
	if not reaction._reversible:
		return rate_law_f

	# Generate reverse rate
	rate_law_r = sp.var(reaction._sym_kr)
	# For exchange reactions
	if reaction.exchange and len(reaction.products) == 0:
		# Generate an "external" metabolite for exchanges
		metab_ode = sp.Symbol(reaction.get_external_metabolite,
								nonnegative=True)
		rate_law_r = sp.Mul(rate_law_r, metab_ode)
	# For all other reactions
	else:
		for metab in reaction.products:
			metab_ode = sp.Symbol(metab.id, nonnegative=True)(t)
			coeff = abs(reaction.get_coefficient(metab.id))
			if coeff == 1:
				rate_law_r = sp.Mul(rate_law_r, metab_ode)
			else:
				rate_law_r = sp.Mul(rate_law_r, sp.Pow(metab_ode, coeff))

	# Combine forward and reverse rates, and return rate law
	return sp.Add(rate_law_f, sp.Mul(-1, rate_law_r))

def _generate_rate_expr_type_3(reaction):
	"""Internal use. Generates the type 3 rate law for the reaction as
	a sympy expression for simulation.

	To safely generate a rate law, use the generate_rate_law method.
	"""
	# Generate forward rate
	rate_law_f = sp.var(reaction._sym_Keq)
	# For exchange reactions
	if reaction.exchange and len(reaction.reactants) == 0:
		# Generate an "external" metabolite for exchanges
		metab_ode = sp.Symbol(reaction.get_external_metabolite,
								nonnegative=True)
		rate_law_f = sp.Mul(rate_law_f, metab_ode)
	# For all other reactions
	else:
		for metab in reaction.reactants:
			metab_ode = sp.Symbol(metab.id, nonnegative=True)(t)
			coeff = abs(reaction.get_coefficient(metab.id))
			if coeff == 1:
				rate_law_f = sp.Mul(rate_law_f, metab_ode)
			else:
				rate_law_f = sp.Mul(rate_law_f, sp.Pow(metab_ode, coeff))

	# Return rate if reaction is irreversible
	if not reaction._reversible:
		return sp.Mul(sp.var(reaction._sym_kr), rate_law_f)

	# Generate reverse rate
	rate_law_r = sp.S.One
	# For exchange reactions
	if reaction.exchange and len(reaction.products) == 0:
		# Generate an "external" metabolite for exchanges
		metab_ode = sp.Symbol(reaction.get_external_metabolite,
								nonnegative=True)
		rate_law_r = sp.Mul(rate_law_r, metab_ode)
	# For all other reactions
	else:
		for metab in reaction.products:
			metab_ode = sp.Symbol(metab.id, nonnegative=True)(t)
			coeff = abs(reaction.get_coefficient(metab.id))
			if coeff == 1:
				rate_law_r = sp.Mul(rate_law_r, metab_ode)
			else:
				rate_law_r = sp.Mul(rate_law_r, sp.Pow(metab_ode, coeff))

	# Combine forward and reverse rates, and return rate law
	return sp.Mul(sp.var(reaction._sym_kr), sp.Add(rate_law_f,
												sp.Mul(-1, rate_law_r)))

def _get_mass_action_ratio_expr(reaction):
	"""Internal use. Generates the mass action ratio for the reaction as
	a human readable string.

	To safely generate the mass action ratio, use the
	get_mass_action_ratio method.
	"""
	# For the reactants
	reactant_bits = sp.S.One
	if reaction.exchange and len(reaction.reactants) == 0:
		# Generate an "external" metabolite for exchanges
		metab_ode = sp.Symbol(reaction.get_external_metabolite,
								nonnegative=True)
		reactant_bits = sp.Mul(reactant_bits, metab_ode)
	# For all other reactions
	else:
		for metab in reaction.reactants:
			metab_ode = sp.Symbol(metab.id, nonnegative=True)(t)
			coeff = abs(reaction.get_coefficient(metab.id))
			if coeff == 1:
				reactant_bits = sp.Mul(reactant_bits, metab_ode)
			else:
				reactant_bits = sp.Mul(reactant_bits, sp.Pow(metab_ode, coeff))

	# For the products
	product_bits = sp.S.One
	if reaction.exchange and len(reaction.products) == 0:
		# Generate an "external" metabolite for exchanges
		metab_ode = sp.Symbol(reaction.get_external_metabolite,
								nonnegative=True)
		product_bits = sp.Mul(product_bits, metab_ode)
	# For all other reactions
	else:
		for metab in reaction.products:
			metab_ode = sp.Symbol(metab.id, nonnegative=True)(t)
			coeff = abs(reaction.get_coefficient(metab.id))
			if coeff == 1:
				product_bits = sp.Mul(product_bits, metab_ode)
			else:
				product_bits = sp.Mul(product_bits, sp.Pow(metab_ode, coeff))

	# Combine to make the mass action ratio
	return sp.Mul(product_bits, sp.Pow(reactant_bits, -1))

def _sort_symbols(model, rate_type=None):
	"""Internal use. Collect and sort the symbols in expressions of a model
	into different sets, and adjust odes and rates accordingly"""
	if rate_type is None:
		rate_type = model._rtype

	# Initialize sets to store the symbols
	ode_dict = model.odes
	rate_dict = model.generate_rate_laws(rate_type=rate_type,
								sympy_expr=True, update_reactions=False)
	metab_funcs = set()
	rate_symbols = set()
	fixed_symbols = set()
	custom_symbols = set()
	# Collect all symbols in the odes expressions into one set
	for item, expression in iteritems(model.odes):
		symbols = expression.atoms(sp.Symbol)
		functions = expression.atoms(sp.Function)
		for sym in symbols:
		# Sort the symbols into their respective sets
			sym_str = str(sym)
			# Symbols representing fixed concentrations
			if sym_str in iterkeys(model.fixed_concentrations):
				fixed_symbols.add(sym)
			# Symbols representing rate parameters
			if re.search("kf|Keq|kr",sym_str):
				rate_symbols.add(sym)
			# Symbols representing custom rate paraemters
			if sym_str in iterkeys(model.custom_parameters):
				custom_symbols.add(sym)

		for func in functions:
			metab = model.metabolites.get_by_id(str(func)[:-3])
			if metab in iterkeys(model.fixed_concentrations):
				metab_sym = sp.Symbol(metab.id, nonnegative=True)
				ode_dict[item] = expression.subs({func: metab_sym})
				for reaction, rate in iteritems(model.rate_expressions):
					rate_dict[reaction] = rate.subs({func: metab_sym})
				fixed_symbols.add(metab_sym)
			else:
				metab_funcs.add(func)
	symbol_list = [metab_funcs, rate_symbols, fixed_symbols, custom_symbols]
	return ode_dict, rate_dict, symbol_list

def _ignore_h_and_h2o(reaction):
	"""Internal use. Remove hydrogen and water from reactions to prevent them
	from inclusion in simulation. Will not effect hydrogen and water exchanges
	"""
	reaction = reaction.copy()
	for metab, coefficient in iteritems(reaction.metabolites):
		if metab.elements == {'H': 2, 'O': 1} or \
			metab.elements == {'H': 1}:
			if not reaction.exchange:
				reaction.subtract_metabolites({metab:coefficient})

	return reaction
