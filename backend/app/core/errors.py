from fastapi import HTTPException, status


def not_found(what: str = "Resource") -> HTTPException:
    # Used for both missing and cross-tenant resources so ownership is not disclosed.
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{what} not found")


def conflict(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, detail)


def bad_request(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_400_BAD_REQUEST, detail)
