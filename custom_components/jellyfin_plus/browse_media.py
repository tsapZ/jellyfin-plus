"""Support for media browsing."""

import asyncio
from functools import partial
from typing import Any

from jellyfin_apiclient_python import JellyfinClient

from homeassistant.components.media_player import (
    BrowseError,
    BrowseMedia,
    MediaClass,
    MediaType,
    SearchMediaQuery,
)
from homeassistant.core import HomeAssistant

from .client_wrapper import get_artwork_url
from .const import (
    CONTENT_TYPE_MAP,
    MEDIA_CLASS_MAP,
    MEDIA_TYPE_NONE,
    SUPPORTED_COLLECTION_TYPES,
)

CONTAINER_TYPES_SPECIFIC_MEDIA_CLASS: dict[str, str] = {
    MediaType.MUSIC: MediaClass.MUSIC,
    MediaType.SEASON: MediaClass.SEASON,
    MediaType.TVSHOW: MediaClass.TV_SHOW,
    "boxset": MediaClass.DIRECTORY,
    "collection": MediaClass.DIRECTORY,
    "library": MediaClass.DIRECTORY,
}

PLAYABLE_MEDIA_TYPES = [
    MediaType.EPISODE,
    MediaType.MOVIE,
    MediaType.MUSIC,
    MediaType.SEASON,
    MediaType.TVSHOW,
]


async def item_payload(
    hass: HomeAssistant,
    client: JellyfinClient,
    user_id: str,
    item: dict[str, Any],
) -> BrowseMedia:
    """Create response payload for a single media item."""
    title = _beschriftung(item)

    thumbnail = get_artwork_url(client, item, 600)

    media_content_id = item["Id"]
    media_content_type = CONTENT_TYPE_MAP.get(item["Type"], MEDIA_TYPE_NONE)

    # Der Kern des Ablegers: eine Folge oder ein Film startet NICHT sofort.
    # Sie traegt stattdessen die Fenster-Kennung; play_media erkennt sie und
    # loest das Auswahlfenster aus, statt abzuspielen.
    waehlbar = item.get("Type") in ("Episode", "Movie")
    if waehlbar:
        media_content_id = f"{FENSTER_PRAEFIX}{media_content_id}"

    return BrowseMedia(
        title=title,
        media_content_id=media_content_id,
        media_content_type=media_content_type,
        media_class=MEDIA_CLASS_MAP.get(item["Type"], MediaClass.DIRECTORY),
        can_play=bool(
            (media_content_type in PLAYABLE_MEDIA_TYPES or waehlbar)
            and media_content_id
        ),
        can_expand=bool(item.get("IsFolder")),
        children_media_class=None,
        thumbnail=thumbnail,
    )


async def build_root_response(
    hass: HomeAssistant, client: JellyfinClient, user_id: str
) -> BrowseMedia:
    """Create response payload for root folder."""
    folders = await hass.async_add_executor_job(client.jellyfin.get_media_folders)

    children = [
        await item_payload(hass, client, user_id, folder)
        for folder in folders["Items"]
        if folder.get("CollectionType") in SUPPORTED_COLLECTION_TYPES
    ]

    # Ganz nach vorn, weil man in neun von zehn Faellen genau dort landet.
    for platz, (kennung, beschriftung) in enumerate(
        ((LISTE_WEITER, "Weiterschauen"), (LISTE_NAECHSTE, "Naechste Folge"))
    ):
        children.insert(
            platz,
            BrowseMedia(
                title=beschriftung,
                media_content_id=kennung,
                media_content_type="directory",
                media_class=MediaClass.DIRECTORY,
                can_play=False,
                can_expand=True,
            ),
        )

    return BrowseMedia(
        media_content_id="",
        media_content_type="root",
        media_class=MediaClass.DIRECTORY,
        children_media_class=MediaClass.DIRECTORY,
        title="Jellyfin",
        can_play=False,
        can_expand=True,
        children=children,
    )


# --------------------------------------------------------------------------
# Spurenauswahl
#
# Der Praefix trennt unsere synthetischen Kennungen von echten Jellyfin-Ids.
# In ihm steckt alles, was der Abspielbefehl braucht - dadurch ist kein
# Zwischenspeicher noetig, der irgendwann nicht mehr zur Anzeige passt.
# --------------------------------------------------------------------------

WAHL_PRAEFIX = "jfp|"

# Tippt man eine Folge an, kommt diese Kennung bei play_media an. Sie spielt
# nichts, sondern loest das Auswahlfenster aus (siehe media_player.py).
FENSTER_PRAEFIX = "jfpdlg|"

# Drei Bedeutungen, nicht zwei: eine Spurnummer, "keine Spur" (-1) und
# "nicht anfassen" (-2). Ohne die dritte laesst sich "Abspielen (Standard)"
# nicht von "ohne Untertitel" unterscheiden.
UNVERAENDERT = -2


def zerlege_wahl(media_content_id: str) -> tuple[str, int, int] | None:
    """jfp|<ItemId>|<Ton>|<Untertitel> -> (ItemId, Ton, Untertitel)."""
    if not media_content_id.startswith(WAHL_PRAEFIX):
        return None
    teile = media_content_id[len(WAHL_PRAEFIX):].split("|")
    if len(teile) != 3:
        return None
    return teile[0], int(teile[1]), int(teile[2])


def _spuren(item: dict[str, Any]) -> tuple[list[dict], list[dict]]:
    """Ton- und Untertitelspuren eines Titels."""
    quellen = item.get("MediaSources") or []
    streams = quellen[0].get("MediaStreams", []) if quellen else item.get("MediaStreams", [])
    ton = [s for s in streams if s.get("Type") == "Audio"]
    unter = [s for s in streams if s.get("Type") == "Subtitle"]
    return ton, unter


def _kurz(stream: dict[str, Any]) -> str:
    """Sprechender, aber kurzer Name einer Spur."""
    name = stream.get("DisplayTitle") or stream.get("Language") or "Spur"
    return str(name)[:60]


ANSICHT_PRAEFIX = "jfpw|"     # Anpassen-Ansicht
TON_PRAEFIX = "jfpa|"         # Liste der Tonspuren
UNTER_PRAEFIX = "jfps|"       # Liste der Untertitelspuren


def _zerlege_ansicht(kennung: str, praefix: str) -> tuple[str, int, int] | None:
    """<praefix><ItemId>|<Ton>|<Untertitel> -> (ItemId, Ton, Untertitel)."""
    if not kennung.startswith(praefix):
        return None
    teile = kennung[len(praefix):].split("|")
    if len(teile) != 3:
        return None
    return teile[0], int(teile[1]), int(teile[2])


def _name_ton(ton: list[dict], index: int) -> str:
    if index == UNVERAENDERT:
        return "Standard"
    for s in ton:
        if s.get("Index") == index:
            return _kurz(s)
    return "Standard"


def _name_unter(unter: list[dict], index: int) -> str:
    if index == UNVERAENDERT:
        return "Standard"
    if index == -1:
        return "Aus"
    for s in unter:
        if s.get("Index") == index:
            return _kurz(s)
    return "Standard"


def _titel(item: dict[str, Any]) -> str:
    name = item["Name"]
    if item.get("Type") == "Episode" and item.get("IndexNumber") is not None:
        return f"{item['IndexNumber']}. {name}"
    return str(name)


def _beschriftung(item: dict[str, Any], *, mit_staffel: bool = False) -> str:
    """Die Zeile, wie sie im Medienbrowser steht: Nummer, Stand, Name.

    MIT_STAFFEL gilt nur fuer Weiterschauen und Naechste Folge. Dort liegen
    Folgen aus allen Serien nebeneinander, und eine blosse "2." beantwortet
    die Frage nicht, welche Folge das ist: "Rick and Morty - 2. Intelligenz
    braucht keine Ferien" ist in Wahrheit S9E02, und "One-Punch Man - 5."
    stammt aus den Specials. Innerhalb einer Staffel waere die
    Staffelnummer dagegen in jeder Zeile dieselbe und nur Ballast.

    Der Gesehen-Zustand steht VORN, weil die Zeile hinten abgeschnitten
    wird, sobald der Serienname davorsteht.
    """
    name = str(item["Name"])
    art = item.get("Type")
    nummer = item.get("IndexNumber")

    if art == "Episode" and nummer is not None:
        staffel = item.get("ParentIndexNumber")
        if not mit_staffel:
            name = "%d. %s" % (nummer, name)
        elif staffel is None:
            name = "E%02d %s" % (nummer, name)
        else:
            name = "S%dE%02d %s" % (staffel, nummer, name)

    # Was der Server ueber den Fortschritt weiss, als Vorzeichen im Titel.
    # BrowseMedia hat kein Feld dafuer - der Titel ist die einzige Stelle,
    # an der es in der Oberflaeche ankommt.
    ud = item.get("UserData") or {}
    if art in ("Episode", "Movie"):
        if ud.get("Played"):
            name = "\u2713 " + name
        elif (ud.get("PlaybackPositionTicks") or 0) > 0:
            name = "\u25b6 %d%% " % round(ud.get("PlayedPercentage") or 0) + name
    else:
        offen = ud.get("UnplayedItemCount")
        if offen == 0:
            name = "\u2713 " + name
        elif offen and art in ("Series", "Season"):
            name = "%s  (%d offen)" % (name, offen)
    return name


def _art(item: dict[str, Any]) -> MediaType:
    return MediaType.EPISODE if item.get("Type") == "Episode" else MediaType.MOVIE


async def build_track_response(
    hass: HomeAssistant,
    client: JellyfinClient,
    user_id: str,
    kennung: str,
) -> BrowseMedia:
    """Anpassen-Ansicht: Ton, Untertitel, Abspielen.

    Nimmt entweder eine nackte ItemId (dann gelten die Voreinstellungen des
    Servers) oder eine unserer drei Kennungen.
    """
    wahl = (
        _zerlege_ansicht(kennung, ANSICHT_PRAEFIX)
        or _zerlege_ansicht(kennung, TON_PRAEFIX)
        or _zerlege_ansicht(kennung, UNTER_PRAEFIX)
    )
    if wahl is None:
        item_id, gew_ton, gew_unter = kennung, UNVERAENDERT, UNVERAENDERT
    else:
        item_id, gew_ton, gew_unter = wahl

    item = await hass.async_add_executor_job(fetch_item, client, item_id)
    if item is None:
        raise BrowseError(f"Media not found: {item_id}")

    ton, unter = _spuren(item)
    bild = get_artwork_url(client, item, 600)

    def knoten(
        beschriftung: str, id_: str, *, abspielbar: bool = False
    ) -> BrowseMedia:
        return BrowseMedia(
            title=beschriftung,
            media_content_id=id_,
            media_content_type=_art(item),
            media_class=MediaClass.VIDEO,
            can_play=abspielbar,
            can_expand=not abspielbar,
            thumbnail=bild,
        )

    # --- die Unterlisten ---------------------------------------------------
    # Jeder Eintrag fuehrt ZURUECK in die Anpassen-Ansicht, nur mit dem
    # geaenderten Wert. Dadurch ist es ein Auswahlfeld, obwohl es technisch
    # eine Liste ist.
    if kennung.startswith(TON_PRAEFIX):
        kinder = [
            knoten(
                ("* " if gew_ton == UNVERAENDERT else "") + "Standard",
                f"{ANSICHT_PRAEFIX}{item_id}|{UNVERAENDERT}|{gew_unter}",
            )
        ]
        for s in ton:
            i = s.get("Index", -1)
            kinder.append(
                knoten(
                    ("* " if gew_ton == i else "") + _kurz(s),
                    f"{ANSICHT_PRAEFIX}{item_id}|{i}|{gew_unter}",
                )
            )
        return BrowseMedia(
            media_class=MediaClass.DIRECTORY,
            media_content_id=kennung,
            media_content_type=_art(item),
            title=f"Tonspur - {_titel(item)}",
            can_play=False,
            can_expand=True,
            children=kinder,
            children_media_class=MediaClass.VIDEO,
            thumbnail=bild,
        )

    if kennung.startswith(UNTER_PRAEFIX):
        kinder = [
            knoten(
                ("* " if gew_unter == UNVERAENDERT else "") + "Standard",
                f"{ANSICHT_PRAEFIX}{item_id}|{gew_ton}|{UNVERAENDERT}",
            ),
            knoten(
                ("* " if gew_unter == -1 else "") + "Aus",
                f"{ANSICHT_PRAEFIX}{item_id}|{gew_ton}|-1",
            ),
        ]
        for s in unter:
            i = s.get("Index", -1)
            kinder.append(
                knoten(
                    ("* " if gew_unter == i else "") + _kurz(s),
                    f"{ANSICHT_PRAEFIX}{item_id}|{gew_ton}|{i}",
                )
            )
        return BrowseMedia(
            media_class=MediaClass.DIRECTORY,
            media_content_id=kennung,
            media_content_type=_art(item),
            title=f"Untertitel - {_titel(item)}",
            can_play=False,
            can_expand=True,
            children=kinder,
            children_media_class=MediaClass.VIDEO,
            thumbnail=bild,
        )

    # --- die Anpassen-Ansicht selbst ---------------------------------------
    kinder = [
        knoten(
            f"Ton: {_name_ton(ton, gew_ton)}",
            f"{TON_PRAEFIX}{item_id}|{gew_ton}|{gew_unter}",
        ),
        knoten(
            f"Untertitel: {_name_unter(unter, gew_unter)}",
            f"{UNTER_PRAEFIX}{item_id}|{gew_ton}|{gew_unter}",
        ),
        knoten(
            "Abspielen",
            f"{WAHL_PRAEFIX}{item_id}|{gew_ton}|{gew_unter}",
            abspielbar=True,
        ),
    ]

    return BrowseMedia(
        media_class=MediaClass.DIRECTORY,
        media_content_id=kennung,
        media_content_type=_art(item),
        title=_titel(item),
        can_play=False,
        can_expand=True,
        children=kinder,
        children_media_class=MediaClass.VIDEO,
        thumbnail=bild,
    )


# --------------------------------------------------------------------------
# Weiterschauen und Naechste Folge
#
# Die beiden Listen, in denen man meistens landet. Sie gehoeren in den
# Browser selbst und nicht in eine zweite Oberflaeche daneben - und weil sie
# benutzerbezogen sind, zeigen sie wirklich den eigenen Stand.
# --------------------------------------------------------------------------

LISTE_WEITER = "jfp-weiterschauen"
LISTE_NAECHSTE = "jfp-naechste"


def _hole_liste(client: JellyfinClient, user_id: str, welche: str) -> list[dict]:
    """Weiterschauen oder Naechste Folge vom Server holen.

    ACHTUNG: der user_id, den die Integration herumreicht, ist NICHT die
    Benutzerkennung - _get_user_id liest die Kennung der Anzeige-
    Einstellungen aus. Das faellt sonst nirgends auf, weil der Wert nie in
    einer Adresse landet; hier schon, und der Server antwortet dann mit 403.
    Die echte Kennung liefert users(): die Bibliothek ersetzt darin
    {UserId} durch den angemeldeten Benutzer.
    """
    if welche == LISTE_NAECHSTE:
        antwort = client.jellyfin.get_next(limit=24)
        return (antwort or {}).get("Items", [])

    ich = client.jellyfin.users() or {}
    echte_kennung = ich.get("Id")
    if not echte_kennung:
        return []
    antwort = client.jellyfin._get(
        "UserItems/Resume",
        {"userId": echte_kennung, "limit": 24, "enableImages": "true",
         "fields": "userData"},
    )
    return (antwort or {}).get("Items", [])


async def build_liste_response(
    hass: HomeAssistant,
    client: JellyfinClient,
    user_id: str,
    welche: str,
) -> BrowseMedia:
    """Weiterschauen bzw. Naechste Folge als Ordner."""
    eintraege = await hass.async_add_executor_job(_hole_liste, client, user_id, welche)

    kinder = []
    for e in eintraege:
        knoten = await item_payload(hass, client, user_id, e)
        # In diesen Listen steht eine Folge ohne ihre Serie sinnlos da - und
        # ohne ihre Staffel auch. Beides kommt vom Server mit (SeriesName,
        # ParentIndexNumber), es muss nur angezeigt werden.
        knoten.title = _beschriftung(e, mit_staffel=True)
        if e.get("SeriesName"):
            knoten.title = f"{e['SeriesName']} - {knoten.title}"
        kinder.append(knoten)

    return BrowseMedia(
        title="Weiterschauen" if welche == LISTE_WEITER else "Naechste Folge",
        media_content_id=welche,
        media_content_type="directory",
        media_class=MediaClass.DIRECTORY,
        children_media_class=MediaClass.VIDEO,
        can_play=False,
        can_expand=True,
        children=kinder,
    )


async def build_item_response(
    hass: HomeAssistant,
    client: JellyfinClient,
    user_id: str,
    media_content_id: str,
) -> BrowseMedia:
    """Create response payload for the provided media query."""
    if media_content_id in (LISTE_WEITER, LISTE_NAECHSTE):
        return await build_liste_response(hass, client, user_id, media_content_id)

    # Unsere eigenen Kennungen zuerst - fetch_item wuerde daran scheitern,
    # weil in ihnen mehr steckt als eine Jellyfin-Id.
    if media_content_id.startswith(
        (ANSICHT_PRAEFIX, TON_PRAEFIX, UNTER_PRAEFIX)
    ):
        return await build_track_response(hass, client, user_id, media_content_id)

    # Eine Folge oder ein Film hat keine Kinder im Sinne des Servers - bei uns
    # aber sehr wohl: Ton, Untertitel, Abspielen.
    item = await hass.async_add_executor_job(fetch_item, client, media_content_id)
    if item is not None and item.get("Type") in ("Episode", "Movie"):
        return await build_track_response(hass, client, user_id, media_content_id)

    title, media, thumbnail, media_type = await get_media_info(
        hass, client, user_id, media_content_id
    )

    if title is None or media is None:
        raise BrowseError(f"Media not found: {media_content_id}")

    children = await asyncio.gather(
        *(item_payload(hass, client, user_id, media_item) for media_item in media)
    )

    response = BrowseMedia(
        media_class=CONTAINER_TYPES_SPECIFIC_MEDIA_CLASS.get(
            str(media_type), MediaClass.DIRECTORY
        ),
        media_content_id=media_content_id,
        media_content_type=str(media_type),
        title=title,
        can_play=bool(media_type in PLAYABLE_MEDIA_TYPES and media_content_id),
        can_expand=True,
        can_search=True,
        children=children,
        thumbnail=thumbnail,
    )

    response.calculate_children_class()

    return response


def fetch_item(client: JellyfinClient, item_id: str) -> dict[str, Any] | None:
    """Fetch item from Jellyfin server."""
    result = client.jellyfin.get_item(item_id)

    if not result:
        return None

    item: dict[str, Any] = result
    return item


def fetch_items(
    client: JellyfinClient,
    params: dict[str, Any],
) -> list[dict[str, Any]] | None:
    """Fetch items from Jellyfin server."""
    result = client.jellyfin.user_items(params=params)

    if not result or "Items" not in result or len(result["Items"]) < 1:
        return None

    items: list[dict[str, Any]] = result["Items"]

    return [
        item
        for item in items
        if not item.get("IsFolder")
        or (item.get("IsFolder") and item.get("ChildCount", 1) > 0)
    ]


async def search_items(
    hass: HomeAssistant, client: JellyfinClient, user_id: str, query: SearchMediaQuery
) -> list[BrowseMedia]:
    """Search items in Jellyfin server."""
    search_result: list[BrowseMedia] = []

    items: list[dict[str, Any]] = []

    params: dict[str, Any] = {
        "searchTerm": query.search_query,
        "recursive": True,
        "limit": 60,
        "fields": "childCount,userData",
        # Ohne diese Begrenzung stehen zwischen den Treffern auch Personen,
        # Studios und Sammlungen - alles, was den Begriff im Namen hat.
        "includeItemTypes": "Movie,Series,Episode",
    }
    if query.media_content_id:
        params["parentId"] = query.media_content_id
    ergebnis = await hass.async_add_executor_job(
        partial(client.jellyfin.user_items, params=params)
    )
    items.extend((ergebnis or {}).get("Items", []))

    for item in items:
        search_result.append(await item_payload(hass, client, user_id, item))

    return search_result


async def get_media_info(
    hass: HomeAssistant,
    client: JellyfinClient,
    user_id: str,
    media_content_id: str,
) -> tuple[str | None, list[dict[str, Any]] | None, str | None, str | None]:
    """Fetch media info."""
    thumbnail: str | None = None
    title: str | None = None
    media: list[dict[str, Any]] | None = None
    media_type: str | None = None

    item = await hass.async_add_executor_job(fetch_item, client, media_content_id)

    if item is None:
        return None, None, None, None

    title = item["Name"]
    thumbnail = get_artwork_url(client, item)

    if item.get("IsFolder"):
        params: dict[str, Any] = {
            "parentId": media_content_id,
            "fields": "childCount,userData",
        }
        if item.get("Type") in ("CollectionFolder", "UserView", "Folder"):
            params["sortBy"] = "DateCreated"
            params["sortOrder"] = "Descending"
        media = await hass.async_add_executor_job(fetch_items, client, params)

    if not media or len(media) == 0:
        media = None

    media_type = CONTENT_TYPE_MAP.get(item["Type"], MEDIA_TYPE_NONE)

    return title, media, thumbnail, media_type
