#!/usr/bin/env python3
"""Reproduce bounded invariants of the zero-mass Ellis wormhole toy geometry.

This is a deterministic software model in geometrized units (G = c = 1). A
PASS means that the declared analytic identities, predeclared predictions, and
an independent numerical proper-distance check agree. It is not evidence that
the required stress-energy exists or that a physical wormhole can be built.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any


INPUT_SCHEMA = "axm.matter-transfer.ellis-wormhole.input/v1"
RECEIPT_SCHEMA = "axm.matter-transfer.ellis-wormhole.receipt/v1"
MODEL_ID = "ellis-zero-mass-wormhole"
CLAIM_CEILING = "NO_PHYSICAL_MACROSCOPIC_MATTER_TRANSFER_MECHANISM_ESTABLISHED"
MAX_JSON_BYTES = 1_048_576
MAX_SAMPLES = 257
INPUT_KEYS = {
    "schema",
    "model",
    "units",
    "throat_radius",
    "stations",
    "samples_l",
    "integration_intervals",
    "tolerance",
    "predictions",
}
PREDICTION_KEYS = {
    "throat_areal_radius",
    "station_to_station_proper_distance",
    "right_station_areal_radius",
    "right_embedding_height",
    "throat_scaled_nec",
}


class ContractError(ValueError):
    """Raised when input or receipt bytes violate the experiment contract."""


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _number(value: Any, name: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError(f"{name} must be a finite number")
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise ContractError(f"{name} must be a finite number") from exc
    if not math.isfinite(result):
        raise ContractError(f"{name} must be a finite number")
    if positive and result <= 0:
        raise ContractError(f"{name} must be greater than zero")
    return result


def validate_input(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ContractError("input must be a JSON object")
    unknown = sorted(set(raw) - INPUT_KEYS)
    missing = sorted(INPUT_KEYS - set(raw))
    if unknown or missing:
        raise ContractError(f"input fields mismatch; missing={missing}, unknown={unknown}")
    if raw["schema"] != INPUT_SCHEMA:
        raise ContractError(f"schema must be {INPUT_SCHEMA}")
    if raw["model"] != MODEL_ID:
        raise ContractError(f"model must be {MODEL_ID}")
    if raw["units"] != "geometrized_G_equals_c_equals_1":
        raise ContractError("units must explicitly be geometrized_G_equals_c_equals_1")

    throat = _number(raw["throat_radius"], "throat_radius", positive=True)
    stations = raw["stations"]
    if not isinstance(stations, dict) or set(stations) != {"left_l", "right_l"}:
        raise ContractError("stations must contain exactly left_l and right_l")
    left = _number(stations["left_l"], "stations.left_l")
    right = _number(stations["right_l"], "stations.right_l")
    if not left < 0 < right:
        raise ContractError("stations must straddle the throat: left_l < 0 < right_l")

    samples = raw["samples_l"]
    if not isinstance(samples, list) or not 3 <= len(samples) <= MAX_SAMPLES:
        raise ContractError(f"samples_l must contain 3..{MAX_SAMPLES} values")
    normalized_samples = [_number(value, f"samples_l[{index}]") for index, value in enumerate(samples)]
    if normalized_samples != sorted(normalized_samples) or len(set(normalized_samples)) != len(normalized_samples):
        raise ContractError("samples_l must be strictly increasing")
    if 0.0 not in normalized_samples:
        raise ContractError("samples_l must include the throat coordinate 0")
    if normalized_samples[0] < left or normalized_samples[-1] > right:
        raise ContractError("samples_l must stay between the declared stations")

    intervals = raw["integration_intervals"]
    if isinstance(intervals, bool) or not isinstance(intervals, int):
        raise ContractError("integration_intervals must be an even integer")
    if intervals < 32 or intervals > 1_000_000 or intervals % 2:
        raise ContractError("integration_intervals must be even and between 32 and 1000000")
    tolerance = _number(raw["tolerance"], "tolerance", positive=True)
    if tolerance > 1e-6:
        raise ContractError("tolerance must not exceed 1e-6")

    predictions = raw["predictions"]
    if not isinstance(predictions, dict) or set(predictions) != PREDICTION_KEYS:
        raise ContractError("predictions must contain exactly the five declared prediction fields")
    normalized_predictions = {
        key: _number(predictions[key], f"predictions.{key}") for key in sorted(PREDICTION_KEYS)
    }

    return {
        "schema": INPUT_SCHEMA,
        "model": MODEL_ID,
        "units": raw["units"],
        "throat_radius": throat,
        "stations": {"left_l": left, "right_l": right},
        "samples_l": normalized_samples,
        "integration_intervals": intervals,
        "tolerance": tolerance,
        "predictions": normalized_predictions,
    }


def _rounded(value: float) -> float:
    return round(value, 12)


def _areal_radius(a: float, l_value: float) -> float:
    return math.hypot(l_value, a)


def _integrate_leg_in_areal_coordinates(a: float, l_magnitude: float, intervals: int) -> float:
    """Numerically integrate dl after r=a*cosh(u), avoiding the throat singularity."""
    endpoint = math.asinh(l_magnitude / a)
    step = endpoint / intervals
    weighted = 1.0 + math.cosh(endpoint)
    for index in range(1, intervals):
        weighted += (4.0 if index % 2 else 2.0) * math.cosh(index * step)
    return a * step * weighted / 3.0


def _sample(a: float, l_value: float) -> dict[str, float]:
    radius = _areal_radius(a, l_value)
    ratio = a / radius
    return {
        "l": _rounded(l_value),
        "areal_radius": _rounded(radius),
        "shape_b": _rounded(a * a / radius),
        "shape_ratio_b_over_r": _rounded(ratio * ratio),
        "d_areal_radius_d_l": _rounded(l_value / radius),
        "a_times_d2_areal_radius_d_l2": _rounded((a**3) / (radius**3)),
        "embedding_height_over_a": _rounded(math.asinh(l_value / a)),
        "scaled_energy_density_8pi_a2_rho": _rounded(-(ratio**4)),
        "scaled_radial_pressure_8pi_a2_pr": _rounded(-(ratio**4)),
        "scaled_radial_nec_8pi_a2_rho_plus_pr": _rounded(-2.0 * (ratio**4)),
    }


def _gate(name: str, passed: bool, measured: Any, expected: Any) -> dict[str, Any]:
    return {"name": name, "status": "PASS" if passed else "HOLD", "measured": measured, "expected": expected}


def run_experiment(raw: Any) -> dict[str, Any]:
    spec = validate_input(raw)
    a = spec["throat_radius"]
    left = spec["stations"]["left_l"]
    right = spec["stations"]["right_l"]
    tolerance = spec["tolerance"]
    samples = [_sample(a, l_value) for l_value in spec["samples_l"]]
    throat_sample = next(sample for sample in samples if sample["l"] == 0.0)

    analytic_distance = right - left
    numeric_distance = _integrate_leg_in_areal_coordinates(a, abs(left), spec["integration_intervals"])
    numeric_distance += _integrate_leg_in_areal_coordinates(a, right, spec["integration_intervals"])
    numeric_error = abs(numeric_distance - analytic_distance)
    right_radius = _areal_radius(a, right)
    right_embedding = a * math.asinh(right / a)

    measured_predictions = {
        "throat_areal_radius": a,
        "station_to_station_proper_distance": analytic_distance,
        "right_station_areal_radius": right_radius,
        "right_embedding_height": right_embedding,
        "throat_scaled_nec": throat_sample["scaled_radial_nec_8pi_a2_rho_plus_pr"],
    }
    prediction_errors = {
        key: _rounded(abs(measured_predictions[key] - expected))
        for key, expected in spec["predictions"].items()
    }
    predictions_pass = all(error <= tolerance for error in prediction_errors.values())
    gates = [
        _gate("throat_is_positive_minimum", a > 0 and throat_sample["a_times_d2_areal_radius_d_l2"] > 0, throat_sample["a_times_d2_areal_radius_d_l2"], "> 0"),
        _gate("morris_thorne_throat_identity", throat_sample["shape_b"] == _rounded(a), throat_sample["shape_b"], _rounded(a)),
        _gate("finite_constant_redshift_no_model_horizon", True, 1.0, "exp(2*Phi) = 1 everywhere"),
        _gate("independent_numeric_proper_distance", numeric_error <= tolerance, _rounded(numeric_error), f"<= {tolerance}"),
        _gate("radial_nec_is_violated_in_declared_gr_model", all(sample["scaled_radial_nec_8pi_a2_rho_plus_pr"] < 0 for sample in samples), [sample["scaled_radial_nec_8pi_a2_rho_plus_pr"] for sample in samples], "all < 0"),
        _gate("predeclared_predictions", predictions_pass, prediction_errors, f"every absolute error <= {tolerance}"),
    ]

    receipt: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "experiment": MODEL_ID,
        "status": "PASS" if all(gate["status"] == "PASS" for gate in gates) else "HOLD",
        "claim_ceiling": CLAIM_CEILING,
        "input_sha256": sha256(canonical_bytes(spec)),
        "model_contract": {
            "metric": "ds^2=-dt^2+dl^2+(l^2+a^2)dOmega^2",
            "morris_thorne_form": "Phi(r)=0; b(r)=a^2/r",
            "units": "geometrized_G_equals_c_equals_1",
            "source_lineage": [
                {
                    "title": "Ether flow through a drainhole: A particle model in general relativity",
                    "author": "H. G. Ellis",
                    "year": 1973,
                    "doi": "10.1063/1.1666161",
                    "relationship": "historical solution lineage",
                },
                {
                    "title": "Wormholes in spacetime and their use for interstellar travel: A tool for teaching general relativity",
                    "authors": ["M. S. Morris", "K. S. Thorne"],
                    "year": 1988,
                    "doi": "10.1119/1.15620",
                    "relationship": "metric, throat, flare-out, and stress-energy framework",
                },
            ],
        },
        "parameters": {
            "throat_radius": _rounded(a),
            "stations": {"left_l": _rounded(left), "right_l": _rounded(right)},
            "integration_intervals_per_leg": spec["integration_intervals"],
            "tolerance": tolerance,
        },
        "results": {
            "analytic_station_to_station_proper_distance": _rounded(analytic_distance),
            "numeric_station_to_station_proper_distance": _rounded(numeric_distance),
            "numeric_absolute_error": _rounded(numeric_error),
            "right_station_areal_radius": _rounded(right_radius),
            "right_embedding_height": _rounded(right_embedding),
            "samples": samples,
        },
        "gates": gates,
        "truth_boundary": {
            "computational_identity_reproduced": all(gate["status"] == "PASS" for gate in gates),
            "stress_energy_requirement_exposed": True,
            "stability_tested": False,
            "quantum_energy_inequalities_tested": False,
            "physical_source_or_actuator_known": False,
            "engineering_feasibility_established": False,
            "matter_transfer_demonstrated": False,
            "merge_or_canon_authority": False,
        },
    }
    receipt["receipt_sha256"] = sha256(canonical_bytes(receipt))
    return receipt


def verify_receipt(raw_input: Any, receipt: Any) -> dict[str, Any]:
    if not isinstance(receipt, dict) or receipt.get("schema") != RECEIPT_SCHEMA:
        raise ContractError("receipt schema mismatch")
    supplied_digest = receipt.get("receipt_sha256")
    if not isinstance(supplied_digest, str) or len(supplied_digest) != 64:
        raise ContractError("receipt_sha256 must be a lowercase SHA-256 hex string")
    without_digest = dict(receipt)
    del without_digest["receipt_sha256"]
    if sha256(canonical_bytes(without_digest)) != supplied_digest:
        raise ContractError("receipt digest mismatch")
    expected = run_experiment(raw_input)
    if receipt != expected:
        raise ContractError("receipt does not match deterministic re-execution")
    return {
        "schema": "axm.matter-transfer.ellis-wormhole.verification/v1",
        "status": "PASS",
        "receipt_sha256": supplied_digest,
        "claim_ceiling": CLAIM_CEILING,
        "merge_or_canon_authority": False,
    }


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContractError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _reject_nonstandard_constant(token: str) -> Any:
    raise ContractError(f"non-standard JSON constant: {token}")


def _read_json(path: Path) -> Any:
    try:
        with path.open("rb") as stream:
            data = stream.read(MAX_JSON_BYTES + 1)
    except OSError as exc:
        raise ContractError(f"cannot read JSON from {path}: {exc}") from exc
    if len(data) > MAX_JSON_BYTES:
        raise ContractError(f"JSON input {path} exceeds {MAX_JSON_BYTES}-byte limit")
    try:
        text = data.decode("utf-8")
        return json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_constant=_reject_nonstandard_constant,
        )
    except ContractError:
        raise
    except (UnicodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise ContractError(f"cannot read valid JSON from {path}: {exc}") from exc


def _write_json(path: Path | None, value: Any) -> None:
    data = canonical_bytes(value)
    if path is None:
        sys.stdout.buffer.write(data)
        return
    if path.exists():
        raise ContractError(f"refusing to overwrite existing output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run", help="run the declared reproduction")
    run_parser.add_argument("--input", type=Path, required=True)
    run_parser.add_argument("--output", type=Path)
    verify_parser = subparsers.add_parser("verify", help="re-execute and verify a receipt")
    verify_parser.add_argument("--input", type=Path, required=True)
    verify_parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        raw_input = _read_json(args.input)
        if args.command == "run":
            result = run_experiment(raw_input)
            _write_json(args.output, result)
            return 0 if result["status"] == "PASS" else 2
        result = verify_receipt(raw_input, _read_json(args.receipt))
        _write_json(None, result)
        return 0
    except ContractError as exc:
        print(f"HOLD: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
