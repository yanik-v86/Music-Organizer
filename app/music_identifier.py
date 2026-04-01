"""
Music fingerprint recognition and metadata lookup.
Uses AcoustID for audio fingerprinting and MusicBrainz for metadata.
"""
import subprocess
import json
from pathlib import Path
import re
from typing import Optional, Any, Tuple

import httpx

import app.config as config_module
from app.config import get_httpx_client_kwargs


# AcoustID API configuration
ACOUSTID_API_URL = "https://api.acoustid.org/v2/lookup"

def _mask_secret(s: str) -> str:
    """Hide most of API keys in debug output."""
    s = (s or "").strip()
    if not s:
        return ""
    if len(s) <= 6:
        return "*" * len(s)
    return f"{s[:3]}***{s[-3:]}"


def _acoustid_client_key() -> str:
    """Read key at call time so Settings reload applies without process restart."""
    cfg = getattr(config_module, "config", None)
    if cfg and hasattr(cfg, "acoustid") and cfg.acoustid:
        return (cfg.acoustid.api_key or "").strip()
    return ""

# MusicBrainz API configuration
MUSICBRAINZ_API_URL = "https://musicbrainz.org/ws/2"
MUSICBRAINZ_USER_AGENT = "MusicOrganizer/1.0"


def get_fingerprint_and_duration(audio_path: str) -> Tuple[Optional[str], int]:
    """
    Generate audio fingerprint using fpcalc (Chromaprint).
    Returns (fingerprint, duration_seconds). Duration improves AcoustID matching.
    """
    try:
        result = subprocess.run(
            ["fpcalc", "-json", str(audio_path)],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            fp = data.get("fingerprint")
            dur = int(data.get("duration") or 0)
            return fp, dur
    except Exception as e:
        print(f"Fingerprint error: {e}")
    return None, 0


def get_fingerprint(audio_path: str) -> Optional[str]:
    """Backward-compatible: fingerprint only."""
    fp, _ = get_fingerprint_and_duration(audio_path)
    return fp


def _extract_year_from_text(text: Any) -> str:
    """Extract first 4-digit year from MusicBrainz field values."""
    try:
        s = str(text or "")
    except Exception:
        return ""
    m = re.search(r"(\d{4})", s)
    return m.group(1) if m else ""


async def lookup_acoustid(audio_path: str, debug: bool = False) -> list[dict]:
    """
    Lookup track information using AcoustID.
    Returns list of possible matches.
    """
    api_key = _acoustid_client_key()
    if not api_key:
        return []

    fingerprint, duration_sec = get_fingerprint_and_duration(audio_path)
    if not fingerprint:
        return []

    if debug:
        # Avoid printing large fingerprints. Duration is enough to see "is there input".
        print(f"[acoustid][debug] fingerprint_ok=True duration_sec={duration_sec} path={audio_path}")
    
    try:
        async with httpx.AsyncClient(timeout=30, **get_httpx_client_kwargs()) as client:
            resp = await client.post(
                ACOUSTID_API_URL,
                data={
                    "client": api_key,
                    "fingerprint": fingerprint,
                    "duration": str(duration_sec),
                    "meta": "recordings+releases+artists",
                    "format": "json",
                }
            )
            data = resp.json()
            
            if data.get("status") == "ok":
                if debug:
                    results_raw = data.get("results") or []
                    print(
                        f"[acoustid][debug] status=ok results_count={len(results_raw)}",
                    )
                def coerce_acoustid_release(rel: dict[str, Any]) -> dict[str, Any]:
                    # AcoustID returns a "releases" structure with at least "title"/"date" in many cases,
                    # but keys may vary slightly, so we try a few common alternatives.
                    title = (
                        rel.get("title")
                        or rel.get("name")
                        or rel.get("album")
                        or rel.get("release")
                        or ""
                    )
                    date_str = rel.get("date") or rel.get("release_date") or rel.get("original_date") or ""
                    # Sometimes AcoustID returns only a year.
                    if not date_str:
                        date_str = rel.get("year") or ""
                    date_str = str(date_str or "")
                    year = _extract_year_from_text(date_str)
                    return {"title": title, "date": date_str, "year": year}

                results: list[dict[str, Any]] = []
                for result in data.get("results", []):
                    if "score" not in result:
                        continue
                    score = float(result["score"])
                    if score <= 0.5:
                        continue

                    acoustid_releases = [
                        coerce_acoustid_release(r)
                        for r in (result.get("releases") or [])
                        if isinstance(r, dict)
                    ]

                    recordings = result.get("recordings") or []
                    if recordings:
                        for recording in recordings:
                            results.append({
                                "score": score,
                                "acoustid": result.get("id"),
                                "recording_id": recording.get("id") if isinstance(recording, dict) else None,
                                "title": recording.get("title") if isinstance(recording, dict) else None,
                                "artist": (
                                    recording.get("artists", [{}])[0].get("name")
                                    if isinstance(recording, dict) and recording.get("artists")
                                    else None
                                ),
                                "duration": recording.get("length") if isinstance(recording, dict) else None,
                                # Fallback for album/date when MusicBrainz doesn't provide it.
                                "acoustid_releases": acoustid_releases,
                            })
                    else:
                        # Rare: only releases/artists without recordings.
                        artist = None
                        artists = result.get("artists") or []
                        if artists and isinstance(artists[0], dict):
                            artist = artists[0].get("name")
                        results.append({
                            "score": score,
                            "acoustid": result.get("id"),
                            "recording_id": None,
                            "title": None,
                            "artist": artist,
                            "duration": None,
                            "acoustid_releases": acoustid_releases,
                        })

                return sorted(results, key=lambda x: x["score"], reverse=True)
            if debug:
                print("[acoustid][debug] status!=ok:", data.get("status"), data.get("message") or data)
            print(f"AcoustID lookup: {data.get('status')!r} {data.get('message') or data}")
    except Exception as e:
        print(f"AcoustID lookup error: {e}")
    
    return []


async def lookup_musicbrainz_recording(recording_id: str, debug: bool = False) -> Optional[dict]:
    """
    Get detailed information from MusicBrainz by recording ID.
    """
    try:
        async with httpx.AsyncClient(
            timeout=10,
            headers={"User-Agent": MUSICBRAINZ_USER_AGENT},
            **get_httpx_client_kwargs(),
        ) as client:
            resp = await client.get(
                f"{MUSICBRAINZ_API_URL}/recording/{recording_id}",
                params={
                    # Need media+tracks to determine track position/number in the release.
                    # release-groups helps when release.date is empty.
                    "inc": "artists+releases+release-groups+media+tracks+labels+isrcs",
                    "fmt": "json"
                }
            )
            data = resp.json()
            
            track_numbers: list[int] = []

            def maybe_collect_track_number(track: Any) -> None:
                if not track:
                    return
                rec = track.get("recording") or {}
                if rec.get("id") != recording_id:
                    return
                # MusicBrainz commonly uses "position" (track number on a medium).
                pos = track.get("position") or track.get("track_number") or track.get("number")
                try:
                    pos_int = int(pos)
                except Exception:
                    return
                if pos_int > 0:
                    track_numbers.append(pos_int)
            
            # Some responses include top-level media/tracks.
            for media in data.get("media", []) or []:
                for track in media.get("tracks", []) or []:
                    maybe_collect_track_number(track)

            # Also try to walk media/tracks nested under releases.
            for r in data.get("releases", []) or []:
                for media in r.get("media", []) or []:
                    for track in media.get("tracks", []) or []:
                        maybe_collect_track_number(track)

            track_number = min(track_numbers) if track_numbers else 0

            releases: list[dict[str, Any]] = []
            for r in data.get("releases", []) or []:
                date_str = str(r.get("date") or "")
                releases.append(
                    {
                        "title": r.get("title") or "",
                        "date": date_str,
                        "year": _extract_year_from_text(date_str),
                        "media-count": len(r.get("media", []) or []),
                    }
                )

            release_groups: list[dict[str, Any]] = []
            for rg in data.get("release-groups", []) or []:
                first_date = rg.get("first-release-date") or rg.get("first-release-year") or ""
                release_groups.append(
                    {
                        "title": rg.get("title") or "",
                        "date": str(first_date or ""),
                        "year": _extract_year_from_text(first_date),
                        "media-count": len(rg.get("media", []) or []),
                    }
                )

            if debug:
                releases_with_year = [r for r in releases if r.get("year")]
                print(
                    "[musicbrainz][debug] recording:",
                    {"id": data.get("id"), "releases_count": len(releases), "releases_with_year": len(releases_with_year)},
                )
                # Print small sample to see which fields are missing.
                print("[musicbrainz][debug] releases_sample:", releases[:3])

            return {
                "id": data.get("id"),
                "title": data.get("title"),
                "artist": data.get("artists", [{}])[0].get("name") if data.get("artists") else None,
                "artist_sort_name": data.get("artists", [{}])[0].get("sort-name") if data.get("artists") else None,
                "track_number": track_number,
                "releases": releases,
                "release_groups": release_groups,
                "isrcs": [
                    isrc.get("id")
                    for media in data.get("media", [])
                    for track in media.get("tracks", [])
                    for isrc in track.get("recording", {}).get("isrcs", [])
                ],
            }
    except Exception as e:
        print(f"MusicBrainz lookup error: {e}")
    return None


async def search_musicbrainz(query: str, limit: int = 5) -> list[dict]:
    """
    Search MusicBrainz for recordings.
    """
    try:
        async with httpx.AsyncClient(
            timeout=10,
            headers={"User-Agent": MUSICBRAINZ_USER_AGENT},
            **get_httpx_client_kwargs(),
        ) as client:
            resp = await client.get(
                f"{MUSICBRAINZ_API_URL}/recording",
                params={
                    "query": query,
                    "fmt": "json",
                    "limit": limit,
                }
            )
            data = resp.json()
            
            results = []
            for recording in data.get("recordings", []):
                results.append({
                    "id": recording.get("id"),
                    "title": recording.get("title"),
                    "artist": recording.get("artists", [{}])[0].get("name") if recording.get("artists") else None,
                    "disambiguation": recording.get("disambiguation"),
                })
            return results
    except Exception as e:
        print(f"MusicBrainz search error: {e}")
    return []


def _quote_mb_query_value(value: str) -> str:
    """Escape user value for MusicBrainz Lucene-like query syntax."""
    s = str(value or "").strip()
    # Keep it simple and robust for quoted field queries.
    s = s.replace("\\", "\\\\").replace('"', '\\"')
    return s


def build_musicbrainz_recording_query(query: str = "", title: str = "", artist: str = "") -> str:
    """
    Build MusicBrainz recording query.
    - If title/artist are provided, use field-based query.
    - Otherwise fallback to raw query string.
    """
    title = (title or "").strip()
    artist = (artist or "").strip()
    query = (query or "").strip()

    parts: list[str] = []
    if title:
        parts.append(f'recording:"{_quote_mb_query_value(title)}"')
    if artist:
        parts.append(f'artist:"{_quote_mb_query_value(artist)}"')
    if parts:
        return " AND ".join(parts)
    return query


async def search_musicbrainz_enriched(
    query: str = "",
    title: str = "",
    artist: str = "",
    limit: int = 10,
    details_limit: int = 5,
) -> list[dict]:
    """
    Search recordings and enrich top results with detailed MusicBrainz metadata.
    """
    effective_query = build_musicbrainz_recording_query(query=query, title=title, artist=artist)
    if not effective_query:
        return []

    basic_results = await search_musicbrainz(effective_query, limit=limit)
    if not basic_results:
        return []

    enriched: list[dict] = []
    for idx, item in enumerate(basic_results):
        merged = dict(item)
        if idx < details_limit and item.get("id"):
            details = await lookup_musicbrainz_recording(str(item["id"]))
            if details:
                merged["artist_sort_name"] = details.get("artist_sort_name")
                merged["track_number"] = details.get("track_number", 0)
                merged["releases"] = details.get("releases", []) or []
                merged["release_groups"] = details.get("release_groups", []) or []
                merged["isrcs"] = details.get("isrcs", []) or []
                # Quick aliases for UI convenience.
                merged["albums"] = merged["releases"]
        enriched.append(merged)
    return enriched


async def identify_track(audio_path: str, debug: bool = False) -> dict:
    """
    Identify a track using AcoustID fingerprinting.
    Returns identification result with metadata suggestions.
    """
    # First try AcoustID
    api_key = _acoustid_client_key()
    if debug:
        print(f"[identify][debug] acoustid client present={bool(api_key)} key={_mask_secret(api_key)} path={audio_path}")

    acoustid_results = await lookup_acoustid(audio_path, debug=debug)
    
    if acoustid_results:
        # Get the best match
        best_match = acoustid_results[0]

        if debug:
            print(
                "[identify][debug] best AcoustID match:",
                {
                    "score": best_match.get("score"),
                    "acoustid": best_match.get("acoustid"),
                    "recording_id": best_match.get("recording_id"),
                    "title": best_match.get("title"),
                    "artist": best_match.get("artist"),
                    "acoustid_releases_count": len(best_match.get("acoustid_releases") or []),
                },
            )

        acoustid_releases = best_match.get("acoustid_releases") or []
        
        # Get detailed info from MusicBrainz
        releases: list[dict[str, Any]] = []
        release_groups: list[dict[str, Any]] = []
        title = best_match.get("title") or ""
        artist = best_match.get("artist")
        artist_sort_name = None
        track_number = 0
        isrcs: list[str] = []

        if best_match.get("recording_id"):
            detailed = await lookup_musicbrainz_recording(best_match["recording_id"], debug=debug)
            if detailed:
                title = detailed.get("title") or ""
                artist = detailed.get("artist")
                artist_sort_name = detailed.get("artist_sort_name")
                track_number = detailed.get("track_number", 0) or 0
                releases = detailed.get("releases", []) or []
                release_groups = detailed.get("release_groups", []) or []
                isrcs = detailed.get("isrcs", []) or []

        # Fallback: if MusicBrainz doesn't provide year/date, use AcoustID releases.
        # (This fixes cases where "album date/year" is missing.)
        if (not releases or not any(r.get("year") for r in releases)) and acoustid_releases:
            releases = acoustid_releases

        if debug:
            # Keep debug print bounded: print just a small sample.
            print(
                "[identify][debug] resolved candidates:",
                {
                    "releases_count": len(releases),
                    "release_groups_count": len(release_groups),
                    "releases_sample": releases[:3],
                    "release_groups_sample": release_groups[:3],
                },
            )

        return {
            "status": "identified",
            "confidence": best_match["score"],
            "source": "acoustid",
            "acoustid": best_match.get("acoustid"),
            "recording_id": best_match.get("recording_id"),
            "title": title,
            "artist": artist,
            "artist_sort_name": artist_sort_name,
            "track_number": track_number,
            "releases": releases,
            "release_groups": release_groups,
            "isrcs": isrcs,
        }
        
        # Should not normally reach here because we return above when acoustid_results exists,
        # but keep a safe fallback.
        return {
            "status": "identified",
            "confidence": best_match.get("score", 0),
            "source": "acoustid",
            "acoustid": best_match.get("acoustid"),
            "recording_id": best_match.get("recording_id"),
            "title": best_match.get("title"),
            "artist": best_match.get("artist"),
            "track_number": 0,
            "releases": acoustid_releases,
            "release_groups": [],
            "isrcs": [],
        }
    
    return {"status": "not_found", "source": "acoustid"}


async def search_track(
    query: str = "",
    title: str = "",
    artist: str = "",
    limit: int = 10,
) -> list[dict]:
    """
    Search for tracks on MusicBrainz.
    """
    return await search_musicbrainz_enriched(
        query=query,
        title=title,
        artist=artist,
        limit=limit,
        details_limit=min(limit, 5),
    )
