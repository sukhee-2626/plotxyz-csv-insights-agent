"""Original deterministic implementation for CSV Insights (plotxyz-csv-insights-agent)."""
from __future__ import annotations

import ast
import csv
import io
import json
import math
import os
import re
import statistics
import time
from collections import Counter, defaultdict, deque


class LogicError(ValueError):
    """Raised when supplied input cannot be processed."""


def _text(payload, key, min_len=1, max_len=20000):
    value = payload.get(key)
    if not isinstance(value, str):
        raise LogicError(f"'{key}' must be a string")
    value = value.strip()
    if len(value) < min_len:
        raise LogicError(f"'{key}' is required")
    if len(value) > max_len:
        raise LogicError(f"'{key}' exceeds {max_len} characters")
    return value


def _num(payload, key, default=None, lo=None, hi=None):
    value = payload.get(key, default)
    if value is None or value == "":
        if default is None:
            raise LogicError(f"'{key}' is required")
        return default
    if isinstance(value, bool):
        raise LogicError(f"'{key}' must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise LogicError(f"'{key}' must be numeric")
    if lo is not None and number < lo:
        raise LogicError(f"'{key}' must be at least {lo}")
    if hi is not None and number > hi:
        raise LogicError(f"'{key}' must be at most {hi}")
    return number


def _json(payload, key, expected=None, max_len=200000):
    raw = payload.get(key)
    if isinstance(raw, (dict, list)):
        data = raw
    elif isinstance(raw, str):
        if len(raw) > max_len:
            raise LogicError(f"'{key}' exceeds {max_len} characters")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LogicError(f"'{key}' is not valid JSON: {exc.msg} at line {exc.lineno}")
    else:
        raise LogicError(f"'{key}' must be JSON")
    if expected is not None and not isinstance(data, expected):
        name = expected.__name__ if hasattr(expected, "__name__") else str(expected)
        raise LogicError(f"'{key}' must be a JSON {name}")
    return data


def _csv(payload, key, max_rows=5000):
    text = _text(payload, key, max_len=2000000)
    try:
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise LogicError(f"'{key}' must include a header row")
        columns = [str(c).strip() for c in reader.fieldnames if c and str(c).strip()]
        if not columns:
            raise LogicError(f"'{key}' must include named columns")
        rows = []
        for index, raw in enumerate(reader):
            if index >= max_rows:
                raise LogicError(f"'{key}' exceeds {max_rows} rows")
            rows.append({col: (raw.get(col) or "").strip() for col in columns})
    except csv.Error as exc:
        raise LogicError(f"'{key}' is not valid CSV: {exc}")
    if not rows:
        raise LogicError(f"'{key}' must include at least one data row")
    return columns, rows


STOPWORDS = {'will', 'they', 'was', 'your', 'than', 'that', 'on', 'be', 'then', 'do', 'our', 'with', 'he', 'is', 'about', 'had', 'were', 'as', 'may', 'we', 'their', 'are', 'did', 'at', 'she', 'a', 'by', 'the', 'if', 'might', 'it', 'into', 'have', 'from', 'should', 'not', 'over', 'can', 'for', 'and', 'an', 'you', 'does', 'to', 'this', 'could', 'would', 'under', 'of', 'no', 'its', 'in', 'i', 'or', 'has'}


def _tokens(text):
    return [w for w in re.findall(r"[a-z0-9][a-z0-9_+-]{1,}", text.lower()) if w not in STOPWORDS]


def _sentences(text):
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [p.strip(" -•\t") for p in parts if len(p.strip()) > 2]


def provider_status():
    """Report which optional model providers are configured (never exposes secrets)."""
    ollama = bool(os.getenv("OLLAMA_BASE_URL"))
    openai = bool(os.getenv("OPENAI_BASE_URL") and os.getenv("OPENAI_MODEL"))
    return {"ollama_compatible": ollama, "openai_compatible": openai}


def _llm(messages, temperature=0.2):
    """Call an explicitly configured OpenAI-compatible endpoint; return None when unavailable."""
    base = os.getenv("OPENAI_BASE_URL", "").rstrip("/")
    model = os.getenv("OPENAI_MODEL", "")
    if not base or not model:
        ollama = os.getenv("OLLAMA_BASE_URL", "").rstrip("/")
        if not ollama:
            return None
        base = f"{ollama}/v1"
        model = os.getenv("OLLAMA_MODEL", "")
    if not model:
        return None
    try:
        import httpx

        headers = {"Content-Type": "application/json"}
        key = os.getenv("OPENAI_API_KEY")
        if key:
            headers["Authorization"] = f"Bearer {key}"
        with httpx.Client(timeout=20) as client:
            response = client.post(
                f"{base}/chat/completions",
                headers=headers,
                json={"model": model, "messages": messages, "temperature": temperature},
            )
            response.raise_for_status()
            return str(response.json()["choices"][0]["message"]["content"]).strip()
    except Exception:
        return None


def _result(summary, result, warnings=None):
    return {"summary": summary, "result": result, "warnings": warnings or []}


def agent_csv_insights(payload):
    columns, rows = _csv(payload, "csv")
    numeric = {}
    for column in columns:
        values = []
        for row in rows:
            if row[column] == "":
                continue
            try:
                values.append(float(row[column]))
            except ValueError:
                pass
        if len(values) >= max(2, len(rows) * 0.5):
            numeric[column] = values
    stats_rows = []
    for column in columns:
        values = numeric.get(column)
        if values:
            stats_rows.append([column, "number", len(values), round(statistics.fmean(values), 3), round(statistics.median(values), 3), round(min(values), 3), round(max(values), 3)])
        else:
            counts = Counter(row[column] for row in rows if row[column])
            top = counts.most_common(1)[0] if counts else ("", 0)
            stats_rows.append([column, "text", len([r for r in rows if r[column]]), "", "", "", f"top: {top[0]} ({top[1]})"])
    correlations = []
    names = list(numeric)
    for i, left in enumerate(names):
        for right in names[i + 1:]:
            try:
                value = statistics.correlation(numeric[left], numeric[right])
                correlations.append([left, right, round(value, 3)])
            except statistics.StatisticsError:
                pass
    chart = None
    if numeric:
        first = names[0]
        values = numeric[first]
        low, high = min(values), max(values)
        bins = [0] * 8
        width = (high - low) / 8 if high > low else 1
        for value in values:
            bins[min(7, int((value - low) / width))] += 1
        chart = {"labels": [f"{low + i * width:.1f}" for i in range(8)], "values": bins}
    markdown = f"## Dataset summary\n\n- Rows: **{len(rows)}**\n- Columns: **{len(columns)}**\n- Numeric columns: **{len(numeric)}**\n\n" + "\n".join(f"- `{column}`: {len(values)} numeric values" for column, values in numeric.items())
    return _result(
        f"Profiled {len(rows)} rows across {len(columns)} columns; {len(numeric)} numeric column(s).",
        {
            "metrics": {"rows": len(rows), "columns": len(columns), "numeric_columns": len(numeric), "correlations": len(correlations)},
            "table": {"columns": ["Column", "Kind", "Count", "Mean", "Median", "Min", "Max / Top"], "rows": stats_rows},
            "chart": chart,
            "markdown": markdown,
        },
        ["Summary statistics describe the supplied sample only; they are not population estimates."],
    )


run = agent_csv_insights
