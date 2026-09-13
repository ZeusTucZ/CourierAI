from math import radians, sin, cos, atan2, sqrt


def meters(a, b):
    """Great-circle lower bound, inputs (longitude, latitude)."""
    lon1, lat1, lon2, lat2 = map(radians, (*a, *b))
    h = sin((lat2-lat1)/2)**2 + cos(lat1)*cos(lat2)*sin((lon2-lon1)/2)**2
    return 6371009 * 2 * atan2(sqrt(min(1, h)), sqrt(max(0, 1-h)))


def point(graph, node):
    return [float(graph.nodes[node]["x"]), float(graph.nodes[node]["y"])]


def edge_coordinates(graph, edge):
    u, v, k = edge
    geometry = graph[u][v][k].get("geometry")
    coords = [list(p[:2]) for p in geometry.coords] if geometry is not None else [point(graph,u), point(graph,v)]
    if meters(coords[-1], point(graph,u)) < meters(coords[0], point(graph,u)):
        coords.reverse()
    return coords


def line(graph, edges, origin):
    coordinates = []
    for edge in edges:
        coords = edge_coordinates(graph, edge)
        coordinates.extend(coords[1:] if coordinates and coords[0] == coordinates[-1] else coords)
    if len(coordinates) < 2:
        coordinates = [point(graph,origin), point(graph,origin)]
    return {"type": "LineString", "coordinates": coordinates}
