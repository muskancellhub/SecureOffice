from fastapi import HTTPException, Request, status


def get_current_user(request: Request) -> dict:
    user = getattr(request.state, 'user', None)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Unauthorized')
    return user
