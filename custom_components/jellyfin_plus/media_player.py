"""Support for the Jellyfin media player."""

from datetime import timedelta
import logging
import time
from typing import Any, override

from homeassistant.components.media_player import (
    ATTR_MEDIA_ENQUEUE,
    BrowseMedia,
    MediaPlayerEnqueue,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
    SearchMedia,
    SearchMediaQuery,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util.dt import parse_datetime, utcnow

from .browse_media import (
    FENSTER_PRAEFIX,
    build_item_response,
    build_root_response,
    fetch_item,
    search_items,
    zerlege_wahl,
)
from .client_wrapper import get_artwork_url
from .const import CONTENT_TYPE_MAP, LOGGER, MAX_IMAGE_WIDTH
from .coordinator import JellyfinConfigEntry, JellyfinDataUpdateCoordinator
from .entity import JellyfinClientEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: JellyfinConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Jellyfin media_player from a config entry."""
    coordinator = entry.runtime_data

    @callback
    def handle_coordinator_update() -> None:
        """Add media player per session."""
        entities: list[MediaPlayerEntity] = []
        for session_id in coordinator.data:
            if session_id not in coordinator.session_ids:
                entity: MediaPlayerEntity = JellyfinMediaPlayer(coordinator, session_id)
                LOGGER.debug("Creating media player for session: %s", session_id)
                coordinator.session_ids.add(session_id)
                entities.append(entity)
        async_add_entities(entities)

    handle_coordinator_update()

    entry.async_on_unload(coordinator.async_add_listener(handle_coordinator_update))


class JellyfinMediaPlayer(JellyfinClientEntity, MediaPlayerEntity):
    """Represents a Jellyfin Player device."""

    def __init__(
        self,
        coordinator: JellyfinDataUpdateCoordinator,
        session_id: str,
    ) -> None:
        """Initialize the Jellyfin Media Player entity."""
        super().__init__(coordinator, session_id)
        self._attr_unique_id = f"{coordinator.server_id}-{session_id}"

        self.now_playing: dict[str, Any] | None = self.session_data.get(
            "NowPlayingItem"
        )
        self.play_state: dict[str, Any] | None = self.session_data.get("PlayState")

        self._update_from_session_data()

    @callback
    @override
    def _handle_coordinator_update(self) -> None:
        if self.available:
            self.now_playing = self.session_data.get("NowPlayingItem")
            self.play_state = self.session_data.get("PlayState")
        else:
            self.now_playing = None
            self.play_state = None

        self._update_from_session_data()
        super()._handle_coordinator_update()

    @callback
    def _update_from_session_data(self) -> None:
        """Process session data to update entity properties."""
        state = None
        media_content_type = None
        media_content_id = None
        media_title = None
        media_series_title = None
        media_season = None
        media_episode = None
        media_album_name = None
        media_album_artist = None
        media_artist = None
        media_track = None
        media_duration = None
        media_position = None
        media_position_updated = None
        volume_muted = False
        volume_level = None

        if self.available:
            state = MediaPlayerState.IDLE
            media_position_updated = (
                parse_datetime(self.session_data["LastPlaybackCheckIn"])
                if self.now_playing
                else None
            )
            if media_position_updated is not None:
                takt = self.coordinator.update_interval or timedelta(seconds=10)
                frueheste = utcnow() - takt
                if media_position_updated < frueheste:
                    media_position_updated = frueheste

        if self.now_playing is not None:
            state = MediaPlayerState.PLAYING
            media_content_type = CONTENT_TYPE_MAP.get(self.now_playing["Type"], None)
            media_content_id = self.now_playing["Id"]
            media_title = self.now_playing["Name"]

            if "RunTimeTicks" in self.now_playing:
                media_duration = int(self.now_playing["RunTimeTicks"] / 10000000)

            if media_content_type == MediaType.EPISODE:
                media_content_type = MediaType.TVSHOW
                media_series_title = self.now_playing.get("SeriesName")
                media_season = self.now_playing.get("ParentIndexNumber")
                media_episode = self.now_playing.get("IndexNumber")
            elif media_content_type == MediaType.MUSIC:
                media_album_name = self.now_playing.get("Album")
                media_album_artist = self.now_playing.get("AlbumArtist")
                media_track = self.now_playing.get("IndexNumber")
                if media_artists := self.now_playing.get("Artists"):
                    media_artist = str(media_artists[0])

        if self.play_state is not None:
            if self.play_state.get("IsPaused"):
                state = MediaPlayerState.PAUSED

            media_position = (
                int(self.play_state["PositionTicks"] / 10000000)
                if "PositionTicks" in self.play_state
                else None
            )
            volume_muted = bool(self.play_state.get("IsMuted", False))
            volume_level = (
                float(self.play_state["VolumeLevel"] / 100)
                if "VolumeLevel" in self.play_state
                else None
            )

        self._attr_state = state
        self._attr_is_volume_muted = volume_muted
        # Only update volume_level if the API provides it,
        # otherwise preserve current value
        if volume_level is not None:
            self._attr_volume_level = volume_level
        self._attr_media_content_type = media_content_type
        self._attr_media_content_id = media_content_id
        self._attr_media_title = media_title
        self._attr_media_series_title = media_series_title
        self._attr_media_season = media_season
        self._attr_media_episode = media_episode
        self._attr_media_album_name = media_album_name
        self._attr_media_album_artist = media_album_artist
        self._attr_media_artist = media_artist
        self._attr_media_track = media_track
        self._attr_media_duration = media_duration
        media_position, media_position_updated = self._sprung_halten(
            media_position, media_position_updated
        )
        self._attr_media_position = media_position
        self._attr_media_position_updated_at = media_position_updated

    @property
    @override
    def media_image_url(self) -> str | None:
        """Image url of current playing media."""
        # We always need the now playing item.
        # If there is none, there's also no url
        if self.now_playing is None:
            return None

        return get_artwork_url(
            self.coordinator.api_client, self.now_playing, MAX_IMAGE_WIDTH
        )

    @property
    @override
    def supported_features(self) -> MediaPlayerEntityFeature:
        """Flag media player features that are supported."""
        commands: list[str] = self.capabilities.get("SupportedCommands", [])
        _LOGGER.debug(
            "Supported commands for device %s, client %s, %s",
            self.device_name,
            self.client_name,
            commands,
        )
        features = MediaPlayerEntityFeature(0)

        if "PlayMediaSource" in commands or self.capabilities.get(
            "SupportsMediaControl", False
        ):
            features |= (
                MediaPlayerEntityFeature.BROWSE_MEDIA
                | MediaPlayerEntityFeature.PLAY_MEDIA
                | MediaPlayerEntityFeature.PAUSE
                | MediaPlayerEntityFeature.PLAY
                | MediaPlayerEntityFeature.STOP
                | MediaPlayerEntityFeature.SEEK
                | MediaPlayerEntityFeature.SEARCH_MEDIA
                | MediaPlayerEntityFeature.MEDIA_ENQUEUE
            )

            if "Mute" in commands and "Unmute" in commands:
                features |= MediaPlayerEntityFeature.VOLUME_MUTE

            if "VolumeSet" in commands or "SetVolume" in commands:
                features |= MediaPlayerEntityFeature.VOLUME_SET

        return features

    # Wie lange die eigene Absicht gegen den Serverstand gilt: zwei
    # Durchlaeufe des Koordinators plus Luft fuer den Fernseher, der ein
    # paar Sekunden braucht, bis er die neue Stelle zurueckmeldet.
    SPRUNG_GNADE = 15.0

    # Klassenweit vorbelegt, damit __init__ unveraendert aus der Vorlage
    # bleiben kann - je Entitaet wird beim ersten Sprung ueberschrieben.
    _sprung_ziel: float | None = None
    _sprung_zeit: Any = None

    def _sprung_halten(self, position: int | None, gemeldet: Any) -> tuple:
        """Den nachhinkenden Serverstand nach einem eigenen Sprung ueberbruecken.

        Sobald der Server in der Naehe der erwarteten Stelle ankommt, hat er
        den Sprung vollzogen - ab da gilt wieder er, denn er weiss auch von
        Spruengen, die nicht von hier kamen (Fernbedienung, Vorspann).
        """
        if self._sprung_ziel is None or self._sprung_zeit is None:
            return position, gemeldet

        alter = (utcnow() - self._sprung_zeit).total_seconds()
        erwartet = self._sprung_ziel + alter
        angekommen = position is not None and abs(position - erwartet) <= 8

        if alter > self.SPRUNG_GNADE or self.now_playing is None or angekommen:
            self._sprung_ziel = None
            self._sprung_zeit = None
            return position, gemeldet

        return int(self._sprung_ziel), self._sprung_zeit

    @override
    def media_seek(self, position: float) -> None:
        """Send seek command.

        Der Koordinator fragt den Server nur alle zehn Sekunden. Bis dahin
        stuende in media_position die alte Stelle, und wer zweimal kurz
        hintereinander springt, rechnet zweimal von derselben Zahl los.
        Darum wird die Absicht hier sofort eingetragen.
        """
        self.coordinator.api_client.jellyfin.remote_seek(
            self.session_id, int(position * 10000000)
        )
        self._sprung_ziel = float(position)
        self._sprung_zeit = utcnow()
        self._attr_media_position = int(position)
        self._attr_media_position_updated_at = self._sprung_zeit
        self.schedule_update_ha_state()

    @override
    def media_pause(self) -> None:
        """Send pause command."""
        self.coordinator.api_client.jellyfin.remote_pause(self.session_id)
        self._attr_state = MediaPlayerState.PAUSED
        self.schedule_update_ha_state()

    @override
    def media_play(self) -> None:
        """Send play command."""
        self.coordinator.api_client.jellyfin.remote_unpause(self.session_id)
        self._attr_state = MediaPlayerState.PLAYING
        self.schedule_update_ha_state()

    def media_play_pause(self) -> None:
        """Send the PlayPause command to the session."""
        self.coordinator.api_client.jellyfin.remote_playpause(self.session_id)

    @override
    def media_stop(self) -> None:
        """Send stop command."""
        self.coordinator.api_client.jellyfin.remote_stop(self.session_id)
        self._attr_state = MediaPlayerState.IDLE
        self.schedule_update_ha_state()

    @override
    def play_media(
        self, media_type: MediaType | str, media_id: str, **kwargs: Any
    ) -> None:
        """Play a piece of media."""
        command = "PlayNow"
        enqueue = kwargs.get(ATTR_MEDIA_ENQUEUE)
        if enqueue == MediaPlayerEnqueue.NEXT:
            command = "PlayNext"
        elif enqueue == MediaPlayerEnqueue.ADD:
            command = "PlayLast"
        # Eine angetippte Folge spielt nicht, sie fragt erst nach den Spuren.
        if media_id.startswith(FENSTER_PRAEFIX):
            self._auswahl_melden(media_id[len(FENSTER_PRAEFIX):])
            return

        # Unsere Kennung traegt die gewaehlten Spuren mit sich.
        wahl = zerlege_wahl(media_id)
        if wahl is not None:
            item_id, ton, unter = wahl
            params: dict[str, Any] = {}
            if ton >= 0:
                params["audioStreamIndex"] = ton
            if unter >= 0:
                params["subtitleStreamIndex"] = unter
            elif unter == -1:
                params["subtitleStreamIndex"] = -1
            # Dort weitermachen, wo aufgehoert wurde. Ohne diese Angabe
            # beginnt der Server bei null - und der naechste Stopp schreibt
            # die Null als neuen Stand zurueck. Genau daran sind am
            # 2026-08-24 vier Folgen Fortschritt verlorengegangen.
            # Unter fuenf Minuten Laufzeit nicht fortsetzen - das entspricht
            # MinResumeDurationSeconds.
            _it = fetch_item(self.coordinator.api_client, item_id) or {}
            _ab = int((_it.get("UserData") or {}).get("PlaybackPositionTicks") or 0)
            if _ab > 0 and (_it.get("RunTimeTicks") or 0) >= 300 * 10000000:
                params["startPositionTicks"] = _ab
            self.coordinator.api_client.jellyfin.remote_play_media(
                self.session_id, [item_id], command, params=params
            )
            if ton >= 0 or unter >= -1:
                self._spuren_nachsetzen(item_id, ton, unter)
            return

        _it = fetch_item(self.coordinator.api_client, media_id) or {}
        _ab = int((_it.get("UserData") or {}).get("PlaybackPositionTicks") or 0)
        _p = ({"startPositionTicks": _ab}
              if _ab > 0 and (_it.get("RunTimeTicks") or 0) >= 300 * 10000000
              else None)
        self.coordinator.api_client.jellyfin.remote_play_media(
            self.session_id, [media_id], command, params=_p
        )

    def _auswahl_melden(self, item_id: str) -> None:
        """Ereignis mit den Spuren des Titels feuern, statt abzuspielen.

        Der Medienbrowser kann nur Kacheln - Klapplisten und einen Knopf
        unten rechts kann er nicht. Also uebernimmt HA ab hier: die
        Automation in packages/jellyfin_wahlfenster.yaml fuellt zwei
        Auswahlfelder und laesst browser_mod das Fenster zeigen.

        Die Integration kennt browser_mod bewusst nicht. Faellt es weg,
        laeuft das Ereignis ins Leere - kaputt geht nichts.
        """
        item = fetch_item(self.coordinator.api_client, item_id)
        if item is None:
            LOGGER.warning("Auswahlfenster: %s nicht gefunden", item_id)
            return

        quellen = item.get("MediaSources") or []
        streams = (
            quellen[0].get("MediaStreams", [])
            if quellen
            else item.get("MediaStreams", [])
        )

        def liste(art: str) -> list[str]:
            # Die Spurnummer gehoert vorne hin: zwei Spuren duerfen
            # denselben Anzeigenamen haben, und ein Auswahlfeld lehnt
            # doppelte Eintraege ab.
            return [
                f"{s.get('Index')} - {s.get('DisplayTitle') or s.get('Language') or 'Spur'}"
                for s in streams
                if s.get("Type") == art
            ]

        titel = item["Name"]
        if item.get("Type") == "Episode" and item.get("IndexNumber") is not None:
            titel = f"{item['IndexNumber']}. {titel}"
        if item.get("SeriesName"):
            titel = f"{item['SeriesName']} - {titel}"

        daten = {
            "item_id": item_id,
            "titel": titel,
            "ton": liste("Audio"),
            "untertitel": liste("Subtitle"),
            "entity_id": self.entity_id,
        }
        # Aus dem Executor heraus ist async_fire nicht direkt erlaubt.
        self.hass.loop.call_soon_threadsafe(
            self.hass.bus.async_fire, "jellyfin_plus_auswahl", daten
        )

    def _spuren_nachsetzen(self, item_id: str, ton: int, unter: int) -> None:
        """Die gewaehlten Spuren nach dem Start noch einmal setzen.

        Der Tizen-Client des Fernsehers wertet audioStreamIndex und
        subtitleStreamIndex im Abspielbefehl NICHT aus - er nimmt immer
        seine eigene Standardspur. Eingebettet wie extern, am 2026-08-20 an
        drei Faellen nachgemessen. Ein SetSubtitleStreamIndex NACH dem Start
        greift dagegen binnen Sekunden.

        Darum wird die Wahl zweimal gesagt: einmal im Abspielbefehl, falls
        ein anderer Client sie doch auswertet und dann von der ersten
        Sekunde an richtig laeuft, und einmal danach als Befehl.

        Laeuft im Executor - play_media ist keine Koroutine -, deshalb darf
        hier gewartet werden. Ohne das Warten kaeme der Befehl an, bevor
        ueberhaupt etwas laeuft, und verpuffte.
        """
        api = self.coordinator.api_client.jellyfin

        def sende(befehl: str, index: int) -> None:
            if hasattr(api, "command"):
                api.command(self.session_id, befehl, json={"Index": str(index)})
            else:  # aeltere Fassung der Bibliothek
                api._post(
                    "Sessions/%s/Command" % self.session_id,
                    json={"Name": befehl, "Arguments": {"Index": str(index)}},
                )

        ende = time.monotonic() + 30
        while time.monotonic() < ende:
            time.sleep(1.5)
            try:
                sitzungen = api.sessions() or []
            except Exception:  # noqa: BLE001 - ein Aussetzer darf nichts brechen
                continue
            for s in sitzungen:
                if s.get("Id") != self.session_id:
                    continue
                if (s.get("NowPlayingItem") or {}).get("Id") != item_id:
                    continue
                zustand = s.get("PlayState") or {}
                # NUR schicken, was wirklich abweicht. Ein Tonwechsel laesst
                # den Client den Datenstrom neu aushandeln, und dabei faellt
                # die gerade gesetzte Untertitelspur wieder heraus - ein
                # ueberfluessiger Tonbefehl macht also die Untertitelwahl
                # kaputt. Am 2026-08-20 genau daran aufgelaufen: die einzige
                # Tonspur lief laengst, der Befehl war sinnlos, und der
                # Untertitel stand danach auf "aus".
                geschickt = False
                if ton >= 0 and zustand.get("AudioStreamIndex") != ton:
                    sende("SetAudioStreamIndex", ton)
                    geschickt = True
                if unter >= -1 and zustand.get("SubtitleStreamIndex") != unter:
                    if geschickt:
                        # Dem Client Zeit lassen, den Ton umzustellen -
                        # sonst geht der Untertitelbefehl im Neuaufbau unter.
                        time.sleep(3)
                    sende("SetSubtitleStreamIndex", unter)
                return
        LOGGER.debug(
            "Spurwahl verfiel: %s lief nach 30 s nicht in Sitzung %s",
            item_id,
            self.session_id,
        )

    def play_media_shuffle(self, media_content_id: str) -> None:
        """Play a piece of media on shuffle."""
        self.coordinator.api_client.jellyfin.remote_play_media(
            self.session_id, [media_content_id], "PlayShuffle"
        )

    @override
    def set_volume_level(self, volume: float) -> None:
        """Set volume level, range 0..1."""
        self.coordinator.api_client.jellyfin.remote_set_volume(
            self.session_id, int(volume * 100)
        )
        self._attr_volume_level = volume
        self.schedule_update_ha_state()

    @override
    def mute_volume(self, mute: bool) -> None:
        """Mute the volume."""
        if mute:
            self.coordinator.api_client.jellyfin.remote_mute(self.session_id)
        else:
            self.coordinator.api_client.jellyfin.remote_unmute(self.session_id)
        self._attr_is_volume_muted = mute
        self.schedule_update_ha_state()

    @override
    async def async_browse_media(
        self,
        media_content_type: MediaType | str | None = None,
        media_content_id: str | None = None,
    ) -> BrowseMedia:
        """Return a BrowseMedia instance.

        The BrowseMedia instance will be used by the
        "media_player/browse_media" websocket command.

        """
        if media_content_id is None or media_content_id == "media-source://jellyfin":
            return await build_root_response(
                self.hass, self.coordinator.api_client, self.coordinator.user_id
            )

        return await build_item_response(
            self.hass,
            self.coordinator.api_client,
            self.coordinator.user_id,
            media_content_id,
        )

    @override
    async def async_search_media(
        self,
        query: SearchMediaQuery,
    ) -> SearchMedia:
        """Search the media player."""
        result = await search_items(
            self.hass, self.coordinator.api_client, self.coordinator.user_id, query
        )
        return SearchMedia(result=result)
