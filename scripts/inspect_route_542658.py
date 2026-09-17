import json
from sqlalchemy import select
from app.db.session import SessionLocal
from app.db.models import Route
from app.db.session import engine
engine.echo = False
with SessionLocal() as db:
    for r in db.scalars(select(Route).where(Route.codigo_ut == '542658')):
        coords = json.loads(r.suggested_geometry_json or r.routing_geometry_json or '[]')
        print('GEOMETRY start/end', coords[:2], coords[-2:])
        print(json.dumps({'id':r.id,'origin':r.origin_address,'km':r.routing_distance_km,'minutes':r.routing_duration_minutes,'geometry_points':len(json.loads(r.routing_geometry_json or '[]')),'suggested_points':len(json.loads(r.suggested_geometry_json or '[]')),'stops':[{'seq':s.sequence,'address':s.customer_address,'city':s.city,'province':s.province,'postal':s.postal_code,'lat':s.latitude,'lng':s.longitude} for s in r.stops]},ensure_ascii=False))
