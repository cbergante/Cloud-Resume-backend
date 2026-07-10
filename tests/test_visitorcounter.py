import pytest

API_URL = "https://fa-resumechallenge.azurewebsites.net/api/visitorcounter"


@pytest.fixture(scope="session")
def api_request_context(playwright):
    context = playwright.request.new_context()
    yield context
    context.dispose()


def test_visitor_counter_returns_success(api_request_context):
    response = api_request_context.get(API_URL)
    assert response.ok
    assert response.headers["content-type"] == "application/json"


def test_visitor_counter_increments(api_request_context):
    response1 = api_request_context.get(API_URL)
    count1 = response1.json()["count"]

    response2 = api_request_context.get(API_URL)
    count2 = response2.json()["count"]

    assert count2 == count1 + 1