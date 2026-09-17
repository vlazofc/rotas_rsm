from sqlalchemy import select
from app.db.session import SessionLocal, engine
from app.db.models import Route
engine.echo = False
with SessionLocal() as db:
    route = db.get(Route, 370)
    print({"id": route.id if route else None, "code": route.codigo_ut if route else None,
           "status": route.status if route else None, "routing_status": route.routing_status if route else None,
           "routing_error": route.routing_error if route else None,
           "distance_km": route.routing_distance_km if route else None})
    if route:
        for stop in route.stops:
            if stop.latitude is None or stop.longitude is None:
                print("PENDING", stop.sequence, stop.customer_name, stop.customer_address, stop.city)
