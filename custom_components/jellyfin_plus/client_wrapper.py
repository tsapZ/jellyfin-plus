"""Utility methods for initializing a Jellyfin client."""

import socket
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit

from jellyfin_apiclient_python import Jellyfin, JellyfinClient
from jellyfin_apiclient_python.api import API
from jellyfin_apiclient_python.connection_manager import (
    CONNECTION_STATE,
    ConnectionManager,
)

from homeassistant import exceptions
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .const import CLIENT_VERSION, ITEM_KEY_IMAGE_TAGS, USER_AGENT, USER_APP_NAME


async def validate_input(
    hass: HomeAssistant, user_input: dict[str, Any], client: JellyfinClient
) -> tuple[str, dict[str, Any]]:
    """Validate that the provided url and credentials can be used to connect."""
    url = user_input[CONF_URL]
    username = user_input[CONF_USERNAME]
    password = user_input[CONF_PASSWORD]

    user_id, connect_result = await hass.async_add_executor_job(
        _connect, client, url, username, password
    )

    return (user_id, connect_result)


def create_client(device_id: str, device_name: str | None = None) -> JellyfinClient:
    """Create a new Jellyfin client."""
    if device_name is None:
        device_name = socket.gethostname()

    jellyfin = Jellyfin()

    client = jellyfin.get_client()
    client.config.app(USER_APP_NAME, CLIENT_VERSION, device_name, device_id)
    client.config.http(USER_AGENT)

    return client


def _connect(
    client: JellyfinClient, url: str, username: str, password: str
) -> tuple[str, dict[str, Any]]:
    """Connect to the Jellyfin server and assert that the user can login."""
    client.config.data["auth.ssl"] = url.startswith("https")

    connect_result = _connect_to_address(client.auth, url)

    _login(client.auth, url, username, password)

    return (_get_user_id(client.jellyfin), connect_result)


def _connect_to_address(
    connection_manager: ConnectionManager, url: str
) -> dict[str, Any]:
    """Connect to the Jellyfin server."""
    result: dict[str, Any] = connection_manager.connect_to_address(url)
    if CONNECTION_STATE(result["State"]) != CONNECTION_STATE.ServerSignIn:
        raise CannotConnect

    return result


def _login(
    connection_manager: ConnectionManager,
    url: str,
    username: str,
    password: str,
) -> None:
    """Assert that the user can log in to the Jellyfin server."""
    response = connection_manager.login(url, username, password)

    if "AccessToken" not in response:
        raise InvalidAuth


def _get_user_id(api: API) -> str:
    """Set the unique userid from a Jellyfin server."""
    settings: dict[str, Any] = api.get_user_settings()
    userid: str = settings["Id"]
    return userid


def get_artwork_url(
    client: JellyfinClient, item: dict[str, Any], max_width: int = 600
) -> str | None:
    """Find a suitable thumbnail for an item."""
    artwork_id: str | None = None
    artwork_type: str | None = None
    parent_backdrop_id: str | None = item.get("ParentBackdropItemId")

    if "AlbumPrimaryImageTag" in item:
        # jellyfin_apiclient_python doesn't support passing
        # a specific tag to `.artwork`, so we don't use the
        # actual value of AlbumPrimaryImageTag. However, its
        # mere presence tells us that the album does have
        # primary artwork, and the resulting URL will pull the
        # primary album art even if the tag is not specified.
        artwork_type = "Primary"
        artwork_id = item["AlbumId"]
    elif "Backdrop" in item[ITEM_KEY_IMAGE_TAGS]:
        artwork_type = "Backdrop"
        artwork_id = item["Id"]
    elif parent_backdrop_id:
        artwork_type = "Backdrop"
        artwork_id = parent_backdrop_id
    elif "Primary" in item[ITEM_KEY_IMAGE_TAGS]:
        artwork_type = "Primary"
        artwork_id = item["Id"]
    else:
        return None

    return bild_url(
        str(client.jellyfin.artwork(artwork_id, artwork_type, max_width)),
        max_width,
        _bild_tag(item, artwork_id, artwork_type),
    )


# Vorschaubilder im Medienbrowser (jellyfin_plus): 360 px webp statt 600 px jpg.
VORSCHAU_BREITE = 360


def _bild_tag(item: dict[str, Any], artwork_id: str, artwork_type: str) -> str | None:
    """Tag des gewaehlten Bildes - damit wird die Adresse dauerhaft cachebar."""
    if artwork_type == "Primary":
        if artwork_id == item.get("Id"):
            return (item.get(ITEM_KEY_IMAGE_TAGS) or {}).get("Primary")
        return item.get("AlbumPrimaryImageTag")
    if artwork_id == item.get("Id"):
        return (item.get("BackdropImageTags") or [None])[0]
    return (item.get("ParentBackdropImageTags") or [None])[0]


def bild_url(url: str, max_width: int, tag: str | None) -> str:
    """Bildadresse neu aufbauen: klein, webp, mit tag, ohne api_key."""
    teile = urlsplit(url)
    abfrage: dict[str, Any] = {"maxWidth": max_width, "quality": 80, "format": "webp"}
    if tag:
        abfrage["tag"] = tag
    return urlunsplit((teile.scheme, teile.netloc, teile.path, urlencode(abfrage), ""))


class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate the server is unreachable."""


class InvalidAuth(exceptions.HomeAssistantError):
    """Error to indicate the credentials are invalid."""
