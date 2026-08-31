"""Matched-work performance entry point, locked pending method-native backends."""


class MatchedWorkNotAuthorized(RuntimeError):
    pass


def run_matched_work(*args: object, **kwargs: object) -> None:
    raise MatchedWorkNotAuthorized(
        "matched-work execution remains NOT_AUTHORIZED: S5 is frozen, but six "
        "method-native production backends and H2/H4 calibration are not closed"
    )
