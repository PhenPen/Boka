"""Application wiring: CORS, the JSON error shape, and route registration."""

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .errors import ApiError

app = FastAPI(title="Clinic booking API", version="1.0.0")

# The page is served from the same origin in production. Open CORS keeps a
# locally opened copy of the page working too; it does not weaken the key check.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"ok": True}


@app.exception_handler(ApiError)
async def handle_api_error(_: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(
        {"error": exc.message}, status_code=exc.status, headers=exc.headers
    )


@app.exception_handler(StarletteHTTPException)
async def handle_http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    return JSONResponse({"error": str(exc.detail)}, status_code=exc.status_code)


@app.exception_handler(Exception)
async def handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse({"error": "internal server error"}, status_code=500)


# Vercel routes every non-static request into this one function, and the path
# the function receives depends on the rewrite. Registering the same router
# under each candidate prefix means any of them resolves.
for _prefix in ("", "/api", "/api/index"):
    app.include_router(router, prefix=_prefix, include_in_schema=_prefix == "")
