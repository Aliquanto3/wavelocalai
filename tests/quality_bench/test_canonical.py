"""JSON canonique et empreintes (AD-4)."""

import hashlib
import json
import math
import re
import unicodedata

import pytest

from scripts.quality_bench.common.canonical import (
    canonical_bytes,
    nfc,
    pretty_bytes,
    sha256_bytes,
    sha256_hex,
    utc_now,
)


def test_canonical_bytes_sorted_compact_utf8():
    data = canonical_bytes({"b": 1, "a": ["é", {"z": None, "y": True}]})
    assert data == '{"a":["é",{"y":true,"z":null}],"b":1}'.encode()


def test_canonical_bytes_independent_of_key_order():
    assert canonical_bytes({"a": 1, "b": 2}) == canonical_bytes({"b": 2, "a": 1})


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_non_finite_floats_refused(value):
    with pytest.raises(ValueError):
        canonical_bytes({"x": value})
    with pytest.raises(ValueError):
        sha256_hex([value])
    with pytest.raises(ValueError):
        pretty_bytes({"x": value})


def test_sha256_hex_is_lowercase_sha256_of_canonical_form():
    obj = {"question": "Quelle est la capitale ?", "n": 3}
    expected = hashlib.sha256(canonical_bytes(obj)).hexdigest()
    assert sha256_hex(obj) == expected
    assert re.fullmatch(r"[0-9a-f]{64}", sha256_hex(obj))
    assert sha256_bytes(b"abc") == hashlib.sha256(b"abc").hexdigest()


def test_nfc_normalizes_decomposed_accents():
    decomposed = "été"
    assert nfc(decomposed) == "été"
    assert unicodedata.is_normalized("NFC", nfc(decomposed))
    assert sha256_hex(nfc(decomposed)) == sha256_hex("été")


def test_utc_now_iso_second_z():
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", utc_now())


def test_pretty_bytes_round_trips():
    obj = {"b": [1, 2], "a": "é"}
    assert json.loads(pretty_bytes(obj).decode("utf-8")) == obj
    assert pretty_bytes(obj).endswith(b"\n")
