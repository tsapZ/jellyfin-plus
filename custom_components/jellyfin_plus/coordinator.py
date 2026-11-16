"""Data update coordinator for the Jellyfin integration."""

from datetime import timedelta
from typing import Any, override

from jellyfin_apiclient_python import JellyfinClient

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import CONF_CLIENT_DEVICE_ID, DOMAIN, LOGGER, USER_APP_NAME

# Aus jeder Sitzung des Benutzers wurde bisher ein Spieler - auch aus denen,
# die gar nichts abspielen. Zwei Merkmale trennen das sauber:
#
#   SupportsRemoteControl  Seerr und der API-Schluessel der eigenen Sensoren
#                          melden hier False. Sie sind keine Abspielgeraete,
#                          sondern Programme, die den Server befragen.
#   EIGENE_CLIENTS         HA selbst. Die eigene laufende Sitzung faellt
#                          schon ueber die Geraetekennung weg, die Sitzung
#                          der alten offiziellen Integration aber nicht -
#                          die heisst "Home Assistant" und blieb uebrig.
EIGENE_CLIENTS = (USER_APP_NAME, "Home Assistant", "HA")

# Die Verengung auf bestimmte Clients (bei Fabian: nur der Fernseher, sonst
# wird auch jedes Handy und jeder Browser ein Spieler, der danach dauerhaft
# "nicht verfuegbar" herumsteht) ist seit 2026-11-16 eine Option der
# Integration statt einer festen Liste - siehe _async_update_data.

type JellyfinConfigEntry = ConfigEntry[JellyfinDataUpdateCoordinator]


class JellyfinDataUpdateCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Data update coordinator for the Jellyfin integration."""

    config_entry: JellyfinConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: JellyfinConfigEntry,
        api_client: JellyfinClient,
        system_info: dict[str, Any],
        user_id: str,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass=hass,
            logger=LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=10),
        )
        self.api_client = api_client
        self.server_id: str = system_info["Id"]
        self.server_name: str = system_info["Name"]
        self.server_version: str | None = system_info.get("Version")
        self.client_device_id: str = config_entry.data[CONF_CLIENT_DEVICE_ID]
        self.user_id: str = user_id

        self.session_ids: set[str] = set()
        self.remote_session_ids: set[str] = set()
        self.device_ids: set[str] = set()

    @override
    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Get the latest data from Jellyfin."""
        sessions = await self.hass.async_add_executor_job(
            self.api_client.jellyfin.sessions
        )

        if sessions is None:
            return {}

        # Welche Clients Spieler werden, steht in den Optionen der Integration
        # (Einstellungen -> Jellyfin Plus -> Konfigurieren), Komma-getrennt.
        # Leer = alles, was sich fernsteuern laesst.
        nur_clients = {
            c.strip()
            for c in str(self.config_entry.options.get("clients", "")).split(",")
            if c.strip()
        }
        sessions_by_id: dict[str, dict[str, Any]] = {
            session["Id"]: session
            for session in sessions
            if session["DeviceId"] != self.client_device_id
            and session["Client"] not in EIGENE_CLIENTS
            and session.get("SupportsRemoteControl")
            and (not nur_clients or session["Client"] in nur_clients)
            # Tools like Jellystat report sessions as the server itself
            and session["DeviceId"] != self.server_id
        }

        self.device_ids = {session["DeviceId"] for session in sessions_by_id.values()}

        return sessions_by_id
