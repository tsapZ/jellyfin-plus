# -*- coding: utf-8 -*-
"""Baut custom_components/jellyfin_plus - die offizielle Jellyfin-Integration
mit einer Zwischenstufe vor dem Abspielen.

WARUM EIN ABLEGER STATT ETWAS EIGENEM
Anmeldung, Sitzungsverwaltung, Geraeteregistrierung, Poster und Suche sind in
der offiziellen Integration erledigt und werden gepflegt. Was fehlt, sind
genau zwei Dinge:

  1. Eine Folge startet beim Antippen SOFORT. Man kann vorher weder Ton- noch
     Untertitelspur waehlen - HAs media_player.play_media reicht so etwas
     nicht durch.
  2. Folgen stehen nur mit Namen da, ohne Nummer.

DIE SPURWAHL MUSS ZWEIMAL GESAGT WERDEN
Jellyfins Abspielbefehl kennt audioStreamIndex und subtitleStreamIndex, und
naheliegenderweise wuerde man es dabei belassen. Der Tizen-Client des
Fernsehers WERTET SIE NICHT AUS - er nimmt immer seine eigene Standardspur,
bei eingebetteten wie externen Untertiteln (am 2026-08-20 an drei Faellen
nachgemessen, auch nach vorherigem Stop). Ein SetSubtitleStreamIndex NACH dem
Start greift dagegen binnen Sekunden. Deshalb setzt _spuren_nachsetzen die
Wahl ein zweites Mal, sobald der Titel wirklich laeuft. Die Parameter bleiben
trotzdem im Abspielbefehl - ein Client, der sie auswertet, laeuft dann von
der ersten Sekunde an richtig, statt sichtbar umzuschalten.

Der Startknopf "Abspielen (Standard)" traegt darum -2 und nicht -1: -1 heisst
"Untertitel aus", und das ist etwas anderes als "nimm, was der Server
vorsieht".

Beides wird hier nachgeruestet, alles andere bleibt unveraendert.

WIE DIE AUSWAHL FUNKTIONIERT
Eine Folge ist kein Endknoten mehr, sondern ein Ordner. Darin steht je ein
Eintrag pro Kombination aus Ton- und Untertitelspur; ein Tipp darauf spielt
mit genau diesen Spuren. Die Kennung traegt die Wahl mit sich:

    jfp|<ItemId>|<AudioIndex>|<SubtitleIndex>

VERSIONSBINDUNG
Die Vorlage wird aus dem HA-Kern in genau der Fassung geholt, die laeuft -
gelesen aus /homeassistant/.HA_VERSION, nicht von Hand eingetragen. Die
Fassung landet als `version` im manifest.json, damit von aussen sichtbar
ist, zu welchem Kern der Ableger gehoert; packages/jellyfin_pflege.yaml
vergleicht das und meldet sich, wenn es auseinanderlaeuft.

NACH EINEM HA-UPDATE DIESES SKRIPT LAUFEN LASSEN. Beim Sprung auf 2026.9.3
hat sich in der Vorlage genau eine Zeile geaendert - die Signatur von
async_remove_config_entry_device von dr.DeviceEntry auf dr.AnyDeviceEntry,
einer der Breaking Changes der Fassung. Ein von Hand gepflegter Fork haette
die alte behalten, ohne dass irgendwo etwas aufgefallen waere. Genau dafuer
gibt es dieses Skript: die Aenderungen von HA kommen automatisch mit, die
eigenen werden neu daraufgesetzt, und wenn eine nicht mehr passt, bricht
der zugehoerige assert mit Namen ab.
"""

import json
import os
import re
import shutil
import sys
import time
import urllib.request


def laufende_version():
    """Die Fassung, die HA gerade wirklich ausfuehrt.

    Bis zum 2026-09-20 stand hier eine Zahl von Hand. Das ist genau die
    Sorte Schritt, die man nach einem Update vergisst - und dann patcht
    das Skript die Vorlage der VORIGEN Fassung und meldet trotzdem Erfolg.
    /homeassistant/.HA_VERSION schreibt HA bei jedem Start selbst.

    Eine andere Fassung geht als Argument: `python3 baue_integration.py 2026.8.3`.
    """
    if len(sys.argv) > 1:
        return sys.argv[1].strip()
    if not os.path.exists('/homeassistant/.HA_VERSION'):
        sys.exit('Keine HA-Fassung: als Argument angeben, z. B. 2026.9.3')
    with open('/homeassistant/.HA_VERSION', encoding='utf-8') as f:
        return f.read().strip()


VERSION = laufende_version()
QUELLE = ('https://raw.githubusercontent.com/home-assistant/core/%s/'
          'homeassistant/components/jellyfin/' % VERSION)
# Auf Fabians HA der echte Ordner; im GitHub-Repo (tsapZ/jellyfin-plus) setzt
# der Workflow JFP_ZIEL=custom_components/jellyfin_plus.
ZIEL = os.environ.get('JFP_ZIEL', '/homeassistant/custom_components/jellyfin_plus')
print('Vorlage: home-assistant/core @ %s' % VERSION)

DATEIEN = ['__init__.py', 'browse_media.py', 'client_wrapper.py', 'config_flow.py',
           'const.py', 'coordinator.py', 'diagnostics.py', 'entity.py',
           'icons.json', 'media_player.py', 'media_source.py', 'remote.py',
           'sensor.py', 'services.py', 'services.yaml', 'strings.json']


def hol(name):
    r = urllib.request.Request(QUELLE + name, headers={'User-Agent': 'curl'})
    return urllib.request.urlopen(r, timeout=40).read().decode('utf-8')


# Erst holen, dann sichern, dann schreiben. Der Reihe nach, weil ein
# Netzfehler sonst eine Sicherung anlegt, die niemand braucht - und weil
# eine halb ueberschriebene Integration schlimmer ist als gar keine.
inhalt = {}
for f in DATEIEN:
    inhalt[f] = hol(f)
    print('  geholt  %-20s %6d' % (f, len(inhalt[f])))

if os.path.isdir(ZIEL) and os.path.isdir('/homeassistant/werkzeuge'):
    sicherung = '/homeassistant/werkzeuge/alt/jfp.vor-%s' % time.strftime('%Y%m%d-%H%M')
    os.makedirs('/homeassistant/werkzeuge/alt', exist_ok=True)
    shutil.rmtree(sicherung, ignore_errors=True)
    shutil.copytree(ZIEL, sicherung)
    print()
    print('  gesichert nach %s' % sicherung)

os.makedirs(ZIEL, exist_ok=True)
os.makedirs(ZIEL + '/translations', exist_ok=True)

# ---------------------------------------------------------------- manifest --
inhalt['manifest.json'] = json.dumps({
    "domain": "jellyfin_plus",
    "name": "Jellyfin Plus",
    "codeowners": ["@tsapZ"],
    "config_flow": True,
    "documentation": "https://github.com/tsapZ/jellyfin-plus",
    "issue_tracker": "https://github.com/tsapZ/jellyfin-plus/issues",
    "iot_class": "local_polling",
    "loggers": ["jellyfin_apiclient_python"],
    "requirements": ["jellyfin-apiclient-python==1.11.0"],
    # Die HA-Fassung, aus der die Vorlage stammt - NICHT eine eigene
    # Zaehlung. Nur so laesst sich von aussen sehen, ob der Ableger noch zum
    # laufenden Kern passt; sensor.jellyfin_plus_vorlage in
    # packages/jellyfin_pflege.yaml liest genau dieses Feld.
    "version": VERSION,
}, indent=2, ensure_ascii=False) + '\n'

# ------------------------------------------------------------------- const --
t = inhalt['const.py']
assert 'DOMAIN' in t
# Achtung: die Zeile traegt eine Typangabe (DOMAIN: Final = "jellyfin"),
# ein Muster ohne sie trifft nicht.
t, n = re.subn(r'^DOMAIN\s*(?::\s*\w+\s*)?=\s*.+$',
               'DOMAIN: Final = "jellyfin_plus"', t, count=1, flags=re.M)
assert n == 1, 'DOMAIN-Zeile nicht gefunden'
t = t.replace('USER_APP_NAME: Final = "Home Assistant"',
              'USER_APP_NAME: Final = "Home Assistant Plus"')
inhalt['const.py'] = t

# ------------------------------------------------------------ browse_media --
t = inhalt['browse_media.py']

# 1) Folgen mit Nummer beschriften, und Folge/Film aufklappbar statt spielbar
ALT_PAYLOAD = '''    title = item["Name"]
    thumbnail = get_artwork_url(client, item, 600)

    media_content_id = item["Id"]
    media_content_type = CONTENT_TYPE_MAP.get(item["Type"], MEDIA_TYPE_NONE)

    return BrowseMedia(
        title=title,
        media_content_id=media_content_id,
        media_content_type=media_content_type,
        media_class=MEDIA_CLASS_MAP.get(item["Type"], MediaClass.DIRECTORY),
        can_play=bool(media_content_type in PLAYABLE_MEDIA_TYPES and media_content_id),
        can_expand=bool(item.get("IsFolder")),
        children_media_class=None,
        thumbnail=thumbnail,
    )'''

NEU_PAYLOAD = '''    title = _beschriftung(item)

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
    )'''
assert ALT_PAYLOAD in t, 'item_payload nicht wie erwartet'
t = t.replace(ALT_PAYLOAD, NEU_PAYLOAD, 1)

# 1b) Ordneransichten: Gesehen-Zustand anfordern, Bibliotheken nach Neuzugang
#
# Ohne `fields=userData` kommt der Gesehen-Zustand gar nicht erst mit und
# jede Zeile saehe ungesehen aus. Und ohne `sortBy` sortiert Jellyfin nach
# SortName - alphabetisch, waehrend in seiner eigenen Oberflaeche das
# Zuletzt-hinzugefuegte vorn steht. Wer eine frisch importierte Folge sucht,
# blaettert sonst durch das ganze Alphabet.
#
# Das gilt NUR fuer die Bibliotheken. Innerhalb einer Serie muss die
# Reihenfolge bei Staffel und Folge bleiben.
ALT_SORT = """    if item.get("IsFolder"):
        media = await hass.async_add_executor_job(
            fetch_items, client, {"parentId": media_content_id, "fields": "childCount"}
        )"""
NEU_SORT = """    if item.get("IsFolder"):
        params: dict[str, Any] = {
            "parentId": media_content_id,
            "fields": "childCount,userData",
        }
        if item.get("Type") in ("CollectionFolder", "UserView", "Folder"):
            params["sortBy"] = "DateCreated"
            params["sortOrder"] = "Descending"
        media = await hass.async_add_executor_job(fetch_items, client, params)"""
assert ALT_SORT in t, 'get_media_info nicht wie erwartet'
t = t.replace(ALT_SORT, NEU_SORT, 1)

# 1c) Suche: ueber user_items statt ueber die Huelle search_media_items
#
# Die Vorlage baute ihre Treffer von Hand und bestimmte can_play aus
# item["MediaType"] - das ist "Video" oder "Audio", nie "episode". Der
# Vergleich gegen PLAYABLE_MEDIA_TYPES war damit immer falsch, also war kein
# Treffer abspielbar; ausserdem fehlte die Fenster-Kennung fuer die
# Spurenauswahl. Jetzt entstehen Treffer mit item_payload wie jede andere
# Liste.
#
# search_media_items nimmt nur die Parameter an, die seine Signatur kennt -
# `fields` gehoert nicht dazu, also kaeme kein UserData mit. user_items
# reicht ein beliebiges Woerterbuch an den Server durch.
ALT_SUCHE = """    items: list[dict[str, Any]] = []
    # Search for items based on media filter classes (or all if none specified)
    media_types: list[MediaClass] | list[None] = []
    if query.media_filter_classes:
        media_types = query.media_filter_classes
    else:
        media_types = [None]

    for media_type in media_types:
        items_dict: dict[str, Any] = await hass.async_add_executor_job(
            partial(
                client.jellyfin.search_media_items,
                term=query.search_query,
                media=media_type,
                parent_id=query.media_content_id,
            )
        )
        items.extend(items_dict.get("Items", []))"""
NEU_SUCHE = """    items: list[dict[str, Any]] = []

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
    items.extend((ergebnis or {}).get("Items", []))"""
assert ALT_SUCHE in t, 'search_items nicht wie erwartet'
t = t.replace(ALT_SUCHE, NEU_SUCHE, 1)

ALT_TREFFER = """    for item in items:
        content_type: str = item["MediaType"]

        response = BrowseMedia(
            media_class=CONTAINER_TYPES_SPECIFIC_MEDIA_CLASS.get(
                content_type, MediaClass.DIRECTORY
            ),
            media_content_id=item["Id"],
            media_content_type=content_type,
            title=item["Name"],
            thumbnail=get_artwork_url(client, item),
            can_play=bool(content_type in PLAYABLE_MEDIA_TYPES),
            can_expand=item.get("IsFolder", False),
            children=None,
        )
        search_result.append(response)"""
NEU_TREFFER = """    for item in items:
        search_result.append(await item_payload(hass, client, user_id, item))"""
assert ALT_TREFFER in t, 'Trefferschleife nicht wie erwartet'
t = t.replace(ALT_TREFFER, NEU_TREFFER, 1)

# 2) Spurenauswahl bauen
SPUREN = '''

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
            name = "\\u2713 " + name
        elif (ud.get("PlaybackPositionTicks") or 0) > 0:
            name = "\\u25b6 %d%% " % round(ud.get("PlayedPercentage") or 0) + name
    else:
        offen = ud.get("UnplayedItemCount")
        if offen == 0:
            name = "\\u2713 " + name
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
'''

# Vor build_item_response einfuegen
ANKER = 'async def build_item_response('
assert ANKER in t
t = t.replace(ANKER, SPUREN.lstrip('\n') + '\n\n' + ANKER, 1)

# 3) build_item_response soll fuer Folgen/Filme die Spurenauswahl liefern
ALT_BUILD = '''    title, media, thumbnail, media_type = await get_media_info(
        hass, client, user_id, media_content_id
    )

    if title is None or media is None:
        raise BrowseError(f"Media not found: {media_content_id}")'''
NEU_BUILD = '''    if media_content_id in (LISTE_WEITER, LISTE_NAECHSTE):
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
        raise BrowseError(f"Media not found: {media_content_id}")'''
assert ALT_BUILD in t
t = t.replace(ALT_BUILD, NEU_BUILD, 1)

# 4) Weiterschauen und Naechste Folge in die Wurzel des Browsers
ALT_ROOT = '''    children = [
        await item_payload(hass, client, user_id, folder)
        for folder in folders["Items"]
        if folder.get("CollectionType") in SUPPORTED_COLLECTION_TYPES
    ]'''
NEU_ROOT = '''    children = [
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
        )'''
assert ALT_ROOT in t, 'build_root_response nicht wie erwartet'
t = t.replace(ALT_ROOT, NEU_ROOT, 1)

# 4b) Suche in jeder Bibliothek (Fabian 2026-11-16): HAs Medienbrowser zeigt das
# Suchfeld nur, wenn der geoeffnete Ordner can_search meldet - und reicht dann
# dessen Kennung an search_items weiter, das daraus parentId macht. In "Filme"
# wird also nur in Filmen gesucht, in "Serien" nur in Serien.
ALT_KANNSUCHEN = '''        can_play=bool(media_type in PLAYABLE_MEDIA_TYPES and media_content_id),
        can_expand=True,
        children=children,
        thumbnail=thumbnail,
    )'''
NEU_KANNSUCHEN = '''        can_play=bool(media_type in PLAYABLE_MEDIA_TYPES and media_content_id),
        can_expand=True,
        can_search=True,
        children=children,
        thumbnail=thumbnail,
    )'''
assert t.count(ALT_KANNSUCHEN) == 1, 'build_item_response-Ende nicht wie erwartet'
t = t.replace(ALT_KANNSUCHEN, NEU_KANNSUCHEN, 1)

inhalt['browse_media.py'] = t

# ------------------------------------------------------------- coordinator --
t = inhalt['coordinator.py']

ALT_SITZ = '''        sessions_by_id: dict[str, dict[str, Any]] = {
            session["Id"]: session
            for session in sessions
            if session["DeviceId"] != self.client_device_id
            and session["Client"] != USER_APP_NAME
        }'''
NEU_SITZ = '''        # Welche Clients Spieler werden, steht in den Optionen der Integration
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
        }'''
assert ALT_SITZ in t, 'Sitzungsfilter nicht wie erwartet'
t = t.replace(ALT_SITZ, NEU_SITZ, 1)

ALT_IMP = 'from .const import CONF_CLIENT_DEVICE_ID, DOMAIN, LOGGER, USER_APP_NAME'
NEU_IMP = '''from .const import CONF_CLIENT_DEVICE_ID, DOMAIN, LOGGER, USER_APP_NAME

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
# Integration statt einer festen Liste - siehe _async_update_data.'''
assert ALT_IMP in t, 'const-Import nicht wie erwartet'
t = t.replace(ALT_IMP, NEU_IMP, 1)

inhalt['coordinator.py'] = t

# ------------------------------------------------------------- config_flow --
# Option "clients": welche Jellyfin-Clients Spieler werden (Komma-getrennt).
t = inhalt['config_flow.py']
ALT_OPT = '''OPTIONAL_DATA_SCHEMA = vol.Schema(
    {vol.Optional("audio_codec"): vol.In(SUPPORTED_AUDIO_CODECS)}
)'''
NEU_OPT = '''OPTIONAL_DATA_SCHEMA = vol.Schema(
    {
        vol.Optional("audio_codec"): vol.In(SUPPORTED_AUDIO_CODECS),
        vol.Optional("clients", default=""): str,
    }
)'''
assert ALT_OPT in t, 'Optionsschema nicht wie erwartet'
t = t.replace(ALT_OPT, NEU_OPT, 1)
inhalt['config_flow.py'] = t

# ------------------------------------------------------------ media_player --
t = inhalt['media_player.py']

ALT_PLAY = '''        self.coordinator.api_client.jellyfin.remote_play_media(
            self.session_id, [media_id], command
        )'''
NEU_PLAY = '''        # Eine angetippte Folge spielt nicht, sie fragt erst nach den Spuren.
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
        )'''
assert ALT_PLAY in t
t = t.replace(ALT_PLAY, NEU_PLAY, 1)

# time wird fuers Warten in _spuren_nachsetzen gebraucht und ist im
# Original nicht importiert.
t = t.replace('import logging' + chr(10),
              'import logging' + chr(10) + 'import time' + chr(10), 1)
assert chr(10) + 'import time' in t, 'import time nicht eingesetzt'

t = t.replace(
    'from .browse_media import build_item_response, build_root_response, search_items',
    'from .browse_media import (\n'
    '    FENSTER_PRAEFIX,\n'
    '    build_item_response,\n'
    '    build_root_response,\n'
    '    fetch_item,\n'
    '    search_items,\n'
    '    zerlege_wahl,\n'
    ')')

# --------------------------------------------------------- Sprung merken --
#
# WAS DAS BEHEBT
# Wer dreimal kurz hintereinander "+30 s" drueckte, landete bei +30 statt
# bei +90 - und musste zwischen zwei Druecken fuenf bis acht Sekunden
# warten. Der Grund liegt nicht im Knopf, sondern in der Zahl, von der er
# losrechnet: media_position kommt aus dem Koordinator, der den Server alle
# zehn Sekunden fragt, und der Server erfaehrt die neue Stelle erst, wenn
# der Fernseher sie meldet. Innerhalb dieses Fensters liefert jede Abfrage
# dieselbe alte Zahl, also rechnen alle drei Druecke von derselben Stelle.
#
# Ab hier traegt der Spieler seine eigene Absicht sofort ein und
# verteidigt sie kurz gegen den nachhinkenden Serverstand. Damit stimmt
# nebenbei auch der Fortschrittsbalken der Wiedergabekarte direkt nach
# einem Sprung, statt zehn Sekunden lang zurueckzuspringen.
t = t.replace('from homeassistant.util.dt import parse_datetime',
              'from homeassistant.util.dt import parse_datetime, utcnow', 1)
assert 'parse_datetime, utcnow' in t, 'utcnow-Import nicht gesetzt'
t = t.replace('import logging' + chr(10),
              'from datetime import timedelta' + chr(10) + 'import logging' + chr(10), 1)
assert 'from datetime import timedelta' in t, 'timedelta-Import nicht gesetzt'

# ------------------------------------------------- Zeitstempel der Stelle --
#
# DIE FALLE, DIE EINEN GANZEN TESTLAUF GEKOSTET HAT (2026-09-20)
# media_position_updated_at kommt in der Vorlage aus LastPlaybackCheckIn -
# und das ist der Zeitpunkt der letzten FORTSCHRITTSMELDUNG des Clients,
# nicht der Zeitpunkt der Stelle. Beim START eines Titels setzt Jellyfin
# NowPlayingItem und PositionTicks (aus /Sessions/Playing), fasst
# LastPlaybackCheckIn aber nicht an - das aendert erst die naechste
# Fortschrittsmeldung (/Sessions/Playing/Progress).
#
# Direkt nach dem Start ist die Stelle also brandneu und ihr Zeitstempel
# minutenalt. Gemessen: Folge lief seit 8 Sekunden, Stempel 340 Sekunden
# alt. "+30 s" sprang daraufhin von Sekunde 8 auf Sekunde 378, und der
# Fortschrittsbalken der Wiedergabekarte stand fuenf Minuten zu weit.
#
# Aelter als ein Abfragetakt KANN die Stelle nicht sein - der Koordinator
# hat sie gerade geholt. Also nach unten begrenzen. Meldet der Client
# wirklich nicht mehr, laeuft die Anzeige dadurch hoechstens einen Takt
# voraus statt beliebig weit daneben.
ALT_STEMPEL = '''            media_position_updated = (
                parse_datetime(self.session_data["LastPlaybackCheckIn"])
                if self.now_playing
                else None
            )'''
NEU_STEMPEL = '''            media_position_updated = (
                parse_datetime(self.session_data["LastPlaybackCheckIn"])
                if self.now_playing
                else None
            )
            if media_position_updated is not None:
                takt = self.coordinator.update_interval or timedelta(seconds=10)
                frueheste = utcnow() - takt
                if media_position_updated < frueheste:
                    media_position_updated = frueheste'''
assert ALT_STEMPEL in t, 'LastPlaybackCheckIn nicht wie erwartet'
t = t.replace(ALT_STEMPEL, NEU_STEMPEL, 1)

ALT_SEEK = '''    @override
    def media_seek(self, position: float) -> None:
        """Send seek command."""
        self.coordinator.api_client.jellyfin.remote_seek(
            self.session_id, int(position * 10000000)
        )'''
NEU_SEEK = '''    # Wie lange die eigene Absicht gegen den Serverstand gilt: zwei
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
        self.schedule_update_ha_state()'''
assert ALT_SEEK in t, 'media_seek nicht wie erwartet'
t = t.replace(ALT_SEEK, NEU_SEEK, 1)

ALT_POS = '''        self._attr_media_duration = media_duration
        self._attr_media_position = media_position
        self._attr_media_position_updated_at = media_position_updated'''
NEU_POS = '''        self._attr_media_duration = media_duration
        media_position, media_position_updated = self._sprung_halten(
            media_position, media_position_updated
        )
        self._attr_media_position = media_position
        self._attr_media_position_updated_at = media_position_updated'''
assert ALT_POS in t, 'Positionszuweisung nicht wie erwartet'
t = t.replace(ALT_POS, NEU_POS, 1)

inhalt['media_player.py'] = t

# ------------------------------------------------------------ Uebersetzung --
# Die Vorlage verweist mit [%key:common::...%] auf HAs gemeinsame
# Textbausteine. Einer EIGENEN Integration stehen die nicht zur Verfuegung -
# die Verweise erscheinen dann woertlich im Einrichtungsdialog. Also echte
# Texte hinterlegen.

DE = {
    "title": "Jellyfin mit Spurenwahl",
    "config": {
        "abort": {
            "already_configured": "Dieser Zugang ist bereits eingerichtet.",
            "reauth_successful": "Die Anmeldung wurde erneuert.",
        },
        "error": {
            "cannot_connect": "Verbindung fehlgeschlagen - stimmt die Adresse?",
            "invalid_auth": "Benutzername oder Kennwort stimmt nicht.",
            "unknown": "Unerwarteter Fehler.",
        },
        "step": {
            "user": {
                "title": "Mit Jellyfin verbinden",
                "description": (
                    "Benutzername und Kennwort statt eines API-Schluessels: der "
                    "daraus entstehende Zugang darf nur als dieser Benutzer "
                    "handeln. Dadurch zeigen \"Weiterschauen\" und \"Naechste "
                    "Folge\" auch wirklich deine Listen."
                ),
                "data": {
                    "url": "Adresse des Servers",
                    "username": "Benutzername",
                    "password": "Kennwort",
                },
                "data_description": {
                    "url": "Zum Beispiel https://jellyfin.example.org",
                },
            },
            "reauth_confirm": {
                "title": "Anmeldung erneuern",
                "description": "Das Kennwort wird erneut gebraucht.",
                "data": {"password": "Kennwort"},
            },
        },
    },
    "entity": {
        "sensor": {
            "watching": {"name": "Aktive Clients", "unit_of_measurement": "Clients"}
        }
    },
    "options": {
        "step": {"init": {
            "data": {"audio_codec": "Tonformat",
                     "clients": "Nur diese Clients werden Spieler"},
            "data_description": {"clients": "Komma-getrennt, so wie Jellyfin sie unter Geraete nennt (z. B. Jellyfin for Tizen). Leer = alle fernsteuerbaren."}}}
    },
    "services": {
        "play_media_shuffle": {
            "name": "Zufaellig abspielen",
            "description": "Spielt die Auswahl in zufaelliger Reihenfolge.",
            "fields": {
                "media": {"name": "Medium", "description": "Was abgespielt werden soll."}
            },
        }
    },
}

EN = {
    "title": "Jellyfin with track selection",
    "config": {
        "abort": {
            "already_configured": "This account is already configured.",
            "reauth_successful": "Re-authentication was successful.",
        },
        "error": {
            "cannot_connect": "Failed to connect.",
            "invalid_auth": "Invalid authentication.",
            "unknown": "Unexpected error.",
        },
        "step": {
            "user": {
                "title": "Connect to Jellyfin",
                "description": (
                    "Username and password rather than an API key: the resulting "
                    "token may only act as this user, so Resume and Next Up show "
                    "your own lists."
                ),
                "data": {
                    "url": "Server address",
                    "username": "Username",
                    "password": "Password",
                },
                "data_description": {"url": "For example https://jellyfin.example.com"},
            },
            "reauth_confirm": {
                "title": "Re-authenticate",
                "description": "The password is needed again.",
                "data": {"password": "Password"},
            },
        },
    },
    "entity": {
        "sensor": {
            "watching": {"name": "Active clients", "unit_of_measurement": "clients"}
        }
    },
    "options": {"step": {"init": {
        "data": {"audio_codec": "Audio codec", "clients": "Only these clients become players"},
        "data_description": {"clients": "Comma-separated, as Jellyfin lists them under Devices (e.g. Jellyfin for Tizen). Empty = every remote-controllable client."}}}},
    "services": {
        "play_media_shuffle": {
            "name": "Play media shuffled",
            "description": "Starts playing the selection shuffled.",
            "fields": {
                "media": {"name": "Media", "description": "The media to play."}
            },
        }
    },
}

inhalt["strings.json"] = json.dumps(EN, indent=2, ensure_ascii=False)
inhalt["translations/en.json"] = json.dumps(EN, indent=2, ensure_ascii=False)
inhalt["translations/de.json"] = json.dumps(DE, indent=2, ensure_ascii=False)

# Ein eigenes Logo laesst sich NICHT mitliefern - Markenbilder kommen aus
# brands.home-assistant.io und sind an die Domaene gebunden. HA zeigt darum
# ein neutrales Sinnbild. Wenigstens die Entitaetssymbole sind gesetzt.
inhalt["icons.json"] = json.dumps({
    "entity": {"sensor": {"watching": {"default": "mdi:television-play"}}},
    "services": {"play_media_shuffle": {"service": "mdi:shuffle-variant"}},
}, indent=2, ensure_ascii=False)

# --------------------------------------------------------------- schreiben --
inhalt['manifest.json'] = inhalt['manifest.json']
for name, text in inhalt.items():
    pfad = os.path.join(ZIEL, name)
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    with open(pfad, 'w', encoding='utf-8') as f:
        f.write(text)

print()
print('geschrieben nach', ZIEL)
for w, _, fs in os.walk(ZIEL):
    for f in sorted(fs):
        p = os.path.join(w, f)
        print('  %-46s %6d' % (p.replace(ZIEL + '/', ''), os.path.getsize(p)))

# Gegenproben
b = open(ZIEL + '/browse_media.py', encoding='utf-8').read()
m = open(ZIEL + '/media_player.py', encoding='utf-8').read()
c = open(ZIEL + '/const.py', encoding='utf-8').read()
print()
print('Pruefungen:')
print('  DOMAIN               ', re.search(r'DOMAIN.*=.*', c).group(0))
print('  Spurenauswahl da     ', 'build_track_response' in b)
print('  Nummerierung da      ', "IndexNumber" in b)
print('  play_media erweitert ', 'zerlege_wahl' in m)
for f in ('browse_media.py', 'media_player.py', 'const.py', '__init__.py'):
    import py_compile
    py_compile.compile(os.path.join(ZIEL, f), doraise=True)
print('  alle Dateien syntaktisch in Ordnung')
