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
from unittest.mock import patch
import pytest

# Local application imports (anything from EESSI/eessi-bot-software-layer)
from tools.filter import (COMPONENT_TOO_SHORT,
                          COMPONENT_UNKNOWN,
                          EESSIBotActionFilter,
                          EESSIBotActionFilterError,
                          FILTER_COMPONENT_ACCEL,
                          FILTER_COMPONENT_ARCH,
                          FILTER_COMPONENT_INST,
                          FILTER_COMPONENT_REPO,
                          FILTER_EMPTY_VALUE,
                          FILTER_FORMAT_ERROR,
                          UNKNOWN_COMPONENT_CONST)


def test_empty_action_filter():
    af = EESSIBotActionFilter("")
    expected = ''
    actual = af.to_string()
    assert expected == actual


def test_add_wellformed_filter_from_string():
    af = EESSIBotActionFilter("")
    component = 'acc'
    value = 'nvidia/cc80'
    af.add_filter_from_string(f"{component}:{value}")
    expected = f"accelerator:{value}"
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
    value2 = 'zen4'
    filter_string2 = f"{component2}:{value2}"
    with pytest.raises(Exception) as err2:
        af.add_filter_from_string(filter_string2)
    assert err2.type == EESSIBotActionFilterError
    expected_msg2 = COMPONENT_TOO_SHORT.format(component=component2, value=value2)
    assert str(err2.value) == expected_msg2

    component3 = 'arc'
    value3 = ''
    filter_string3 = f"{component3}:{value3}"
    with pytest.raises(Exception) as err3:
        af.add_filter_from_string(filter_string3)
    assert err3.type == EESSIBotActionFilterError
    expected_msg3 = FILTER_EMPTY_VALUE.format(filter_string=filter_string3)
    assert str(err3.value) == expected_msg3


def test_add_single_action_filter():
    af = EESSIBotActionFilter("")
    component = 'arch'
    value = '.*intel.*'
    af.add_filter(component, value)
    expected = "architecture:.*intel.*"
    actual = af.to_string()
    assert expected == actual


def test_add_non_supported_component():
    af = EESSIBotActionFilter("")
    component = 'machine'
    value = '.*intel.*'
    with pytest.raises(Exception) as err:
        af.add_filter(component, value)
    assert err.type == EESSIBotActionFilterError
    expected_msg = COMPONENT_UNKNOWN.format(component=component, value=value)
    assert str(err.value) == expected_msg


def test_add_too_short_supported_component():
    af = EESSIBotActionFilter("")
    component = 'a'
    value = '.*intel.*'
    with pytest.raises(Exception) as err:
        af.add_filter(component, value)
    assert err.type == EESSIBotActionFilterError
    expected_msg = COMPONENT_TOO_SHORT.format(component=component, value=value)
    assert str(err.value) == expected_msg


# TODO tests for removing filters
@pytest.fixture
def complex_filter():
    af = EESSIBotActionFilter("")
    component1 = 'arch'
    value1 = '.*intel.*'
    af.add_filter(component1, value1)
    component2 = 'repo'
    value2 = 'nessi.no-2022.*'
    af.add_filter(component2, value2)
    component3 = 'inst'
    value3 = '[aA]'
    af.add_filter(component3, value3)
    yield af


def test_remove_existing_filter(complex_filter):
    component1 = 'architecture'
    value1 = '.*intel.*'
    filter_string1 = f"{component1}:{value1}"
    component2 = 'repository'
    value2 = 'nessi.no-2022.*'
    filter_string2 = f"{component2}:{value2}"
    component3 = 'instance'
    value3 = '[aA]'
    filter_string3 = f"{component3}:{value3}"

    # remove last filter
    org_filter = copy.deepcopy(complex_filter)
    org_filter.remove_filter(component3, value3)
    expected = filter_string1
    expected += f" {filter_string2}"
    actual = org_filter.to_string()
    assert expected == actual

    # remove second last filter
    org_filter = copy.deepcopy(complex_filter)
    org_filter.remove_filter(component2, value2)
    expected = filter_string1
    expected += f" {filter_string3}"
    actual = org_filter.to_string()
    assert expected == actual

    # remove first filter
    org_filter = copy.deepcopy(complex_filter)
    org_filter.remove_filter(component1, value1)
    expected = filter_string2
    expected += f" {filter_string3}"
    actual = org_filter.to_string()
    assert expected == actual


def test_remove_non_existing_filter(complex_filter):
    component = 'accel'
    value = 'amd/gfx90a'

    # remove non-existing filter
    org_filter = copy.deepcopy(complex_filter)
    org_filter.remove_filter(component, value)
    org_filter_str = org_filter.to_string()
    complex_filter_str = complex_filter.to_string()
    assert org_filter_str == complex_filter_str


def test_remove_filter_errors(complex_filter):
    component1 = 'ac'
    value1 = 'amd/gfx90a'
    component2 = 'operating_system'
    value2 = 'linux'

    # remove filter using too short component name
    org_filter = copy.deepcopy(complex_filter)
    with pytest.raises(Exception) as err1:
        org_filter.remove_filter(component1, value1)
    assert err1.type == EESSIBotActionFilterError
    expected_msg1 = COMPONENT_TOO_SHORT.format(component=component1, value=value1)
    assert str(err1.value) == expected_msg1

    # remove filter using unknown component name
    org_filter = copy.deepcopy(complex_filter)
    with pytest.raises(Exception) as err2:
        org_filter.remove_filter(component2, value2)
    assert err2.type == EESSIBotActionFilterError
    expected_msg2 = COMPONENT_UNKNOWN.format(component=component2, value=value2)
    assert str(err2.value) == expected_msg2


def test_empty_filter_to_string():
    af = EESSIBotActionFilter("")
    expected = ''
    actual = af.to_string()
    assert expected == actual


def test_empty_filter_empty_context_no_component():
    af = EESSIBotActionFilter("")
    context = {}
    components = []
    actual = af.check_filters(context, components)
    expected = True
    assert expected == actual


def test_empty_filter_arch_context_no_component():
    af = EESSIBotActionFilter("")
    context = {"arch": "foo"}
    components = []
    actual = af.check_filters(context, components)
    expected = True
    assert expected == actual


def test_empty_filter_arch_context_arch_component():
    af = EESSIBotActionFilter("")
    context = {"arch": "foo"}
    components = [FILTER_COMPONENT_ARCH]
    actual = af.check_filters(context, components)
    expected = False
    # if component to check is given, they need to be present in filter and
    # context
    assert expected == actual


def test_empty_filter_empty_context_arch_component():
    af = EESSIBotActionFilter("")
    context = {}
    components = [FILTER_COMPONENT_ARCH]
    actual = af.check_filters(context, components)
    expected = False
    # if component to check is given, they need to be present in filter and
    # context
    assert expected == actual


def test_arch_filter_to_string():
    af = EESSIBotActionFilter("")
    component = 'arch'
    value = '.*intel.*'
    af.add_filter(component, value)
    expected = f"architecture:{value}"
    actual = af.to_string()
    assert expected == actual


def test_arch_filter_no_context_other_component():
    af = EESSIBotActionFilter("")
    component = 'arch'
    value = 'x86_64/intel/cascadelake'
    af.add_filter(component, value)
    context = {"architecture": "x86_64/intel/cascadelake"}
    components = ['OTHER']
    with pytest.raises(Exception) as err:
        af.check_filters(context, components)
    assert err.type == EESSIBotActionFilterError
    expected_msg = UNKNOWN_COMPONENT_CONST.format(component=components[0])
    assert str(err.value) == expected_msg


def test_arch_filter_arch_context_arch_component():
    af = EESSIBotActionFilter("")
    component = 'arch'
    value = 'x86_64/intel/cascadelake'
    af.add_filter(component, value)
    context = {"architecture": "x86_64/intel/cascadelake"}
    components = [FILTER_COMPONENT_ARCH]
    actual = af.check_filters(context, components)
    expected = True
    assert expected == actual


def test_arch_filter_arch_context_no_component():
    af = EESSIBotActionFilter("")
    component = 'arch'
    value = 'x86_64/intel/cascadelake'
    af.add_filter(component, value)
    context = {"architecture": "x86_64/intel/cascadelake"}
    components = []
    actual = af.check_filters(context, components)
    expected = True
    assert expected == actual


def test_arch_filter_no_context_no_component():
    af = EESSIBotActionFilter("")
    component = 'arch'
    value = 'x86_64/intel/cascadelake'
    af.add_filter(component, value)
    context = {}
    components = []
    actual = af.check_filters(context, components)
    expected = True
    assert expected == actual


def test_arch_filter_no_context_arch_component():
    af = EESSIBotActionFilter("")
    component = 'arch'
    value = 'x86_64/intel/cascadelake'
    af.add_filter(component, value)
    context = {}
    components = [FILTER_COMPONENT_ARCH]
    actual = af.check_filters(context, components)
    expected = False
    assert expected == actual


def test_arch_filter_arch_context_inst_component():
    af = EESSIBotActionFilter("")
    component = 'arch'
    value = 'x86_64/intel/cascadelake'
    af.add_filter(component, value)
    context = {"architecture": "x86_64/intel/cascadelake"}
    components = [FILTER_COMPONENT_INST]
    actual = af.check_filters(context, components)
    expected = False
    assert expected == actual


def test_arch_filter_arch_context_two_components():
    af = EESSIBotActionFilter("")
    component = 'arch'
    value = 'x86_64/intel/cascadelake'
    af.add_filter(component, value)
    context = {"architecture": "x86_64/intel/cascadelake"}
    components = [FILTER_COMPONENT_ARCH, FILTER_COMPONENT_INST]
    actual = af.check_filters(context, components)
    expected = False
    assert expected == actual


def test_complex_filter_to_string(complex_filter):
    expected = "architecture:.*intel.*"
    expected += " repository:nessi.no-2022.*"
    expected += " instance:[aA]"
    actual = complex_filter.to_string()
    assert expected == actual


def test_complex_filter_no_context_other_component(complex_filter):
    context = {"architecture": ".*intel.*"}
    components = ['OTHER']
    with pytest.raises(Exception) as err:
        complex_filter.check_filters(context, components)
    assert err.type == EESSIBotActionFilterError
    expected_msg = UNKNOWN_COMPONENT_CONST.format(component=components[0])
    assert str(err.value) == expected_msg


def test_complex_filter_no_context_no_component(complex_filter):
    context = {}
    components = []
    expected = True
    actual = complex_filter.check_filters(context, components)
    assert expected == actual


# def test_complex_filter_no_context_no_component(complex_filter):
#     context = {}
#     components = []
#     expected = True
#     actual = complex_filter.check_filters(context, components)
#     assert expected == actual


def test_complex_filter_arch_context_arch_component(complex_filter):
    context = {"architecture": ".*intel.*"}
    components = [FILTER_COMPONENT_ARCH]
    expected = True
    actual = complex_filter.check_filters(context, components)
    assert expected == actual


def test_complex_filter_job_context_arch_component(complex_filter):
    context = {"architecture": ".*intel.*", "job": 1234}
    components = [FILTER_COMPONENT_ARCH]
    expected = True
    actual = complex_filter.check_filters(context, components)
    assert expected == actual


def test_complex_filter_repo_context_arch_and_repo_components(complex_filter):
    context = {"architecture": ".*intel.*", "repository": "EESSI"}
    components = [FILTER_COMPONENT_ARCH, FILTER_COMPONENT_REPO]
    expected = False
    actual = complex_filter.check_filters(context, components)
    assert expected == actual


@pytest.fixture
def arch_filter_slash_syntax():
    af = EESSIBotActionFilter("")
    component = 'arch'
    value = 'x86_64/intel/cascadelake'
    af.add_filter(component, value)
    yield af


def test_match_architecture_syntax_slash(arch_filter_slash_syntax):
    components = [FILTER_COMPONENT_ARCH]
    context = {"architecture": "x86_64/intel/cascadelake"}
    expected = True
    actual = arch_filter_slash_syntax.check_filters(context, components)
    assert expected == actual

    context = {"architecture": "x86_64-intel-cascadelake"}
    expected = True
    actual = arch_filter_slash_syntax.check_filters(context, components)
    assert expected == actual


@pytest.fixture
def arch_filter_dash_syntax():
    af = EESSIBotActionFilter("")
    component = 'arch'
    value = 'x86_64-intel-cascadelake'
    af.add_filter(component, value)
    yield af


def test_match_architecture_syntax_dash(arch_filter_dash_syntax):
    components = [FILTER_COMPONENT_ARCH]
    context = {"architecture": "x86_64-intel-cascadelake"}
    expected = True
    actual = arch_filter_dash_syntax.check_filters(context, components)
    assert expected == actual

    context = {"architecture": "x86_64/intel-cascadelake"}
    expected = True
    actual = arch_filter_dash_syntax.check_filters(context, components)
    assert expected == actual


@pytest.fixture
def accel_filter_slash_syntax():
    af = EESSIBotActionFilter("")
    component = 'accel'
    value = 'nvidia/cc70'
    af.add_filter(component, value)
    yield af


def test_match_accelerator_syntax_slash(accel_filter_slash_syntax):
    components = [FILTER_COMPONENT_ACCEL]
    context = {"accelerator": "nvidia/cc70"}
    expected = True
    actual = accel_filter_slash_syntax.check_filters(context, components)
    assert expected == actual

    context = {"accelerator": "nvidia=cc70"}
    expected = True
    actual = accel_filter_slash_syntax.check_filters(context, components)
    assert expected == actual


@pytest.fixture
def accel_filter_equal_syntax():
    af = EESSIBotActionFilter("")
    component = 'accel'
    value = 'amd=gfx90a'
    af.add_filter(component, value)
    yield af


def test_match_accelerator_syntax_equal(accel_filter_equal_syntax):
    components = [FILTER_COMPONENT_ACCEL]
    context = {"accelerator": "amd=gfx90a"}
    expected = True
    actual = accel_filter_equal_syntax.check_filters(context, components)
    assert expected == actual

    context = {"accelerator": "amd/gfx90a"}
    expected = True
    actual = accel_filter_equal_syntax.check_filters(context, components)
    assert expected == actual

# All after this line is generated by Claude (via Cursor)
# import pytest
# from tools.filter import (EESSIBotActionFilter,
#                           EESSIBotActionFilterError,
#                           FILTER_COMPONENT_ARCH,
#                           FILTER_COMPONENT_INST,
#                           FILTER_COMPONENT_REPO)


def test_filter_creation():
    """Test basic filter creation from string"""
    filter_str = "arch:x86_64 inst:AWS repo:eessi-2023.06"
    action_filter = EESSIBotActionFilter(filter_str)

    # Check that filters were parsed correctly
    assert len(action_filter.action_filters) == 3
    assert action_filter.get_filter_by_component(FILTER_COMPONENT_ARCH) == ['x86_64']
    assert action_filter.get_filter_by_component(FILTER_COMPONENT_INST) == ['AWS']
    assert action_filter.get_filter_by_component(FILTER_COMPONENT_REPO) == ['eessi-2023.06']


def test_unexpected_exception_handling():
    """Test that unexpected exceptions in filter creation are logged and re-raised"""
    # Create a mock exception
    mock_exception = ValueError("Test unexpected error")

    # Mock the log function to verify it's called
    with patch('tools.filter.log') as mock_log:
        # Mock the add_filter_from_string method to raise our mock exception
        with patch.object(EESSIBotActionFilter, 'add_filter_from_string', side_effect=mock_exception):
            # Try to create a filter, which should raise our mock exception
            with pytest.raises(ValueError) as exc_info:
                EESSIBotActionFilter("arch:x86_64")

            # Verify the exception was re-raised
            assert exc_info.value == mock_exception

            # Verify the log function was called with the expected message
            mock_log.assert_called_once()
            log_call_args = mock_log.call_args[0][0]
            assert "Unexpected err=" in log_call_args
            assert "Test unexpected error" in log_call_args
            assert "type(err)=<class 'ValueError'>" in log_call_args 


def test_filter_creation_invalid_format():
    """Test filter creation with invalid format"""
    with pytest.raises(EESSIBotActionFilterError):
        EESSIBotActionFilter("invalid_format")


def test_filter_creation_empty_value():
    """Test filter creation with empty value"""
    with pytest.raises(EESSIBotActionFilterError):
        EESSIBotActionFilter("arch:")


def test_filter_creation_short_component():
    """Test filter creation with component name too short"""
    with pytest.raises(EESSIBotActionFilterError):
        EESSIBotActionFilter("ar:x86_64")


def test_add_filter():
    """Test adding a filter manually"""
    action_filter = EESSIBotActionFilter("")
    action_filter.add_filter("arch", "x86_64")
    assert action_filter.get_filter_by_component(FILTER_COMPONENT_ARCH) == ['x86_64']


def test_remove_filter():
    """Test removing a filter"""
    action_filter = EESSIBotActionFilter("arch:x86_64 inst:AWS")
    action_filter.remove_filter("arch", "x86_64")
    assert len(action_filter.get_filter_by_component(FILTER_COMPONENT_ARCH)) == 0
    assert len(action_filter.get_filter_by_component(FILTER_COMPONENT_INST)) == 1


def test_check_build_filters():
    """Test checking build filters against a context"""
    action_filter = EESSIBotActionFilter("arch:x86_64 inst:AWS repo:eessi-2023.06")

    # Matching context
    matching_context = {
        FILTER_COMPONENT_ARCH: "x86_64",
        FILTER_COMPONENT_INST: "AWS",
        FILTER_COMPONENT_REPO: "eessi-2023.06"
    }
    assert action_filter.check_build_filters(matching_context) is True

    # Non-matching context
    non_matching_context = {
        FILTER_COMPONENT_ARCH: "aarch64",
        FILTER_COMPONENT_INST: "AWS",
        FILTER_COMPONENT_REPO: "eessi-2023.06"
    }
    assert action_filter.check_build_filters(non_matching_context) is False


def test_to_string():
    """Test converting filters to string"""
    filter_str = "arch:x86_64 inst:AWS repo:eessi-2023.06"
    action_filter = EESSIBotActionFilter(filter_str)
    # The to_string method returns the expanded component names
    expected_str = "architecture:x86_64 instance:AWS repository:eessi-2023.06"
    assert action_filter.to_string() == expected_str


def test_clear_all():
    """Test clearing all filters"""
    action_filter = EESSIBotActionFilter("arch:x86_64 inst:AWS")
    action_filter.clear_all()
    assert len(action_filter.action_filters) == 0


def test_architecture_filter_normalization():
    """Test that architecture filters are normalized (replacing all - with /)"""
    action_filter = EESSIBotActionFilter("arch:x86_64-intel-haswell")
    assert action_filter.get_filter_by_component(FILTER_COMPONENT_ARCH) == ['x86_64/intel/haswell']

    # Test matching with normalized value - only check architecture component
    context = {
        FILTER_COMPONENT_ARCH: "x86_64/intel/haswell"
    }
    assert action_filter.check_filters(context, [FILTER_COMPONENT_ARCH]) is True
