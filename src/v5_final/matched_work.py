"""Matched-work performance entry point, deliberately locked before S5."""


class MatchedWorkNotAuthorized(RuntimeError):
    pass


def run_matched_work(*args: object, **kwargs: object) -> None:
    raise MatchedWorkNotAuthorized(
        "matched-work performance execution remains NOT_AUTHORIZED until an S5 freeze"
    )
