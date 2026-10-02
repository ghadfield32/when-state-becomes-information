"""R6-L causal issuance (OW-R6L-CAUSAL-ISSUANCE-01).

opportunity -> inputs available by the cutoff -> causal state -> forecast or named abstention -> immutable journal;
evaluation happens later, in a separate module, against references matched by a declared policy.

The issuer never receives the future: it is handed `ObservationLog.available_at(cutoff)` and nothing else. The
future-deletion invariance test (same prefix, different futures -> byte-identical records) is the proof, not this
docstring.
"""
