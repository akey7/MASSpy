# -*- coding: utf-8 -*-

# Compatibility with Python 2.7
from __future__ import absolute_import

# Import necesary packages
import re
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator
from cycler import cycler
from warnings import warn
from six import iteritems, iterkeys, itervalues, integer_types, string_types
# Class begins
## Precompiled regular expression for legend location and
## plot_tiled_phase_portrait options
legend_loc = re.compile("best|upper right|upper left|lower left|lower right|"
						"right|center left|center right|lower center|"
						"upper center|center|outside")
ptpp_options = re.compile("both|upper|lower")
plot_re = re.compile("plot")
tiled_re = re.compile("tiled")
## Public Methods
def get_plot_defaults():
	"""Return a copy of the default options for plot_simulation and
	plot_phase_portrait

	See Also:
	---------
	set_plot_defaults(**custom)
	restore_plot_defaults()
	"""
	return _plot_defaults.copy()

def get_tiled_defaults():
	"""Return a copy of the default options for plot_tiled_phase_portrait

	See Also:
	---------
	set_tiled_defaults(**custom)
	restore_tiled_defaults()
	"""
	return _tiled_defaults.copy()

def set_plot_defaults(**custom):
	"""Allows user to change the global default options for plot_simulation and
	plot_phase_portrait (provided if ``kwargs`` are not not specified).

	``kwargs`` are passed on to various matplotlib methods.
    See get_plot_defaults() for a full description of possible ``kwargs``.

	Parameters:
	-----------
	**custom: dict
		A dictionary of ``kwargs`` with options as the keys (str) and the
		desired option defaults as the values

	See Also:
	---------
	get_plot_defaults()
	restore_plot_defaults()
	"""
	options_dict = _handle_plot_options(custom, "plot")
	_plot_defaults.update(options_dict)

def set_tiled_defaults(**custom):
	"""Allows user to change the global default options for
	plot_tiled_phase_portrait (provided if ``kwargs`` are not not specified).

	``kwargs`` are passed on to various matplotlib methods.
    See get_tiled_defaults() for a full description of possible ``kwargs``.

	Parameters:
	-----------
	**custom: dict
		A dictionary of ``kwargs`` with options as the keys (str) and the
		desired option defaults as the values

	See Also:
	---------
	get_tiled_defaults()
	restore_tiled_defaults()
	"""
	options_dict = _handle_plot_options(custom, "tiled")
	_tiled_defaults.update(options_dict)

def restore_plot_defaults():
	"""Restores plot default options to their original values

	See Also:
	---------
	get_plot_defaults()
	set_plot_defaults(**custom)
	"""
	_plot_defaults = _base_plot_defaults
	print("Original plot defaults restored")

def restore_tiled_defaults():
	"""Restores tiled default options to their original values

	See Also:
	---------
	get_tiled_defaults()
	set_tiled_defaults(**custom)
	"""
	_tiled_defaults = _base_tiled_defaults
	print("Original tiled defaults restored")

def plot_simulation(solution_profile, time, ax=None, observable=None,
					**kwargs):
	"""Generates a plot of the data in the solution_profile over time.

	``kwargs`` are passed on to various matplotlib methods.
	See get_plot_defaults() for a full description of possible ``kwargs``.

	Parameters
	----------
	solution_profile : dict
        An dict of interpolating functions containing the solution profiles to
		be plotted. The keys are strings, mass.MassMetabolite objects, or
		mass.MassReaction objects, and the values are interpolating functions
		of the corresponding solution.
	time : tuple, list, or numpy.ndarray
		A tuple containing the start and end time points, or a list of
		numerical values to treat as time points for the solutions. If a tuple
		of form (start point, end_point) is provided, a time vector is
		internally generated with optional kwarg "numpoints" specifying how
		many points are in the generated vector.
	ax : matplotlib.pyplot.axes, optional
		A matplotlib.pyplot.axes instance to plot the data on. If None,
		a figure and an axes will be generated for plotting instead.
	observable : iterable of key(s) of the solution profile, optional
		An iterable of the keys of the given solution_profile dictionary to
		filter solutions such that only the solutions profiles for the given
		"observables" will be plotted. If None, will plot the solutions for all
		items in the given solution_profile dictionary.

	Returns
	-------
	matplotlib.pyplot.figure
		A reference to the current figure instance. Shows plot when returned.
        Can be used to modify plot after initial generation.

	See Also:
	---------
	get_plot_defaults()
	set_plot_defaults(**custom)
	restore_plot_defaults()
	"""
	# Obtain the options dictonary and check inputs
	options_dict = _handle_plot_options(kwargs, "plot")
	time = _check_main_inputs(solution_profile, time, options_dict)
	# Obtain list if solutions to be observed
	observable = _set_plot_observables(solution_profile, observable)
	# Generate a new figure if no axes provided
	if ax is None:
		fig = plt.figure()
		if "figsize" not in kwargs and options_dict["figsize"] == (5.0, 5.0):
			fig.set_size_inches((6.0, 4.0))
		else:
			fig.set_size_inches(options_dict["figsize"])
		fig.clf()
		if options_dict["dpi"] is not None:
			fig.set_dpi(options_dict["dpi"])
		ax = fig.add_subplot(111)
		ax.cla()
	# Otherwise ensure provided axes is a matplotlib.pyplot.axes instance.
	elif not isinstance(ax, type(plt.axes())):
		raise TypeError("ax must be an instance of a "
						"matplotlib.axes._subplots.AxesSubplot object")

	# Set plot function
	plot_function = {"loglog" : ax.loglog,
					"semilogx" : ax.semilogx,
					"semilogy" : ax.semilogy,
					"plot" : ax.plot}[options_dict["plot_function"]]
	# Get solutions
	sols = np.array([profile(time)
					for profile in itervalues(observable)]).T
	# Create Plot
	plot_function(time, sols)
	# Set legend
	lgnd = options_dict["legend"][0]
	lgnd_loc = options_dict["legend"][1]
	lgnd_font = options_dict["legend"][2]
	anchor = None
	if re.match("outside", lgnd_loc):
		lgnd_loc = "center left"
		anchor = (1, 0.5)
	# Create a legend if none provided.
	if lgnd is None or len(lgnd) == 0:
		lgnd = [x if isinstance(x, string_types) else x.id
					for x in list(iterkeys(observable))]
	# Set linecolors and linestyles, ensure legend is update accordingly
	ax = _set_colors_and_styles(ax, lgnd, options_dict)
	ax.legend(lgnd, loc=lgnd_loc, fontsize=lgnd_font, bbox_to_anchor=anchor)
	# Add all other features to the plot
	ax = _add_plot_options_to_plot(ax, options_dict, "plot")
	# Return figure instance
	return ax.get_figure()

def plot_phase_portrait(solution_profile, time, x, y, ax=None,
						poi="endpoints", poi_color="red", poi_labels=True,
						**kwargs):
	"""Generates a phase portrait of x,y in the solution_profile over time.

	``kwargs`` are passed on to various matplotlib methods.
	See get_plot_defaults() for a full description.

	Parameters
	----------
	solution_profile : dict
        An dict of interpolating functions containing the solution profiles to
		be plotted. The keys are strings, mass.MassMetabolite objects, or
		mass.MassReaction objects, and the values are interpolating functions
		of the corresponding solution.
	time : tuple, list, or numpy.ndarray
		A tuple containing the start and end time points, or a list of
		numerical values to treat as time points for the solutions. If a tuple
		of form (start point, end_point) is provided, a time vector is
		internally generated with optional kwarg "numpoints" specifying how
		many points are in the generated vector.
	x : mass.MassMetabolite, mass.MassReaction, or string
		A key of the corresponding to the solution to plot on the x-axis of the
		phase portrait. Must exist in the given solution_profile dictionary.
	y : mass.MassMetabolite, mass.MassReaction, or string
		A key of the corresponding to the solution to plot on the y-axis of the
		phase portrait. Must exist in the given solution_profile dictionary.
	ax : matplotlib.pyplot.axes, optional
		A matplotlib.pyplot.axes instance to plot the data on. If None,
		a figure and an axes will be generated for plotting instead.
	poi : tuple, list, or numpy.ndarray, or the string "endpoints", optional
		An iterable of time "points of interest" to be annotated on each
		phase portrait, or the string "endpoints" to annotate the start and
		end time points. If None provided, will not annotate any time points.
	poi_color : string, iterable of strings, optional
		A string or an iterable of strings of colors from matplotlib.colors to
		use for annotation of "points of interest" for the plot. If a single
		color is provided, all annotated time points will be that color. If an
		iterable of color strings are provided, the length of the iterable must
		be equal to the length of the provided poi iterable. If None provided,
		will default to "red".
	poi_labels : bool, optional
		If True, will label annotated time "points of interest" with their
		time values. Otherwise will not label the time points.

	Returns
	-------
	matplotlib.pyplot.figure
		A reference to the current figure instance. Shows plot when returned.
        Can be used to modify plot after initial generation.

	See Also:
	---------
	get_plot_defaults()
	set_plot_defaults(**custom)
	restore_plot_defaults()
	"""
	# Obtain the options dictonary and check inputs
	options_dict = _handle_plot_options(kwargs, "plot")
	time = _check_main_inputs(solution_profile, time, options_dict)
	# Obtain list of solutions to be observed
	x_observable = _set_plot_observables(solution_profile, x)
	y_observable = _set_plot_observables(solution_profile, y)
	# Generate figure if no axes passed
	if ax is None:
		fig = plt.figure()
		fig.clf()
		fig.set_size_inches(options_dict["figsize"])
		ax = fig.add_subplot(111)
		ax.cla()
	# Otherwise ensure provided axes is a matplotlib.pyplot.axes instance.
	elif not isinstance(ax, type(plt.axes())):
		raise TypeError("ax must be an instance of a "
						"matplotlib.axes._subplots.AxesSubplot object")
	# Set plot function
	plot_function = {"loglog" : ax.loglog,
					"semilogx" : ax.semilogx,
					"semilogy" : ax.semilogy,
					"plot" : ax.plot}[options_dict["plot_function"]]
	# Obtain solutions
	x_sols = np.array([profile(time)
					for profile in itervalues(x_observable)])
	y_sols = np.array([profile(time)
					for profile in itervalues(y_observable)])
	# Plot solutions
	for i in range(0, len(x_sols)):
		for j in range(0, len(y_sols)):
			plot_function(x_sols[i], y_sols[j])
	# Set legend
	lgnd = options_dict["legend"][0]
	if lgnd is None or len(lgnd) == 0:
		pass
	else:
		lgnd_loc = options_dict["legend"][1]
		lgnd_font = options_dict["legend"][2]
		anchor = None
		if re.match("outside", lgnd_loc):
			lgnd_loc = "center left"
			anchor = (1, 0.5)
		# Set linecolors and linestyles, ensure legend is update accordingly
		ax = _set_colors_and_styles(ax, lgnd, options_dict)
		ax.legend(lgnd, loc=lgnd_loc, fontsize=lgnd_font,
					bbox_to_anchor=anchor)
	# Label time points of interest
	if poi is not None:
		ax = _label_poi(ax, time, poi, poi_color, poi_labels,
						plot_function, x_observable, y_observable)
	# Add all other features to the plot
	ax = _add_plot_options_to_plot(ax, options_dict, "plot")
	# Return figure instance
	return ax.get_figure()

def plot_tiled_phase_portrait(solution_profile, time, place_tiles="both",
						data=None, poi=None, poi_color=None, poi_labels=False,
						fontsize=None, **kwargs):
	"""Generates a tiled phase portrait for all items in a given solution_profile

	``kwargs`` are passed on to various matplotlib methods.
	See get_tiled_defaults() for a full description.

	Parameters
	----------
	solution_profile : dict
        An dict of interpolating functions containing the solution profiles to
		be plotted. The keys are strings, mass.MassMetabolite objects, or
		mass.MassReaction objects, and the values are interpolating functions
		of the corresponding solution.
	time : tuple, list, or numpy.ndarray
		A tuple containing the start and end time points, or a list of
		numerical values to treat as time points for the solutions. If a tuple
		of form (start point, end_point) is provided, a time vector is
		internally generated with optional kwarg "numpoints" specifying how
		many points are in the generated vector.
	place_tiles : {'upper', 'lower', 'both'}
		A string representing whether to place subplots on the upper right
		triangular section, the lower left triangular section, or both.
	data : array_like, shape (N, N), optional
		Additional data to display on the tiled phase portrait if place_tiles
		is not set to both. Must matrix of shape (N, N) where N = number of
		keys in the given solution_profile. When place_tiles is "upper", data
		must be a lower triangular matrix with zeros on the main diagonal
		(data = numpy.tril(matrix_for_annotation, k=-1)). When place_tiles is
		"lower",data must be an upper triangular matrix with zeros on the main
		diagonal (data = numpy.triu(matrix_for_annotation, k=1)).
	poi : tuple, list, or numpy.ndarray, or the string "endpoints", optional
		An iterable of time "points of interest" to be annotated on each
		phase portrait, or the string "endpoints" to annotate the start and
		end time points. If None provided, will not annotate any time points.
	poi_color : string, iterable of strings, optional
		A string or an iterable of strings of colors from matplotlib.colors to
		use for annotation of "points of interest" for the plot. If a single
		color is provided, all annotated time points will be that color. If an
		iterable of color strings are provided, the length of the iterable must
		be equal to the length of the provided poi iterable. If None provided,
		will default to "red".
	poi_labels : bool, optional
		If True, will label annotated time "points of interest" with their
		time values. Otherwise will not label the time points.
	fontsize : integer, float, or string
		The size of the font for common axis labels and the title, if provided.
		Can be an integer or float, or one of the following strings:
		{'xx-small’, ‘x-small’, ‘small’, ‘medium’, ‘large’, ‘x-large’,
		‘xx-large’}

	Returns
	-------
	matplotlib.pyplot.figure
		A reference to the current figure instance. Shows plot when returned.
        Can be used to modify plot after initial generation.

	See Also:
	---------
	get_tiled_defaults()
	set_tiled_defaults(**custom)
	restore_tiled_defaults()
	"""
	# Check input
	if not ptpp_options.match(place_tiles):
		raise ValueError("place_tiles must be one of the following: "
						"'both', 'upper', or 'lower'")
	n_keys = len(solution_profile)
	# Check the inputted optional data argument
	if data is not None:
		if not isinstance(data, np.ndarray):
			data = np.array(data)
		# Check dimensions of data matrix
		if data.shape != (n_keys, n_keys):
			raise ValueError("data must be an n x n matrix where n"
						" is equal to the number of keys in solution_profile.")
		# Change place_tiles if set to 'both'
		if re.match("both", place_tiles):
			warn("data provided while place_tiles set to both, will "
					"attempting to correct place_tiles")
			if (np.triu(data) == data).all() == True:
				place_tiles = "lower"
			elif (np.tril(data) == data).all() == True:
				place_tiles = "upper"
			else:
				warn("Could not interpret data matrix, will not display data. "
					"Check data matrix to ensure it is in the form of "
					"numpy.triu(data) for placement on upper tiles or "
					"numpy.tril(data) for placement on lower tiles")
				place_tiles = "both"
	# Obtain the options dictonary and check inputs
	options_dict = _handle_plot_options(kwargs, "tiled")
	time = _check_main_inputs(solution_profile, time, options_dict)

	# Generate main figure, set size and dpi  if desired.
	fig, ax_main = plt.subplots(nrows=n_keys, ncols=n_keys)
	if options_dict["dpi"] is not None:
		fig.set_dpi(options_dict["dpi"])
	fig.set_size_inches(options_dict["figsize"])

	# Obtain sols
	sols = np.array([profile(time)
					for profile in itervalues(solution_profile)])
	# A function that uses the tiled options to generate each individual tile
	def _add_plot_tile(ax, i, j, x, y):
		plot_function = {"loglog" : ax.loglog,
						"semilogx" : ax.semilogx,
						"semilogy" : ax.semilogy,
						"plot" : ax.plot}[options_dict["plot_function"]]
		plot_function(sols[j], sols[i], c=options_dict["linecolor"],
										ls=options_dict["linestyle"])
		# Label points of interest if provided
		if poi is not None:
			ax = _label_poi(ax, time, poi, poi_color,
						poi_labels, plot_function,
						_set_plot_observables(solution_profile, x),
						_set_plot_observables(solution_profile, y))

		ax = _add_plot_options_to_plot(ax, options_dict, "tiled")
		return ax

	# Adjust the font size scalar
	if fontsize is None:
		fontsize = max(options_dict["figsize"][0]*1.5, 15)
	# Add title if desired
	if options_dict["title"] is not None:
		fig.suptitle(options_dict["title"],
						fontsize=fontsize)
	for i, y in enumerate(iterkeys(solution_profile)):
		for j, x in enumerate(iterkeys(solution_profile)):
			ax = ax_main[i][j]
			# Set common axis labels
			if i == n_keys-1:
				label = x
				if not isinstance(label, string_types):
					label = label.id
				ax.set_xlabel(label, fontdict={"size":fontsize})
			if j == 0:
				label = y
				if not isinstance(label, string_types):
					label = label.id
				ax.set_ylabel(label, fontdict={"size":fontsize})
			# Don't create phase portraits of items vs. themselves.
			if i == j:
				ax.annotate("X", xy=(0.5, 0.5), xycoords="axes fraction",
						va="center", ha="center", fontsize=fontsize)
				ax.set_xticklabels([])
				ax.set_yticklabels([])
			# Create phase portraits for upper tiles only
			elif re.match("upper", place_tiles):
				# Create upper tile phase portraits
				if i < j:
					ax = _add_plot_tile(ax, i, j, x, y)
				# Add additional data to lower tiles if provided
				if i > j and data is not None:
					ax.annotate(str(data[i][j]), xy=(0.5, 0.5),
							xycoords="axes fraction", va="center", ha="center",
							fontsize=fontsize)
			# Create phase portraits for lower tiles only
			elif re.match("lower", place_tiles):
				# Create lower tile phase portraits
				if i > j:
					ax = _add_plot_tile(ax, i, j, x, y)
				# Add additional data to upper tiles if provided
				if i < j and data is not None:
					ax.annotate(str(data[i][j]), xy=(0.5, 0.5),
							xycoords="axes fraction", va="center", ha="center",
							fontsize=fontsize)
			# Create phase portraits for both upper and lower tiles
			else:
				ax = _add_plot_tile(ax, i, j, x, y)
	# Return figure instance
	return fig

## Internal Methods
def _add_plot_options_to_plot(ax, options_dict, plot_type):
	"""Internal Method. Add plot features to the axes"""
	# For plot_simulation and plot_phase_portrait specifically
	if plot_re.match(plot_type):
		# Set xlim
		if options_dict["xlim"] != (None, None):
			ax.set_xlim(options_dict["xlim"])
		# Set ylim
		if options_dict["ylim"] != (None, None):
			ax.set_ylim(options_dict["ylim"])
		# Set title if desired
		if options_dict["title"][0] is not None:
			ax.set_title(options_dict["title"][0],
						fontdict=options_dict["title"][1])
		# Set xlabel if desired
		if options_dict["xlabel"][0] is not None:
			ax.set_xlabel(options_dict["xlabel"][0],
						fontdict=options_dict["xlabel"][1])
		# Set ylabel if desired
		if options_dict["ylabel"][0] is not None:
			ax.set_ylabel(options_dict["ylabel"][0],
						fontdict=options_dict["ylabel"][1])

	# Set xgrid and y grid if deisred
	if options_dict["grid"][0]:
		ax.xaxis.grid(True, linestyle="--")
	if options_dict["grid"][1]:
		ax.yaxis.grid(True, linestyle="--")
	# Set options for ticks and ticklabels
	if not options_dict["tick_labels"]:
		ax.set_xticklabels([])
		ax.set_yticklabels([])
	for tick_type in ["x_major_ticks", "x_minor_ticks",
						"y_major_ticks", "y_minor_ticks"]:
		if options_dict[tick_type] is not None:
			# x-axis ticks
			if re.match("x", tick_type[0]):
				axis = ax.xaxis
			# y-axis ticks
			else:
				axis = ax.yaxis
			# Major ticks
			if re.search("major", tick_type):
				axis.set_major_locator(options_dict[tick_type])
			# Minor ticks
			else:
				axis.set_minor_locator(options_dict[tick_type])
	return ax

def _set_plot_observables(solution_profile, observable):
	"""Internal method. Check and return a list of solution profiles to be
		observed in the plot"""
	# If no observables provided, use entire solution profile
	if observable is None:
		observable = solution_profile
	# If a single observable is provided, make it iterable
	elif not hasattr(observable, '__iter__') or \
		isinstance(observable, string_types):
			observable = [observable]
	# Check to ensure specified observables are in the solution profile
	if not set(observable).issubset(set(iterkeys(solution_profile))):
		raise ValueError("observable must keys from the solution_profile")
	# Create a dictionary of solution profile observables
	else:
		observable = dict((x, solution_profile[x]) for x in observable)

	return observable

def _set_colors_and_styles(ax, lgnd, options_dict):
	"""Internal method. Set linecolors and styles for a plot"""
	# Use a larger colormap if more than 20 items are to be plotted and no
	# colors were specified by the user.
	if options_dict["linecolor"] is None and len(lgnd) > 20:
		options_dict["linecolor"] = _get_base_colormap()
	# Set colors and adjust legend entries
	if options_dict["linecolor"] is not None:
		lgnd_id_dict = dict(zip(lgnd, np.arange(len(lgnd))))
		for entry, i in iteritems(lgnd_id_dict):
			ax.get_lines()[lgnd_id_dict[entry]].set_color(
				options_dict["linecolor"][i])
	# Set linestyles and adjust legend entries
	if options_dict["linestyle"] is not None:
		lgnd_id_dict = dict(zip(lgnd, np.arange(len(lgnd))))
		for entry, i in iteritems(lgnd_id_dict):
			ax.get_lines()[lgnd_id_dict[entry]].set_linestyle(
				options_dict["linestyle"][i])

	return ax

def _handle_plot_options(kwargs, plot_type):
	"""Internal method. Using the default options as the base, creates the
	option dictionary and adds customized options, if any"""
	# Handle options for plot_simulation and plot_phase_portrait
	if plot_re.match(plot_type):
		# Get current default options
		options_dict = get_plot_defaults()
		if kwargs is not None:
			# Otherwise update the options dictionary with the kwargs
			for key, value in iteritems(kwargs):
				# Option for type of plot
				if re.match("plot_function", key):
					_update_plot_function(options_dict, value)
				# Option for number of points
				if re.match("numpoints", key):
					_update_numpoints(options_dict, value)
				# Option for figure size
				if re.match("figsize", key):
					_update_figsize(options_dict, value)
				# Option for legend
				if re.match("legend", key):
					_update_legend(options_dict, value)
				# Option for title, xlabel, ylabel text and font size
				if re.match("title|xlabel|ylabel", key):
					_update_labels(options_dict, key, value)
				# Option for xlim and ylim
				if re.match("xlim|ylim", key):
					_update_limits(options_dict, key, value)
				# Option for grid
				if re.match("grid", key):
					_update_grid(options_dict, value)
				# Option for dpi
				if re.match("dpi", key):
					_update_dpi(options_dict, value)
				# Option for major and minor ticks
				if re.match("tick_labels|x_major_ticks|y_major_ticks|"
							"x_minor_ticks|y_minor_ticks", key):
					_update_ticks(options_dict, key, value)
				# Option for linecolors and styles
				if re.match("linecolor|linestyle", key):
					_update_lines(options_dict, key, value)

	# Handle options for plot_tiled_phase_portrait
	if tiled_re.match(plot_type):
		# Get current default options
		options_dict = get_tiled_defaults()
		if kwargs is not None:
			# Otherwise update the options dictionary with the kwargs
			for key, value in iteritems(kwargs):
				# Option for type of plot
				if re.match("plot_function", key):
					_update_plot_function(options_dict, value)
				# Option for number of points
				if re.match("numpoints", key):
					_update_numpoints(options_dict, value)
				# Option for figure size
				if re.match("figsize", key):
					_update_figsize(options_dict, value)
				# Option for title
				if re.match("title", key):
					if not isinstance(value, string_types):
						raise TypeError("%s must be a string" % key)
					options_dict[key] = value
				# Option for grid
				if re.match("grid", key):
					_update_grid(options_dict, value)
				# Option for dpi
				if re.match("dpi", key):
					_update_dpi(options_dict, value)
				# Option for major and minor ticks
				if re.match("tick_labels|x_major_ticks|y_major_ticks|"
							"x_minor_ticks|y_minor_ticks", key):
					_update_ticks(options_dict, key, value)
				# Option for linecolors and styles
				if re.match("linecolor|linestyle", key):
					_update_lines(options_dict, key, value)
	# Return the new options as a dict, or return default options if no kwargs
	return options_dict

def _check_main_inputs(solution_profile, time, options_dict):
	"""Internal method. Check solution_profile and time inputs, return
	the time vector"""
	# Check solution_profile
	if not isinstance(solution_profile, dict):
		raise TypeError("solution profile must be a dictionary.")
	# Check time
	if isinstance(time, tuple):
		# Cannot use 0 in log spacing, adjust to a small value instead.
		if abs(time[0]) < 1e-9:
			time = (1e-9, time[1])
		# Generate numbers spaced evenly on a log scale
		time = np.geomspace(time[0], time[1],
										options_dict["numpoints"])
	if not isinstance(time, (np.ndarray, list)):
		raise TypeError("time must be a list or numpy.ndarray of time "
						"points, or a tuple of form (start_point, end_point).")
	return time

def _label_poi(ax, time, poi, poi_color, poi_labels, plot_function,
				x_observable, y_observable):
	"""Internal method. Annotate the points of interest for phase portraits"""
	# Annotate time points of interest
	if isinstance(poi, string_types):
		# If a string input, ensure it is recognizable.
		if not re.match("endpoints", poi):
			raise ValueError("poi cannot be a string other than "
								"'endpoints'")
		# Adjust annotation for time point correction
		elif time[0] == 1e-9:
			poi = [0, time[-1]]
		else:
			poi = [time[0], time[-1]]
	# Turn poi into an iterable if only a single point provided.
	elif not hasattr(poi, '__iter__'):
		poi = [poi]
	# Default to red if None provided
	if poi_color = None:
		poi_color = "red"
	# Turn poi_color into an iterable if only a single color provided.
	if isinstance(poi_color , string_types):
		 poi_color = [poi_color]
	# Check to ensure the lengths are the same
	if len(poi_color) != len(poi):
		# If more than one poi and only one poi_color, use color for all poi.
		if len(poi_color) == 1:
			poi_color = [poi_color[0] for i in range(0, len(poi))]
		else:
			raise ValueError("Length of poi_color must be equal to the "
							"length of poi")
	# Default to False if None provided.
	if poi_labels is None:
		poi_labels = False
	# Ensure poi_labels is a bool
	elif not isinstance(poi_labels, bool):
		raise TypeError("poi_labels must be a bool")

	# Get the x, y solutions coordinates of the provided time poi
	for i in range(0, len(x_observable)):
		x_poi_coords = np.array([profile(poi)
							for profile in itervalues(x_observable)])[i]
		for j in range(0, len(y_observable)):
			y_poi_coords = np.array([profile(poi)
								for profile in itervalues(y_observable)])[j]
			# Plot the points
			for k in range(0, len(poi)):
				plot_function(x_poi_coords[k], y_poi_coords[k], 'o',
								color=poi_color[k])
				# Label points with time value if desired.
				if poi_labels:
					ax.annotate("   t=%s" % poi[k],
								xy=(x_poi_coords[k], y_poi_coords[k]),
								xycoords='data',
								xytext=(x_poi_coords[k], y_poi_coords[k]),
								textcoords='offset points')
	return ax

def _update_plot_function(options_dict, value):
	"""Internal method. Update "plot_function" to user-defined number"""
	# Check input type for option
	if value not in {"loglog", "semilogx", "semilogy", "plot"}:
		raise ValueError('plot_function must be one of the following: '
					'{"loglog", "semilogx", "semilogy", "plot"}')
	# Update options
	options_dict.update({"plot_function": value})

def _update_numpoints(options_dict, value):
	"""Internal method. Update "numpoints" to user-defined number"""
	# Check input type for option
	if not isinstance(value, (integer_types, float)):
		raise TypeError("numpoints must be an integer")
	# Update options
	options_dict.update({"numpoints": int(value)})

def _update_figsize(options_dict, value):
	"""Internal method. Update "figsize" to user-defined number"""
	# Check input type for option
	if not isinstance(value, tuple):
		raise TypeError("figsize must be a tuple of ints")
	elif value[0] <=0 or value[1] <=0:
		raise ValueError("figsize must have positive dimensions")
	# Update options
	options_dict.update({"figsize": value})

def _update_legend(options_dict, value):
	"""Internal method. Update "legend" to user-defined number"""
	# Check input type for option
	if not hasattr(value, '__iter__'):
		raise TypeError("legend must be an iterable")
	if isinstance(value, string_types):
		value = [value]
	# Check if fontsize for the legend was specified
	if isinstance(value[-1], (integer_types, float)):
		fontsize = value.pop(-1)
	# Otherwise use default
	else:
		fontsize = options_dict["legend"][2]
	# Check if legend location was specified, otherwise use default
	loc = options_dict["legend"][1]
	if len(value) != 0:
		if legend_loc.match(value[-1]):
			loc = value.pop(-1)

		for entry in value:
			if not isinstance(entry, string_types):
				raise TypeError("legend entries must be strings")

	# Update options
	options_dict.update({"legend": (value, loc, fontsize)})

def _update_labels(options_dict, label_type, value):
	"""Internal method. Update "title", "xlabel" or "ylabel" to
	user-defined number"""
	# Check input types for option
	if not hasattr(value, '__iter__'):
		raise TypeError("%s must be an iterable" % label_type)
	if isinstance(value, string_types):
		value = (value, options_dict[label_type][1])
	if not isinstance(value[1], dict):
		raise TypeError("fontdict must be a dictionary")

	# Update options
	options_dict.update({label_type: value})

def _update_limits(options_dict, lim_type, value):
	"""Internal method. Update "xlim", or "ylim" to
	user-defined number"""
	# Check input types for option
	if not hasattr(value, '__iter__') or len(value) != 2:
		raise TypeError("%s must be an iterable of length 2" % lim_type)
	elif not isinstance(value[0], (integer_types, float)) or \
		not isinstance(value[1], (integer_types, float)):
		raise TypeError("Limits must be ints or floats")
	elif value[0] > value[1]:
		warn("%smin is greater than %smax, swapping the values" % \
				(lim_type[0], lim_type[0]))
		value = (value[1], value[0])
	else:
		value = tuple(value)
	# Update options
	options_dict.update({lim_type: value})

def _update_grid(options_dict, value):
	# Check input type for option
	if not hasattr(value, '__iter__') or len(value) != 2:
		raise TypeError("%s must be an iterable of length 2" % lim_type)
	if not isinstance(value[0], bool) or \
		not isinstance(value[1], bool):
		raise TypeError("grid must be bools")
	# Update options
	options_dict.update({"grid": value})

def _update_dpi(options_dict, value):
	# Check input type for option
	if not isinstance(value, (integer_types, float)):
		raise TypeError("dpi must be an integer or float")
	# Update options
	options_dict.update({"dpi": value})

def _update_ticks(options_dict, tick_type, value):
	if re.match("tick_labels", tick_type):
		if not isinstance(value, bool):
			raise TypeError("%s must be a bool" % tick_type)
	else:
		if not isinstance(value, (integer_types, float)):
			raise TypeError("%s must be an integer or float" % tick_type)
		value = MultipleLocator(value)
		# Update options
	options_dict.update({tick_type: value})

def _update_lines(options_dict, line_option, value):
	# Update options
	options_dict.update({line_option: value})

def _get_base_colormap():
	"""Internal method. Use a larger colormap if more than 20 items are
	to be plotted"""
	cm = plt.cm.get_cmap("tab20")
	colors1 = [cm.colors[i] for i in range(len(cm.colors))]
	cm = plt.cm.get_cmap('tab20b')
	colors2 = [cm.colors[i] for i in range(len(cm.colors))]
	cm = plt.cm.get_cmap('tab20c')
	colors3 = [cm.colors[i] for i in range(len(cm.colors))]
	colors = colors1 + colors2 + colors3

	return colors

## Internal variables
_base_plot_defaults = {
	"plot_function" : "plot",
	"numpoints" : 1e5,
	"figsize" : (5.0, 5.0),
	"legend" : (None, "best", 10),
	"xlabel" : (None, {"size": 10}),
	"ylabel" : (None, {"size": 10}),
	"title"  : (None, {"size": 10}),
	"xlim"   : (None, None),
	"ylim"   : (None, None),
	"grid" 	 : (False, False),
	"dpi"    : None,
	"tick_labels" : True,
	"x_major_ticks" : None,
	"x_minor_ticks" : None,
	"y_major_ticks" : None,
	"y_minor_ticks" : None,
	"linecolor" : None,
	"linestyle" : None
}

_base_tiled_defaults = {
	"plot_function" : "plot",
	"tick_labels"   : False,
	"x_major_ticks" : None,
	"x_minor_ticks" : None,
	"y_major_ticks" : None,
	"y_minor_ticks" : None,
	"linecolor"     : None,
    "linestyle"     : None,
	"numpoints" : 1e5,
	"figsize" : (5.0, 5.0),
	"grid" 	 : (False, False),
	"title"  : None,
	"dpi"    : None,
}

_plot_defaults = _base_plot_defaults
_tiled_defaults = _base_tiled_defaults
