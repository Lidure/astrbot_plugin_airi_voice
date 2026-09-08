from web_api import VoiceManagementRoutes


class FakeWebApi:
    class Request:
        username = "admin"

    request = Request()

    class JsonResponse:
        def __call__(self, payload, status_code=200):
            return {"payload": payload, "status_code": status_code}

    json_response = JsonResponse()


def test_webui_error_payload_exposes_message_at_top_level():
    routes = VoiceManagementRoutes(object(), web_api=FakeWebApi())

    response = routes._error("duplicate_keyword", "关键词「TEST」与已有关键词「test」冲突。", 400)

    assert response["status_code"] == 400
    assert response["payload"] == {
        "error": "duplicate_keyword",
        "message": "关键词「TEST」与已有关键词「test」冲突。",
    }


def test_webui_catalog_error_keeps_chinese_detail():
    class FakeCatalogError(Exception):
        code = "duplicate_keyword"
        message = "关键词「TEST」与已有关键词「test」冲突。"

    routes = VoiceManagementRoutes(object(), web_api=FakeWebApi())
    response = routes._catalog_error(FakeCatalogError())

    assert response["status_code"] == 400
    assert response["payload"]["message"] == "关键词「TEST」与已有关键词「test」冲突。"
