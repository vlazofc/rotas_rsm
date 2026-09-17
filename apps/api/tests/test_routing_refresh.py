from types import SimpleNamespace
from app.services import routing


def test_refresh_groups_same_address_and_discards_old_suggestion(monkeypatch):
    stops = [SimpleNamespace(id=i, sequence=i, customer_address='Rua X, 5226', city='São Paulo', province=None, postal_code=None, optimized_sequence=4-i) for i in (1, 2)]
    route = SimpleNamespace(id=1, stops=stops, origin_address='CD', source='automatico', vehicle_sent=None, vehicle_requested=None, suggested_geometry_json='old', routing_status='optimized')
    calls = []
    def request(*args):
        calls.append(args)
        return {'dest_coords':{'lat':-23.5,'lng':-46.6},'route':{'distance':1000,'time':60000,'points':{'coordinates':[[-46.7,-23.5],[-46.6,-23.5]]}}}
    monkeypatch.setattr(routing, '_request_route', request)
    monkeypatch.setattr(routing, 'routing_enabled', lambda _db: True)
    result = routing.route_through_stops(SimpleNamespace(flush=lambda:None), route)
    assert result['success']
    assert calls[0][2] == []
    assert stops[0].latitude == stops[1].latitude
    assert route.suggested_geometry_json is None
    assert [s.sequence for s in stops] == [1, 2]
    assert all(s.optimized_sequence is None for s in stops)


def test_address_removes_map_complement_without_changing_stop():
    stop = SimpleNamespace(customer_address="AV GENERAL FRANCISCO MORAZAN SOB LJ, 25, VL SONIA", city="SAO PAULO", province=None, postal_code=None, customer_name="Cliente")
    assert routing._address(stop) == "AV GENERAL FRANCISCO MORAZAN, 25, VL SONIA, SAO PAULO, Brasil"
    assert "SOB LJ" in stop.customer_address
