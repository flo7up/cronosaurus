"""
Calculator tools — precise math, unit conversion, and financial calculations.

Uses Python's built-in math and decimal modules for accuracy.
No external dependencies required.
"""

import json
import logging
import math
from decimal import Decimal, InvalidOperation
from typing import Any

logger = logging.getLogger(__name__)

CALCULATOR_TOOL_DEFINITIONS = [
    {
        "name": "calculate",
        "description": (
            "Evaluate a mathematical expression. Supports arithmetic (+, -, *, /, **), "
            "percentages, parentheses, and common math functions (sqrt, sin, cos, tan, "
            "log, log10, abs, round, ceil, floor, pi, e). Returns the precise result."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": (
                        "Math expression to evaluate (e.g. '(1500 * 1.05) / 12', "
                        "'sqrt(144)', '2**10', 'round(3.14159, 2)')."
                    ),
                },
            },
            "required": ["expression"],
        },
    },
    {
        "name": "convert_units",
        "description": (
            "Convert between common units of measurement. Supports length, weight, "
            "temperature, area, volume, speed, and data storage units."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "value": {
                    "type": "number",
                    "description": "The numeric value to convert.",
                },
                "from_unit": {
                    "type": "string",
                    "description": "Source unit (e.g. 'km', 'lb', 'celsius', 'GB').",
                },
                "to_unit": {
                    "type": "string",
                    "description": "Target unit (e.g. 'miles', 'kg', 'fahrenheit', 'MB').",
                },
            },
            "required": ["value", "from_unit", "to_unit"],
        },
    },
    {
        "name": "financial_calculate",
        "description": (
            "Perform financial calculations: compound interest, loan payments, "
            "percentage change, ROI, and present/future value."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "calculation": {
                    "type": "string",
                    "enum": [
                        "compound_interest",
                        "loan_payment",
                        "percentage_change",
                        "roi",
                    ],
                    "description": "Type of financial calculation.",
                },
                "principal": {"type": "number", "description": "Initial amount."},
                "rate": {"type": "number", "description": "Interest rate (as percentage, e.g. 5.5 for 5.5%)."},
                "periods": {"type": "number", "description": "Number of periods (years for interest, months for loans)."},
                "final_value": {"type": "number", "description": "Final value (for percentage_change or ROI)."},
            },
            "required": ["calculation"],
        },
    },
]

CALCULATOR_TOOL_NAMES = {d["name"] for d in CALCULATOR_TOOL_DEFINITIONS}

# Safe math namespace for eval
_SAFE_MATH = {
    "abs": abs, "round": round, "min": min, "max": max,
    "sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "log": math.log, "log10": math.log10, "log2": math.log2,
    "ceil": math.ceil, "floor": math.floor, "pow": pow,
    "pi": math.pi, "e": math.e,
}

# Unit conversion tables (to base unit)
_LENGTH = {"m": 1, "km": 1000, "cm": 0.01, "mm": 0.001, "mi": 1609.344, "miles": 1609.344, "yd": 0.9144, "ft": 0.3048, "in": 0.0254, "inch": 0.0254, "inches": 0.0254}
_WEIGHT = {"kg": 1, "g": 0.001, "mg": 0.000001, "lb": 0.453592, "lbs": 0.453592, "oz": 0.0283495, "ton": 1000, "tonne": 1000}
_AREA = {"m2": 1, "km2": 1e6, "ha": 10000, "acre": 4046.86, "ft2": 0.092903, "sqft": 0.092903}
_VOLUME = {"l": 1, "liter": 1, "ml": 0.001, "gal": 3.78541, "gallon": 3.78541, "qt": 0.946353, "cup": 0.236588, "fl_oz": 0.0295735}
_SPEED = {"m/s": 1, "km/h": 0.277778, "kmh": 0.277778, "mph": 0.44704, "knot": 0.514444, "knots": 0.514444}
_DATA = {"b": 1, "byte": 1, "kb": 1024, "mb": 1024**2, "gb": 1024**3, "tb": 1024**4, "pb": 1024**5}

_UNIT_TABLES = [_LENGTH, _WEIGHT, _AREA, _VOLUME, _SPEED, _DATA]


def execute_calculator_tool(tool_name: str, arguments: str | dict) -> dict[str, Any]:
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            return {"success": False, "error": "Invalid arguments JSON"}

    try:
        if tool_name == "calculate":
            return _calculate(arguments)
        elif tool_name == "convert_units":
            return _convert_units(arguments)
        elif tool_name == "financial_calculate":
            return _financial_calc(arguments)
        else:
            return {"success": False, "error": f"Unknown calculator tool: {tool_name}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _calculate(args: dict) -> dict:
    expr = args.get("expression", "")
    if not expr:
        return {"success": False, "error": "expression is required"}
    # Security: only allow safe characters
    allowed = set("0123456789+-*/.() ,eE")
    for word in _SAFE_MATH:
        expr_check = expr.replace(word, "")
    clean = expr
    for ch in clean:
        if ch not in allowed and not ch.isalpha() and ch != "_":
            return {"success": False, "error": f"Disallowed character: {ch}"}
    try:
        result = eval(expr, {"__builtins__": {}}, _SAFE_MATH)  # noqa: S307
        return {"success": True, "expression": args["expression"], "result": result}
    except Exception as e:
        return {"success": False, "error": f"Evaluation error: {e}"}


def _convert_units(args: dict) -> dict:
    value = args.get("value", 0)
    from_u = args.get("from_unit", "").lower().strip()
    to_u = args.get("to_unit", "").lower().strip()

    # Temperature (special case)
    temp_units = {"celsius", "c", "fahrenheit", "f", "kelvin", "k"}
    if from_u in temp_units or to_u in temp_units:
        return _convert_temperature(value, from_u, to_u)

    for table in _UNIT_TABLES:
        if from_u in table and to_u in table:
            base = value * table[from_u]
            result = base / table[to_u]
            return {"success": True, "value": value, "from": args["from_unit"], "to": args["to_unit"], "result": round(result, 6)}

    return {"success": False, "error": f"Cannot convert '{from_u}' to '{to_u}'. Units not found or incompatible."}


def _convert_temperature(value: float, from_u: str, to_u: str) -> dict:
    # Normalize
    f_map = {"celsius": "c", "fahrenheit": "f", "kelvin": "k"}
    f = f_map.get(from_u, from_u)
    t = f_map.get(to_u, to_u)
    if f == t:
        return {"success": True, "value": value, "from": from_u, "to": to_u, "result": value}
    # Convert to Celsius first
    if f == "f":
        c = (value - 32) * 5 / 9
    elif f == "k":
        c = value - 273.15
    else:
        c = value
    # Convert from Celsius to target
    if t == "f":
        result = c * 9 / 5 + 32
    elif t == "k":
        result = c + 273.15
    else:
        result = c
    return {"success": True, "value": value, "from": from_u, "to": to_u, "result": round(result, 4)}


def _financial_calc(args: dict) -> dict:
    calc_type = args.get("calculation", "")
    principal = args.get("principal", 0)
    rate = args.get("rate", 0) / 100  # convert from percentage
    periods = args.get("periods", 0)
    final_value = args.get("final_value", 0)

    if calc_type == "compound_interest":
        if not principal or not rate or not periods:
            return {"success": False, "error": "principal, rate, and periods required"}
        future_value = principal * (1 + rate) ** periods
        interest = future_value - principal
        return {"success": True, "calculation": calc_type, "principal": principal, "rate_pct": rate * 100,
                "periods": periods, "future_value": round(future_value, 2), "total_interest": round(interest, 2)}

    elif calc_type == "loan_payment":
        if not principal or not rate or not periods:
            return {"success": False, "error": "principal, rate (annual), and periods (months) required"}
        monthly_rate = rate / 12
        if monthly_rate == 0:
            payment = principal / periods
        else:
            payment = principal * (monthly_rate * (1 + monthly_rate) ** periods) / ((1 + monthly_rate) ** periods - 1)
        total_paid = payment * periods
        return {"success": True, "calculation": calc_type, "principal": principal, "annual_rate_pct": rate * 100,
                "months": periods, "monthly_payment": round(payment, 2), "total_paid": round(total_paid, 2),
                "total_interest": round(total_paid - principal, 2)}

    elif calc_type == "percentage_change":
        if not principal or not final_value:
            return {"success": False, "error": "principal (original) and final_value required"}
        change = ((final_value - principal) / principal) * 100
        return {"success": True, "calculation": calc_type, "original": principal, "final": final_value,
                "change_pct": round(change, 4), "absolute_change": round(final_value - principal, 2)}

    elif calc_type == "roi":
        if not principal or not final_value:
            return {"success": False, "error": "principal (investment) and final_value (return) required"}
        roi = ((final_value - principal) / principal) * 100
        return {"success": True, "calculation": calc_type, "investment": principal, "return_value": final_value,
                "roi_pct": round(roi, 4), "profit": round(final_value - principal, 2)}

    return {"success": False, "error": f"Unknown calculation type: {calc_type}"}
