# This file is part of the EESSI build-and-deploy bot,
# see https://github.com/EESSI/eessi-bot-software-layer
#
# The bot helps with requests to add software installations to the
# EESSI software layer, see https://github.com/EESSI/software-layer
#
# author: Thomas Roeblitz (@trz42)
#
# license: GPLv2
#

# Standard library imports
from collections import namedtuple
import sys

# Third party imports (anything installed into the local Python environment)
from pyghee.utils import log

# Local application imports (anything from EESSI/eessi-bot-software-layer)
# (none yet)


# NOTE because one can use any prefix of one of the components below to
# define a filter, we need to make sure that no two filters share the same
# prefix OR we have to change the handling of filters.
FILTER_COMPONENT_ACCEL = 'accelerator'
FILTER_COMPONENT_ARCH = 'architecture'
FILTER_COMPONENT_EXPORT = 'exportvariable'
FILTER_COMPONENT_INST = 'instance'
FILTER_COMPONENT_JOB_ENV_VARS = 'job_env_vars'
FILTER_COMPONENT_JOBID = 'jobid'
FILTER_COMPONENT_REPO = 'repository'
FILTER_COMPONENT_SUBMIT_ARGS = 'submit_args'
FILTER_COMPONENTS = [FILTER_COMPONENT_ACCEL,
                     FILTER_COMPONENT_ARCH,
                     FILTER_COMPONENT_EXPORT,
                     FILTER_COMPONENT_INST,
                     FILTER_COMPONENT_JOBID,
                     FILTER_COMPONENT_REPO,
                     FILTER_COMPONENT_SUBMIT_ARGS
                     ]

# Aliases map an alternative name to a canonical FILTER_COMPONENT.
# 'job_env_vars' is an alias for 'exportvariable' (both specify key=value pairs that
# are exported into the build job's environment).
#
# 'job_env_vars' is intentionally NOT included in FILTER_COMPONENTS: it exists only
# as an alias and is resolved to 'exportvariable' before any prefix matching
# happens. If it were in FILTER_COMPONENTS, the prefix-matching logic would be
# ambiguous because 'job' is a prefix of both 'job_env_vars' and 'jobid', so an
# abbreviation like 'job:...' could match either one. By keeping 'job_env_vars' out
# of FILTER_COMPONENTS and resolving it early, 'job:...' still correctly
# resolves to 'jobid' (the only FILTER_COMPONENTS entry with that prefix).
#
# Aliases are resolved in both add_filter() and remove_filter() before the
# prefix-matching loop runs.
FILTER_COMPONENT_ALIASES = {
    FILTER_COMPONENT_JOB_ENV_VARS: FILTER_COMPONENT_EXPORT,
}

COMPONENT_TOO_SHORT = "component in filter spec '{component}:{value}' is too short; must be 3 characters or longer"
COMPONENT_UNKNOWN = "unknown component={component} in {component}:{value}"
FILTER_EMPTY_VALUE = "value in filter string '{filter_string}' is empty"
FILTER_FORMAT_ERROR = "filter string '{filter_string}' does not conform to format 'component:value'"
UNKNOWN_COMPONENT_CONST = "unknown component constant {component}"

Filter = namedtuple('Filter', ('component', 'value'))


class EESSIBotActionFilterError(Exception):
    """
    Exception to be raised when encountering an error in creating or adding a
    filter
    """

    def __init__(self, value):
        self.value = value

    def __str__(self):
        return self.value


class EESSIBotActionFilter:
    """
    Class for representing a filter that limits in which contexts bot commands
    are applied. A filter contains a list of key:value pairs where the key
    corresponds to a component (see FILTER_COMPONENTS) and the value is a
    string used to filter commands based on the context a command is applied to.
    """
    def __init__(self, filter_string):
        """
        EESSIBotActionFilter constructor

        Args:
            filter_string (string): string containing whitespace separated filters

        Raises:
            EESSIBotActionFilterError: raised if caught when adding filter from
                string
            Exception: logged and raised if caught when adding filter from
                string
        """
        self.action_filters = []
        for _filter in filter_string.split():
            try:
                self.add_filter_from_string(_filter)
            except EESSIBotActionFilterError:
                raise
            except Exception as err:
                log(f"Unexpected err={err}, type(err)={type(err)}")
                raise

    def clear_all(self):
        """
        Clears all filters

        Args:
            No arguments

        Returns:
            None (implicitly)
        """
        self.action_filters = []

    def add_filter(self, component, value):
        """
        Adds a filter given by a component and a value. Uses the full component
        name even if only a prefix was used.

        Args:
            component (string): any prefix (min 3 characters long) of known filter
                components (see FILTER_COMPONENTS)
            value (string): string that represents value of component

        Returns:
            None (implicitly)

        Raises:
           EESSIBotActionFilterError: raised if unknown component is provided
                as argument
        """
        # check if component is supported
        # - it is a 3+ character-long string, _and_
        # - it is a prefix of one of the elements in FILTER_COMPONENTS
        if len(component) < 3:
            msg = COMPONENT_TOO_SHORT.format(component=component, value=value)
            log(msg)
            raise EESSIBotActionFilterError(msg)
        # Resolve aliases first (e.g. 'job_env_vars' -> 'exportvariable') so that
        # prefix-matching below does not get confused by components sharing a
        # prefix (e.g. 'job' is a prefix of both 'job_env_vars' and 'jobid').
        if component in FILTER_COMPONENT_ALIASES:
            component = FILTER_COMPONENT_ALIASES[component]
        full_component = None
        for cis in FILTER_COMPONENTS:
            # NOTE the below code assumes that no two filter share the same
            #      3-character-long prefix (e.g., 'repository' and 'repeat' would
            #      have the same prefix 'rep')
            if cis.startswith(component):
                full_component = cis
                break
        if full_component:
            log(f"processing component {component}")
            # replace '-' with '/' in value when using 'architecture' filter
            #   component (done to make sure that values are comparable)
            if full_component == FILTER_COMPONENT_ARCH:
                value = value.replace('-', '/')
            # replace '=' with '/' in value when using 'accelerator' filter
            #   component (done to make sure that values are comparable)
            if full_component == FILTER_COMPONENT_ACCEL:
                value = value.replace('=', '/')
            self.action_filters.append(Filter(full_component, value))
        else:
            msg = COMPONENT_UNKNOWN.format(component=component, value=value)
            log(msg)
            raise EESSIBotActionFilterError(msg)

    def add_filter_from_string(self, filter_string):
        """
        Adds a filter provided as a string

        Args:
            filter_string (string): filter provided as component:value string

        Returns:
            None (implicitly)

        Raises:
           EESSIBotActionFilterError: raised if filter_string does not conform
               to 'component:value' format or value is empty
        """
        # Split on the first ':' only so that the pattern may itself contain
        # colons (e.g. 'submit_args:--time=01:00:00' or
        # 'exportvariable:PATH=/usr/bin:/bin').
        _filter_split = filter_string.split(':', 1)
        if len(_filter_split) != 2:
            msg = FILTER_FORMAT_ERROR.format(filter_string=filter_string)
            log(msg)
            raise EESSIBotActionFilterError(msg)
        if len(_filter_split[0]) < 3:
            msg = COMPONENT_TOO_SHORT.format(component=_filter_split[0], value=_filter_split[1])
            log(msg)
            raise EESSIBotActionFilterError(msg)
        if len(_filter_split[1]) == 0:
            msg = FILTER_EMPTY_VALUE.format(filter_string=filter_string)
            log(msg)
            raise EESSIBotActionFilterError(msg)
        self.add_filter(_filter_split[0], _filter_split[1])

    def get_filter_by_component(self, component):
        """
        Returns filter values for the provided component.

        Args:
            component (string): one of FILTER_COMPONENTS

        Returns:
            (list): values of the filters for the given component

        Raises:
            EESSIBotActionFilterError: if the component provided is not a known filter
        """
        if component not in FILTER_COMPONENTS:
            msg = UNKNOWN_COMPONENT_CONST.format(component=component)
            raise EESSIBotActionFilterError(msg)

        values = []
        for _filter in self.action_filters:
            if component == _filter.component:
                values.append(_filter.value)
        return values

    def remove_filter(self, component, value):
        """
        Removes all elements matching the filter given by (component, value)

        Args:
            component (string): one of FILTER_COMPONENTS
            value (string): value for the component

        Returns:
            None (implicitly)

        Raises:
            EESSIBotActionFilterError:
                if the provided component name is shorter than 3 characters or
                if the provided component is not a known filter
        """
        if len(component) < 3:
            msg = COMPONENT_TOO_SHORT.format(component=component, value=value)
            log(msg)
            raise EESSIBotActionFilterError(msg)
        # Resolve aliases (e.g. 'job_env_vars' -> 'exportvariable') before matching.
        if component in FILTER_COMPONENT_ALIASES:
            component = FILTER_COMPONENT_ALIASES[component]
        full_component = None
        for cis in FILTER_COMPONENTS:
            # NOTE the below code assumes that no two filter share the same
            #      3-character-long prefix (e.g., 'repository' and 'repeat' would
            #      have the same prefix 'rep')
            if cis.startswith(component):
                full_component = cis
                break
        if not full_component:
            # the component provided as argument is not in the list of FILTER_COMPONENTS
            msg = COMPONENT_UNKNOWN.format(component=component, value=value)
            log(msg)
            raise EESSIBotActionFilterError(msg)

        # need to traverse list from end or next elem after a removed item is
        # skipped
        num_filters = len(self.action_filters)
        for idx in range(num_filters, 0, -1):
            # idx runs from num_filters to 1; this needs to be corrected to
            # num_filters-1 to 0
            index = idx - 1
            # NOTE the below code assumes that no two filter share the same
            #      3-character-long prefix (e.g., 'repository' and 'repeat' would
            #      have the same prefix 'rep')
            _filter = self.action_filters[index]
            if _filter.component.startswith(component) and value == _filter.value:
                log(f"removing filter ({_filter.component}, {value})")
                self.action_filters.pop(index)

    def to_string(self):
        """
        Convert filters to string

        Args:
            No arguments

        Returns:
            string containing filters separated by whitespace
        """
        filter_str_list = []
        for _filter in self.action_filters:
            component = _filter.component
            value = _filter.value
            filter_str_list.append(f"{component}:{value}")
        return " ".join(filter_str_list)

    def check_build_filters(self, context):
        """
        Checks if the filter in self matches a given context which is defined
        by the three components FILTER_COMPONENT_ARCH, FILTER_COMPONENT_INST and
        FILTER_COMPONENT_REPO for building.
        A single component of a filter matches the corresponding component in a
        context if the values for these components are exactly the same.

        Args:
            context (dict) : dictionary that contains (component,value)-pairs
                representing the context in which the method is called

        Returns:
            True if all required components in a given context match their
                corresponding component in a filter
            False otherwise
        """
        # TODO list of components to check could be taken from configuration
        build_components = [FILTER_COMPONENT_ARCH, FILTER_COMPONENT_INST, FILTER_COMPONENT_REPO]
        return self.check_filters(context, build_components)

    def check_filters(self, context, components):
        """
        Checks if the filter in self matches a given context which is defined
        by the provided components.

        A single component of a filter matches the corresponding component in a
        context if the values for these components are exactly the same.

        Args:
            context (dict) : dictionary that contains (component,value)-pairs
                representing the context in which the method is called
                The context is typically defined by a combination of the build
                target (CPU microarchitecture, CernVM-FS repository, optionally
                accelerator architecture) and the build system.
            components (list) : contains constants FILTER_COMPONENT_* that must
                be checked

        Returns:
            True if all required components in a given context match their
                corresponding component in a filter
            False otherwise

        Raises:
            EESSIBotActionFilterError: if any required component is not a known filter
        """
        # examples:
        #   filter: 'arch:intel instance:AWS' --> evaluates to True if
        #     context['architecture'] is 'intel' and if context['instance'] is 'AWS'
        #   filter: 'repository:eessi-2023.06' --> evaluates to True if
        #     context['repository'] is 'eessi-2023.06'

        fn = sys._getframe().f_code.co_name

        # we run three checks:
        # (1) for all required components the filters have to match the context (there could be extra filters though)
        # (2) all filters given have to be present in the context and match
        # (3) if the context defines an accelerator, there must be a filter provided for that
        #
        # the first two checks, we skip filters that are arguments to build jobs (exportvariable or job_env_var)
        #   or arguments to the submission of jobs (submit_arg)

        # check one: for all required components the filters have to match the context
        #
        # we iterate over the components and verify if their value in the given
        #   context equals the corresponding value in the filter
        non_action_filters = [FILTER_COMPONENT_EXPORT, FILTER_COMPONENT_JOB_ENV_VARS, FILTER_COMPONENT_SUBMIT_ARGS]

        for component in components:
            if component in non_action_filters:
                log(f"{fn}(): skipping non-action filter component {component}")
                continue

            # we need the try-except block because components can include any names
            try:
                filter_values = self.get_filter_by_component(component)
            except EESSIBotActionFilterError:
                log(f"{fn}(): filter component '{component}' is unknown")
                raise

            if len(filter_values) == 0:
                # no filter for required component provided --> at least one filter per
                #   required component must be given
                log(f"{fn}(): no filter for required component '{component}' provided; check_filters returns False")
                return False

            if component in context:
                # check if all values for the filter are identical to the value
                #   of the component in the context
                context_value = context[component]
                if component == FILTER_COMPONENT_ARCH:
                    if context_value.startswith('linux'):
                        # strip leading OS name from architecture string
                        context_value = '/'.join(context_value.split('/')[1:])
                    # replace '-' with '/' in architecture string
                    context_value = context_value.replace('-', '/')
                if component == FILTER_COMPONENT_ACCEL:
                    context_value = context_value.replace('=', '/')
                for filter_value in filter_values:
                    # TODO should we support both pattern matching and exact matching via the configuration?
                    if filter_value != context_value:
                        msg = f"{fn}(): filter value '{filter_value}'"
                        msg += f" does not match context value '{context_value}'"
                        msg += f" for component '{component}';"
                        msg += " check_filters returns False"
                        log(msg)
                        return False
            else:
                # missing required component in context, could lead to unexpected behavior
                msg = f"{fn}(): missing required component '{component}' in context; check_filters returns False"
                log(msg)
                return False

        # check two: all defined filters have to match the context
        #
        # we iterate over all defined filters
        # Skip export variables, job env vars and submit args: they are not action filters
        non_action_filters = [FILTER_COMPONENT_EXPORT, FILTER_COMPONENT_JOB_ENV_VARS, FILTER_COMPONENT_SUBMIT_ARGS]
        for af in self.action_filters:
            if af.component in non_action_filters:
                log(f"{fn}(): skipping non-action filter component {component}")
                continue

            if af.component in context:
                context_value = context[af.component]
                # replace - with / in architecture component
                if af.component == FILTER_COMPONENT_ARCH:
                    context_value = context_value.replace('-', '/')
                # replace = with / in accelerator component
                if af.component == FILTER_COMPONENT_ACCEL:
                    context_value = context_value.replace('=', '/')

                if af.value != context_value:
                    msg = f"{fn}(): filter value '{af.value}'"
                    msg += f" does not match context value '{context_value}'"
                    msg += f" for component '{af.component}';"
                    msg += " check_filters returns False"
                    log(msg)
                    return False
            # Action filter wasn't found in the context, we won't allow this as it might lead to unexpected results
            else:
                msg = f"{fn}(): context lacks component '{af.component}' which is provided by filter;"
                msg += " check_filters returns False"
                log(msg)
                return False

        # check three: if the context includes an accelerator, there must be a filter for that
        #
        # If the context declares an accelerator, enforce that a filter is defined for this component as well
        # I.e. this enforces that a context with accelerator will only be used if an accelerator is explicitely
        # requested in the build command, thus preventing CPU-only builds on GPU nodes (unless explicitely intended)
        if (
            FILTER_COMPONENT_ACCEL in context and not
            any(af.component == FILTER_COMPONENT_ACCEL for af in self.action_filters)
        ):
            msg = f"{fn}(): context contains component '{FILTER_COMPONENT_ACCEL}', but filter does not provide it"
            msg += " check_filters returns False"
            log(msg)
            return False

        return True
