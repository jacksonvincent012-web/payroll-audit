"""Normalisation helpers for identity fields used in duplicate detection."""

import re

_NON_DIGITS = re.compile(r"\D")


def digits(value):
    """Keep only digits; empty input stays empty."""
    return _NON_DIGITS.sub("", value or "")


def normalise_bank(value):
    return digits(value)


def normalise_phone(value):
    number = digits(value)
    if number.startswith("254") and len(number) == 12:
        return number[3:]
    if number.startswith("0") and len(number) == 10:
        return number[1:]
    return number


def normalise_id(value):
    return digits(value)
