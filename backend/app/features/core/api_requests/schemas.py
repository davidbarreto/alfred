from pydantic import BaseModel


class ClientUsage(BaseModel):
    client: str
    requests: int
    errors: int
    avg_latency_ms: float


class RouteUsage(BaseModel):
    client: str
    method: str
    route: str
    requests: int
    errors: int


class ApiUsageSummary(BaseModel):
    days: int
    total: int
    by_client: list[ClientUsage]
    top_routes: list[RouteUsage]
