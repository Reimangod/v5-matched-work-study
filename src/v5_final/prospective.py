"""Prospective evaluation entry point, deliberately locked before S5."""


class ProspectiveNotAuthorized(RuntimeError):
    pass


def run_prospective(*args: object, **kwargs: object) -> None:
    raise ProspectiveNotAuthorized(
        "prospective molecular evaluation remains NOT_AUTHORIZED until its frozen stage"
    )
