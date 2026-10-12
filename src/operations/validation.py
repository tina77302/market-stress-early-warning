"""Provider integrity gates, deliberately without market-move cutoffs."""
import numpy as np
import pandas as pd


class ValidationFailure(ValueError):
    pass


class TransientProviderError(RuntimeError):
    pass


def validate_series(frame, column, *, positive=False, allow_missing=False, today=None):
    if not isinstance(frame, pd.DataFrame) or frame.empty or column not in frame.columns:
        raise ValidationFailure(f'{column}: empty response or missing expected column.')
    index = frame.index
    if not isinstance(index, pd.DatetimeIndex) or index.isna().any() or index.tz is not None:
        raise ValidationFailure(f'{column}: invalid observation date index.')
    if index.duplicated().any() or not index.is_monotonic_increasing:
        raise ValidationFailure(f'{column}: duplicate or unordered observation dates.')
    if (index != index.normalize()).any() or index.max() > pd.Timestamp(today or pd.Timestamp.now(tz='UTC').date()):
        raise ValidationFailure(f'{column}: intraday or future observation dates.')
    values = frame[column]
    if not pd.api.types.is_numeric_dtype(values) or (not allow_missing and values.isna().any()):
        raise ValidationFailure(f'{column}: nonnumeric or null observations.')
    observed = values.dropna()
    if observed.empty or not np.isfinite(observed.to_numpy(dtype=float)).all():
        raise ValidationFailure(f'{column}: missing or non-finite observations.')
    if positive and (observed <= 0).any():
        raise ValidationFailure(f'{column}: zero/negative price or volatility index.')
    return observed.index[-1].strftime('%Y-%m-%d')


def validate_features(frame, columns, common_date):
    if frame.empty or len(frame) < 1 or set(columns) - set(frame.columns):
        raise ValidationFailure('Missing inference features or insufficient feature history.')
    if frame.index.duplicated().any() or not frame.index.is_monotonic_increasing:
        raise ValidationFailure('Duplicate/unordered feature dates.')
    if frame.index[-1].strftime('%Y-%m-%d') != common_date:
        raise ValidationFailure('Latest features do not match the real common observation date.')
    if not np.isfinite(frame[columns].to_numpy(dtype=float)).all():
        raise ValidationFailure('Missing/non-finite inference features.')
