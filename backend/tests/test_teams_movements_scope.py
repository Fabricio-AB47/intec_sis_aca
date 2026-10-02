from unittest.mock import patch

from app.routers import teams


def test_recordings_only_use_selected_team_storage():
    teams._RECORDINGS_CACHE.clear()
    requested_urls = []
    team_file = {
        "id": "file-a",
        "name": "Clase equipo A.mp4",
        "file": {"mimeType": "video/mp4"},
        "webUrl": "https://example.test/team-a/file-a",
        "parentReference": {"driveId": "drive-a", "path": "/drives/drive-a/root:/General2/Recordings"},
    }

    def graph_get_all(url, **_kwargs):
        requested_urls.append(url)
        if url.endswith("/teams/team-a/channels?$select=id,displayName,membershipType"):
            return {"value": [
                {"id": "channel-a", "displayName": "General"},
                {"id": "channel-b", "displayName": "General2"},
            ]}
        if "/groups/team-a/drives" in url:
            return {"value": [{"id": "drive-a", "name": "Documents"}]}
        if "/groups/team-a/owners" in url:
            return {"value": [{"id": "owner-a", "displayName": "Docente"}]}
        if "/groups/team-a/members" in url:
            return {"value": []}
        if "/drives/drive-a/items/folder-a:" in url:
            return {"value": []}
        if "/drives/drive-a/" in url:
            return {"value": [team_file]}
        if "/drives/owner-drive/" in url:
            return {"value": [{"id": "foreign", "name": "Otra materia.mp4", "file": {"mimeType": "video/mp4"}}]}
        raise AssertionError(f"Consulta Graph inesperada: {url}")

    def graph_get(url):
        requested_urls.append(url)
        if url.startswith("https://graph.microsoft.com/v1.0/teams/team-a/channels/channel-a/filesFolder"):
            return {"id": "folder-a", "name": "General", "parentReference": {"driveId": "drive-a", "path": "/drives/drive-a/root:"}}
        if url.startswith("https://graph.microsoft.com/v1.0/teams/team-a/channels/channel-b/filesFolder"):
            return {"id": "folder-b", "name": "General2", "parentReference": {"driveId": "drive-a", "path": "/drives/drive-a/root:"}}
        if url.startswith("https://graph.microsoft.com/v1.0/groups/team-a?"):
            return {"displayName": "Equipo A"}
        if "/users/owner-a/drive/root:/Recordings" in url:
            return {"id": "owner-folder", "parentReference": {"driveId": "owner-drive"}}
        raise AssertionError(f"Consulta Graph inesperada: {url}")

    with patch.object(teams, "graph_get_all", side_effect=graph_get_all), patch.object(teams, "graph_get", side_effect=graph_get):
        result = teams.teams_recordings("team-a", object(), force_refresh=True)

    assert result["count"] == 1
    assert result["value"][0]["id"] == "file-a"
    assert result["value"][0]["channelId"] == "channel-b"
    assert result["discovery"]["sourceCounts"]["OWNER_ONEDRIVE"] == 0
    assert not any("/users/owner-a/drive/" in url or "/drives/owner-drive/" in url for url in requested_urls)
    teams._RECORDINGS_CACHE.clear()


def test_messages_keep_replies_in_their_channel_without_duplicates():
    def load_roots(_team_id, channel):
        channel_id = channel["id"]
        root = {"id": "root-1", "body": {"content": f"Publicación {channel_id}"}}
        return channel_id, channel["displayName"], [root, root] if channel_id == "channel-a" else [root]

    def load_replies(_team_id, channel_id, _message_id):
        reply = {"id": "reply-1", "replyToId": "root-1", "body": {"content": f"Respuesta {channel_id}"}}
        return [reply, reply] if channel_id == "channel-a" else [reply]

    with (
        patch.object(teams, "graph_get_all", return_value={"value": [
            {"id": "channel-a", "displayName": "Canal A"},
            {"id": "channel-a", "displayName": "Canal A"},
            {"id": "channel-b", "displayName": "Canal B"},
        ]}),
        patch.object(teams, "_load_recent_channel_messages", side_effect=load_roots),
        patch.object(teams, "_load_channel_message_replies", side_effect=load_replies),
    ):
        result = teams.teams_messages("team-a", object())

    assert result["channel_count"] == 2
    assert result["root_message_count"] == 2
    assert result["reply_message_count"] == 2
    assert result["count"] == 4
    assert {(item["channelId"], item["bodyText"]) for item in result["value"] if item["isReply"]} == {
        ("channel-a", "Respuesta channel-a"),
        ("channel-b", "Respuesta channel-b"),
    }


def test_catalog_and_attendance_do_not_repeat_graph_items():
    with patch.object(teams, "graph_get_all", return_value={"value": [
        {"id": "TEAM-A", "displayName": "Aula A"},
        {"id": "team-a", "displayName": "Aula A duplicada"},
        {"id": "team-b", "displayName": "Aula B"},
    ]}):
        catalog = teams.teams_catalog(object())
    assert catalog["count"] == 2
    assert [team["displayName"] for team in catalog["value"]] == ["Aula A", "Aula B"]

    event = {"id": "event-a", "subject": "Clase A", "attendees": []}
    with patch.object(teams, "graph_get_all", return_value={"value": [event, event]}):
        attendance = teams.teams_attendance("team-a", object())
    assert attendance["count"] == 1
    assert attendance["value"][0]["topic"] == "Clase A"
