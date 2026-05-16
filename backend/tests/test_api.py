from api.main import create_app


def test_app_routes_registered():
    app = create_app()
    paths = {route.path for route in app.routes}
    assert "/health" in paths
    assert "/api/v1/search" in paths
    assert "/api/v1/search/semantic" in paths
    assert "/api/v1/search/graphrag" in paths
