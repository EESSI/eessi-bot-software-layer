# Tests for functions defined in 'tools/filter.py' of the EESSI
# build-and-deploy bot, see https://github.com/EESSI/eessi-bot-software-layer
#
# The bot helps with requests to add software installations to the
# EESSI software layer, see https://github.com/EESSI/software-layer
#
# author: Thomas Roeblitz (@trz42)
#
# license: GPLv2
#

# Standard library imports
import copy

# Third party imports (anything installed into the local Python environment)
import pytest

# Local application imports (anything from EESSI/eessi-bot-software-layer)
from tools.filter import (COMPONENT_TOO_SHORT,
                          COMPONENT_UNKNOWN,
                          EESSIBotActionFilter,
                          EESSIBotActionFilterError,
                          FILTER_EMPTY_PATTERN,
                          FILTER_FORMAT_ERROR)


def test_empty_action_filter():
    af = EESSIBotActionFilter("")
    expected = ''
    actual = af.to_string()
    assert expected == actual


def test_add_wellformed_filter_from_string():
    af = EESSIBotActionFilter("")
    component = 'acc'
    pattern = 'nvidia/cc80'
    af.add_filter_from_string(f"{component}:{pattern}")
    expected = f"accelerator:{pattern}"
    actual = af.to_string()
    assert expected == actual


def test_add_non_wellformed_filter_from_string():
    af = EESSIBotActionFilter("")
    component1 = 'acc'
    filter_string1 = f"{component1}"
    with pytest.raises(Exception) as err1:
        af.add_filter_from_string(filter_string1)
    assert err1.type == EESSIBotActionFilterError
    expected_msg1 = FILTER_FORMAT_ERROR.format(filter_string=filter_string1)
    assert str(err1.value) == expected_msg1

    component2 = 'a'
    pattern2 = 'zen4'
    filter_string2 = f"{component2}:{pattern2}"
    with pytest.raises(Exception) as err2:
        af.add_filter_from_string(filter_string2)
    assert err2.type == EESSIBotActionFilterError
    expected_msg2 = COMPONENT_TOO_SHORT.format(component=component2, pattern=pattern2)
    assert str(err2.value) == expected_msg2

    component3 = 'arc'
    pattern3 = ''
    filter_string3 = f"{component3}:{pattern3}"
    with pytest.raises(Exception) as err3:
        af.add_filter_from_string(filter_string3)
    assert err3.type == EESSIBotActionFilterError
    expected_msg3 = FILTER_EMPTY_PATTERN.format(filter_string=filter_string3)
    assert str(err3.value) == expected_msg3


def test_add_single_action_filter():
    af = EESSIBotActionFilter("")
    component = 'arch'
    pattern = '.*intel.*'
    af.add_filter(component, pattern)
    expected = "architecture:.*intel.*"
    actual = af.to_string()
    assert expected == actual


def test_add_non_supported_component():
    af = EESSIBotActionFilter("")
    component = 'machine'
    pattern = '.*intel.*'
    with pytest.raises(Exception) as err:
        af.add_filter(component, pattern)
    assert err.type == EESSIBotActionFilterError
    expected_msg = COMPONENT_UNKNOWN.format(component=component, pattern=pattern)
    assert str(err.value) == expected_msg


def test_add_too_short_supported_component():
    af = EESSIBotActionFilter("")
    component = 'a'
    pattern = '.*intel.*'
    with pytest.raises(Exception) as err:
        af.add_filter(component, pattern)
    assert err.type == EESSIBotActionFilterError
    expected_msg = COMPONENT_TOO_SHORT.format(component=component, pattern=pattern)
    assert str(err.value) == expected_msg


# TODO tests for removing filters
@pytest.fixture
def complex_filter():
    af = EESSIBotActionFilter("")
    component1 = 'arch'
    pattern1 = '.*intel.*'
    af.add_filter(component1, pattern1)
    component2 = 'repo'
    pattern2 = 'nessi.no-2022.*'
    af.add_filter(component2, pattern2)
    component3 = 'inst'
    pattern3 = '[aA]'
    af.add_filter(component3, pattern3)
    yield af


def test_remove_existing_filter(complex_filter):
    component1 = 'architecture'
    pattern1 = '.*intel.*'
    filter_string1 = f"{component1}:{pattern1}"
    component2 = 'repository'
    pattern2 = 'nessi.no-2022.*'
    filter_string2 = f"{component2}:{pattern2}"
    component3 = 'instance'
    pattern3 = '[aA]'
    filter_string3 = f"{component3}:{pattern3}"

    # remove last filter
    org_filter = copy.deepcopy(complex_filter)
    org_filter.remove_filter(component3, pattern3)
    expected = filter_string1
    expected += f" {filter_string2}"
    actual = org_filter.to_string()
    assert expected == actual

    # remove second last filter
    org_filter = copy.deepcopy(complex_filter)
    org_filter.remove_filter(component2, pattern2)
    expected = filter_string1
    expected += f" {filter_string3}"
    actual = org_filter.to_string()
    assert expected == actual

    # remove first filter
    org_filter = copy.deepcopy(complex_filter)
    org_filter.remove_filter(component1, pattern1)
    expected = filter_string2
    expected += f" {filter_string3}"
    actual = org_filter.to_string()
    assert expected == actual


def test_remove_non_existing_filter(complex_filter):
    component = 'accel'
    pattern = 'amd/gfx90a'

    # remove non-existing filter
    org_filter = copy.deepcopy(complex_filter)
    org_filter.remove_filter(component, pattern)
    org_filter_str = org_filter.to_string()
    complex_filter_str = complex_filter.to_string()
    assert org_filter_str == complex_filter_str


def test_remove_filter_errors(complex_filter):
    component1 = 'ac'
    pattern1 = 'amd/gfx90a'
    component2 = 'operating_system'
    pattern2 = 'linux'

    # remove filter using too short component name
    org_filter = copy.deepcopy(complex_filter)
    with pytest.raises(Exception) as err1:
        org_filter.remove_filter(component1, pattern1)
    assert err1.type == EESSIBotActionFilterError
    expected_msg1 = COMPONENT_TOO_SHORT.format(component=component1, pattern=pattern1)
    assert str(err1.value) == expected_msg1

    # remove filter using unknown component name
    org_filter = copy.deepcopy(complex_filter)
    with pytest.raises(Exception) as err2:
        org_filter.remove_filter(component2, pattern2)
    assert err2.type == EESSIBotActionFilterError
    expected_msg2 = COMPONENT_UNKNOWN.format(component=component2, pattern=pattern2)
    assert str(err2.value) == expected_msg2


def test_check_matching_empty_filter():
    af = EESSIBotActionFilter("")
    expected = ''
    actual = af.to_string()
    assert expected == actual

    context = {"arch": "foo"}
    actual = af.check_filters(context)
    expected = True
    assert expected == actual


def test_check_matching_simple_filter():
    af = EESSIBotActionFilter("")
    component = 'arch'
    pattern = '.*intel.*'
    af.add_filter(component, pattern)
    expected = f"architecture:{pattern}"
    actual = af.to_string()
    assert expected == actual

    context = {"architecture": "x86_64/intel/cascadelake"}
    actual = af.check_filters(context)
    expected = True
    assert expected == actual


def test_create_complex_filter(complex_filter):
    expected = "architecture:.*intel.*"
    expected += " repository:nessi.no-2022.*"
    expected += " instance:[aA]"
    actual = complex_filter.to_string()
    assert expected == actual


def test_match_empty_context(complex_filter):
    context = {}
    expected = False
    actual = complex_filter.check_filters(context)
    assert expected == actual


# A context lacking keys for components in the filter shouldn't match
def test_match_sparse_context(complex_filter):
    context = {"architecture": "x86_64/intel/cascadelake"}
    expected = False
    actual = complex_filter.check_filters(context)
    assert expected == actual


def test_matching_context(complex_filter):
    context = {"architecture": "x86_64/intel/cascadelake", "repository": "nessi.no-2022.A", "instance": "A"}
    expected = True
    actual = complex_filter.check_filters(context)
    assert expected == actual


def test_non_match_archictecture_context(complex_filter):
    context = {"architecture": "x86_64/amd/zen4", "repository": "EESSI", "instance": "mybot", "job": 1234}
    expected = False
    actual = complex_filter.check_filters(context)
    assert expected == actual


def test_non_match_repository_context(complex_filter):
    context = {"architecture": "x86_64/intel/cascadelake", "repository": "EESSI", "instance": "A"}
    expected = False
    actual = complex_filter.check_filters(context)
    assert expected == actual

def test_non_match_instance_context(complex_filter):
    context = {"architecture": "x86_64/intel/cascadelake", "repository": "nessi.no-2022.A", "instance": "B"}
    expected = False
    actual = complex_filter.check_filters(context)
    assert expected == actual


# If additional keys are present in the context for which no filter component is defined
# it should not prevent a match
def test_match_additional_context(complex_filter):
    context = {"architecture": "x86_64/intel/cascadelake", "repository": "nessi.no-2022.A", "instance": "A", "job": 1234}
    expected = True
    actual = complex_filter.check_filters(context)
    assert expected == actual

@pytest.fixture
def arch_filter_slash_syntax():
    af = EESSIBotActionFilter("")
    component = 'arch'
    pattern = '.*/intel/.*'
    af.add_filter(component, pattern)
    yield af


def test_match_architecture_syntax_slash(arch_filter_slash_syntax):
    context = {"architecture": "x86_64/intel/cascadelake", "repository": "EESSI"}
    expected = True
    actual = arch_filter_slash_syntax.check_filters(context)
    assert expected == actual

    context = {"architecture": "x86_64-intel-cascadelake"}
    expected = True
    actual = arch_filter_slash_syntax.check_filters(context)
    assert expected == actual


@pytest.fixture
def arch_filter_dash_syntax():
    af = EESSIBotActionFilter("")
    component = 'arch'
    pattern = '.*-intel-.*'
    af.add_filter(component, pattern)
    yield af


def test_match_architecture_syntax_dash(arch_filter_dash_syntax):
    context = {"architecture": "x86_64-intel-cascadelake", "repository": "EESSI"}
    expected = True
    actual = arch_filter_dash_syntax.check_filters(context)
    assert expected == actual

    context = {"architecture": "x86_64/intel-cascadelake"}
    expected = True
    actual = arch_filter_dash_syntax.check_filters(context)
    assert expected == actual


@pytest.fixture
def accel_filter_slash_syntax():
    af = EESSIBotActionFilter("")
    component = 'accel'
    pattern = 'nvidia/.*'
    af.add_filter(component, pattern)
    yield af


def test_match_accelerator_syntax_slash(accel_filter_slash_syntax):
    context = {"accelerator": "nvidia/cc70", "repository": "EESSI"}
    expected = True
    actual = accel_filter_slash_syntax.check_filters(context)
    assert expected == actual

    context = {"accelerator": "nvidia=cc70"}
    expected = True
    actual = accel_filter_slash_syntax.check_filters(context)
    assert expected == actual


@pytest.fixture
def accel_filter_equal_syntax():
    af = EESSIBotActionFilter("")
    component = 'accel'
    pattern = 'amd=gfx90a'
    af.add_filter(component, pattern)
    yield af


def test_match_accelerator_syntax_equal(accel_filter_equal_syntax):
    context = {"accelerator": "amd=gfx90a", "repository": "EESSI"}
    expected = True
    actual = accel_filter_equal_syntax.check_filters(context)
    assert expected == actual

    context = {"accelerator": "amd/gfx90a"}
    expected = True
    actual = accel_filter_equal_syntax.check_filters(context)
    assert expected == actual
