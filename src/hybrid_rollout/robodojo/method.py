"""
Explicit evaluation method identity; never infer it from an auth provider.

Thanks for the contribution: https://github.com/anonymous-report-421/GPT-as-Policy
"""
import os

METHODS = ('pi05_plus_gpt', 'gpt_only')


def evaluation_method(value=None):
    value = value or os.environ.get('ROLLOUT_EVALUATION_METHOD', METHODS[0])
    if value not in METHODS:
        raise ValueError('Unknown evaluation method; no implicit fallback')
    return value
