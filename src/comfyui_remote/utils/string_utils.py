"""Utils functions for Comfy Remote CLI/GUI."""

import logging

from pyparsing import (
    Literal,
    Optional,
    QuotedString,
    Word,
    alphas,
    alphanums,
    ZeroOrMore,
    Group,
    Dict,
    dictOf,
    ParseException,
    White,
    pyparsing_common as ppc,
)

from pyparsing import (
    Literal,
    Optional,
    ParseException,
    QuotedString,
    Word,
    alphanums,
    dictOf,
)

logger = logging.getLogger(__name__)


def convert_string_to_dict(input_string):
    """Convert a string representation of a dictionary into a Python dict.

    This function uses a pyparsing grammar to parse strings into dictionaries,
    handling a variety of formatting options and syntax styles.
    It is designed to be forgiving and flexible, making it easier for users to
    submit parameters from the command line.

    The parser supports:
    - Optional braces: both with/without {}, []
    - Different delimiters: :, =, or whitespace
    - Different separators: comma or semicolon
    - Quoted and unquoted keys/values

    Args:
        input_string (str): String representation of a dict

    Returns:
        dict or None: Dictionary parsed from the input string, or None if parsing fails

    Examples:
        >>> convert_string_to_dict('{"key1":"value1", "key2":"value2"}')
        {'key1': 'value1', 'key2': 'value2'}
        >>> convert_string_to_dict("key1:value1, key2: value2")
        {'key1': 'value1', 'key2': 'value2'}
        >>> convert_string_to_dict("key1=3.14 key2='hello world'")
        {'key1': 3.14, 'key2': 'hello world'}
        >>> convert_string_to_dict("invalid input")
        None
    """
    if not input_string or not isinstance(input_string, str):
        return {}

    left_brace = Literal("{").suppress() | Literal("[").suppress()
    right_brace = Literal("}").suppress() | Literal("]").suppress()

    quoted_string = QuotedString('"', escChar="\\", unquoteResults=True) | QuotedString(
        "'", escChar="\\", unquoteResults=True
    )
    bare_identifier = Word(alphas + "_", alphanums + "_")

    string_value = quoted_string | bare_identifier
    numeric_value = ppc.number()
    null_value = Literal("None") | Literal("null") | Literal("NULL")
    null_value.setParseAction(lambda: [""])

    value = null_value | numeric_value | string_value
    key = string_value

    colon_or_equals = (Literal(":") | Literal("=")).suppress()
    whitespace = White(min=1).leaveWhitespace().suppress()
    delimiter = colon_or_equals | whitespace

    key_value_pair = Group(key + delimiter + value)
    pair_separator = (Literal(",") | Literal(";")).suppress()
    pairs = key_value_pair + ZeroOrMore(pair_separator + key_value_pair)

    grammar = Optional(left_brace) + Optional(Dict(pairs)) + Optional(right_brace)

    try:
        result = grammar.parseString(input_string, parseAll=True).asDict()
        return result
    except ParseException as parse_error:
        logger.warning('Failed to parse string to dictionary: "%s"', input_string)
        logger.debug("Error: %s", parse_error, exc_info=True)
        return None
