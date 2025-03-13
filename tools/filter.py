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
import re

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
FILTER_COMPONENT_JOB = 'job'
FILTER_COMPONENT_REPO = 'repository'
FILTER_COMPONENTS = [FILTER_COMPONENT_ACCEL,
                     FILTER_COMPONENT_ARCH,
                     FILTER_COMPONENT_EXPORT,
                     FILTER_COMPONENT_INST,
                     FILTER_COMPONENT_JOB,
                     FILTER_COMPONENT_REPO
                     ]

COMPONENT_TOO_SHORT = "component in filter spec '{component}:{pattern}' is too short; must be 3 characters or longer"
COMPONENT_UNKNOWN = "unknown component={component} in {component}:{pattern}"
FILTER_EMPTY_PATTERN = "pattern in filter string '{filter_string}' is empty"
FILTER_FORMAT_ERROR = "filter string '{filter_string}' does not conform to format 'component:pattern'"
UNKNOWN_COMPONENT_CONST = "unknown component constant {component}"

Filter = namedtuple('Filter', ('component', 'pattern'))


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
    pattern used to filter commands based on the context a command is applied to.
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

    def add_filter(self, component, pattern):
        """
        Adds a filter given by a component and a pattern

        Args:
            component (string): any prefix (min 3 characters long) of known filter
                components (see FILTER_COMPONENTS)
            pattern (string): regular expression pattern that is applied to a
                string representing the component

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
            msg = COMPONENT_TOO_SHORT.format(component=component, pattern=pattern)
            log(msg)
            raise EESSIBotActionFilterError(msg)
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
            # replace '-' with '/' in pattern when using 'architecture' filter
            #   component (done to make sure that values are comparable)
            if full_component == FILTER_COMPONENT_ARCH:
                pattern = pattern.replace('-', '/')
            # replace '=' with '/' in pattern when using 'accelerator' filter
            #   component (done to make sure that values are comparable)
            if full_component == FILTER_COMPONENT_ACCEL:
                pattern = pattern.replace('=', '/')
            self.action_filters.append(Filter(full_component, pattern))
        else:
            msg = COMPONENT_UNKNOWN.format(component=component, pattern=pattern)
            log(msg)
            raise EESSIBotActionFilterError(msg)

    def add_filter_from_string(self, filter_string):
        """
        Adds a filter provided as a string

        Args:
            filter_string (string): filter provided as component:pattern string

        Returns:
            None (implicitly)

        Raises:
           EESSIBotActionFilterError: raised if filter_string does not conform
               to 'component:pattern' format or pattern is empty
        """
        _filter_split = filter_string.split(':')
        if len(_filter_split) != 2:
            msg = FILTER_FORMAT_ERROR.format(filter_string=filter_string)
            log(msg)
            raise EESSIBotActionFilterError(msg)
        if len(_filter_split[0]) < 3:
            msg = COMPONENT_TOO_SHORT.format(component=_filter_split[0], pattern=_filter_split[1])
            log(msg)
            raise EESSIBotActionFilterError(msg)
        if len(_filter_split[1]) == 0:
            msg = FILTER_EMPTY_PATTERN.format(filter_string=filter_string)
            log(msg)
            raise EESSIBotActionFilterError(msg)
        self.add_filter(_filter_split[0], _filter_split[1])

    def get_filter_by_component(self, component):
        """
        Returns filter pattern for component.

        Args:
            component (string): one of FILTER_COMPONENTS

        Returns:
            (list): list of pattern for filters whose component matches argument
        """
        if component not in FILTER_COMPONENTS:
            msg = UNKNOWN_COMPONENT_CONST.format(component=component)
            raise EESSIBotActionFilterError(msg)

        pattern = []
        for _filter in self.action_filters:
            if component == _filter.component:
                pattern.append(_filter.pattern)
        return pattern

    def remove_filter(self, component, pattern):
        """
        Removes all elements matching the filter given by (component, pattern)

        Args:
            component (string): one of FILTER_COMPONENTS
            pattern (string): regex that is applied to a string representing the component

        Returns:
            None (implicitly)
        """
        if len(component) < 3:
            msg = COMPONENT_TOO_SHORT.format(component=component, pattern=pattern)
            log(msg)
            raise EESSIBotActionFilterError(msg)
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
            msg = COMPONENT_UNKNOWN.format(component=component, pattern=pattern)
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
            if _filter.component.startswith(component) and pattern == _filter.pattern:
                log(f"removing filter ({_filter.component}, {pattern})")
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
            cm = _filter.component
            re = _filter.pattern
            filter_str_list.append(f"{cm}:{re}")
        return " ".join(filter_str_list)

    def check_filters(self, context):
        """
        Checks filters for a given context which is defined by one to five
        components (accelerator, architecture, instance, job, repository)

        Args:
            context (dict) : dictionary that maps components to their value

        Returns:
            True if no filters are defined or all defined filters match
                their corresponding component in the given context
            False if any defined filter does not match its corresponding
                component in the given context
        """
        # if no filters are defined we return True
        if len(self.action_filters) == 0:
            return True

        # we have at least one filter which has to match or we return False
        check = False

        # examples:
        #   filter: 'arch:intel instance:AWS' --> evaluates to True if
        #       context['architecture'] matches 'intel' and if
        #       context['instance'] matches 'AWS'
        #   filter: 'repository:eessi-2023.06' --> evaluates to True if
        #       context['repository'] matches 'eessi-2023.06'

        # we iterate over all defined filters
        for af in self.action_filters:
            if af.component in context:
                value = context[af.component]
                # replace - with / in architecture component
                if af.component == FILTER_COMPONENT_ARCH:
                    value = value.replace('-', '/')
                # replace = with / in accelerator component
                if af.component == FILTER_COMPONENT_ACCEL:
                    value = value.replace('=', '/')
                if re.search(af.pattern, value):
                    # if the pattern of the filter matches
                    check = True
                else:
                    check = False
                    break
        return check
