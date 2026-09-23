"""Album Cover Fetcher — finds album artwork using Cover Art Archive and Apple Music/iTunes.

Folders are scanned recursively. Audio tags supply artist and album; when they are
unavailable, the folder name is used as a fallback. The downloaded image is saved
inside each album folder as "<Album Title>.jpg".
"""
from __future__ import annotations

import io
import json
import queue
import re
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    from mutagen import File as MutagenFile
except ImportError:  # Makes the installation error clearer inside the UI.
    MutagenFile = None

try:
    from send2trash import send2trash
except ImportError:
    send2trash = None

APP_NAME = "Album Cover Fetcher"
USER_AGENT = "AlbumCoverFetcher/1.0 (personal library artwork tool)"
AUDIO_EXTENSIONS = {".mp3", ".flac", ".m4a", ".mp4", ".ogg", ".opus", ".aac", ".wma", ".wav", ".aiff"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"}


@dataclass(frozen=True)
class AlbumFolder:
    folder: Path
    artist: str
    album: str


def clean_text(value: object) -> str:
    """Extract and normalise a textual tag value from mutagen's varied shapes."""
    if isinstance(value, (list, tuple)):
        value = value[0] if value else ""
    return str(value or "").strip()


def safe_filename(title: str) -> str:
    title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title).strip().rstrip(".")
    return title[:180] or "Album Cover"


def request_json(url: str) -> object:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=18) as response:
        return json.loads(response.read().decode("utf-8"))


def request_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "image/jpeg,image/*;q=0.8"})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read()
        content_type = response.headers.get("Content-Type", "")
    if not data or not content_type.startswith("image/"):
        raise ValueError("The source did not return an image")
    return data


def first_tag(audio: object, keys: tuple[str, ...]) -> str:
    tags = getattr(audio, "tags", None)
    if not tags:
        return ""
    for key in keys:
        try:
            value = tags.get(key)
        except AttributeError:
            continue
        text = clean_text(value)
        if text:
            return text
    return ""


def read_album_tags(audio_path: Path) -> tuple[str, str]:
    if MutagenFile is None:
        raise RuntimeError("Mutagen is not installed. Run: pip install -r requirements.txt")
    audio = MutagenFile(audio_path, easy=True)
    if audio is None:
        return "", ""
    artist = first_tag(audio, ("albumartist", "artist"))
    album = first_tag(audio, ("album",))
    return artist, album


def move_other_images_to_trash(folder: Path, keep: set[Path]) -> tuple[int, list[str]]:
    """Move other images in one album folder to the OS Recycle Bin/Trash.

    This is recoverable and never scans child folders or deletes audio files.
    """
    if send2trash is None:
        return 0, ["Image cleanup is unavailable: install the updated requirements first."]
    kept = {path.resolve() for path in keep}
    moved = 0
    warnings: list[str] = []
    for path in folder.iterdir():
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        if path.resolve() in kept:
            continue
        try:
            send2trash(str(path))
            moved += 1
        except PermissionError:
            warnings.append(f"Permission denied — kept {path.name}")
        except OSError as exc:
            warnings.append(f"Could not move {path.name} to Recycle Bin / Trash: {exc}")
    return moved, warnings


def scan_album_folders(root: Path, log: Callable[[str], None]) -> list[AlbumFolder]:
    """One album per directory; tag-based details take precedence over directory name."""
    albums: list[AlbumFolder] = []
    for folder in sorted((path for path in root.rglob("*") if path.is_dir()), key=lambda p: str(p).lower()):
        audio_files = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS]
        if not audio_files:
            continue
        artist = album = ""
        for audio_path in audio_files[:5]:  # A few tracks are ample for imperfect collections.
            try:
                candidate_artist, candidate_album = read_album_tags(audio_path)
            except Exception as exc:
                log(f"Could not read tags in {audio_path.name}: {exc}")
                continue
            artist = artist or candidate_artist
            album = album or candidate_album
            if artist and album:
                break
        album = album or folder.name
        albums.append(AlbumFolder(folder, artist, album))
    return albums


def find_cover_art_archive(artist: str, album: str) -> Optional[bytes]:
    """Search MusicBrainz, then retrieve its official Cover Art Archive front image."""
    query_parts = [f'release:"{album.replace(chr(34), "")}"']
    if artist:
        query_parts.append(f'artist:"{artist.replace(chr(34), "")}"')
    query = " AND ".join(query_parts)
    url = "https://musicbrainz.org/ws/2/release/?" + urllib.parse.urlencode({"query": query, "fmt": "json", "limit": 5})
    data = request_json(url)
    releases = data.get("releases", []) if isinstance(data, dict) else []
    for release in releases:
        release_id = release.get("id")
        if not release_id:
            continue
        try:
            art = request_json(f"https://coverartarchive.org/release/{release_id}")
            for image in art.get("images", []):
                if image.get("front") and image.get("image"):
                    return request_bytes(image["image"])
        except Exception:
            continue
        finally:
            time.sleep(0.8)  # Respect MusicBrainz' public API rate limit.
    return None


def find_apple_music_artwork(artist: str, album: str) -> Optional[bytes]:
    """Fallback search on Apple's iTunes catalogue; requests the largest artwork URL."""
    term = " ".join(part for part in (artist, album) if part).strip()
    if not term:
        return None
    url = "https://itunes.apple.com/search?" + urllib.parse.urlencode({"term": term, "entity": "album", "limit": 10})
    data = request_json(url)
    results = data.get("results", []) if isinstance(data, dict) else []
    wanted = re.sub(r"\W+", "", album).lower()
    for result in results:
        collection = re.sub(r"\W+", "", str(result.get("collectionName", ""))).lower()
        artwork_url = result.get("artworkUrl100")
        if artwork_url and (not wanted or wanted in collection or collection in wanted):
            # Apple supports larger artwork by changing the size suffix.
            return request_bytes(re.sub(r"/\d+x\d+bb", "/1200x1200bb", artwork_url))
    return None


def find_google_images_artwork(artist: str, album: str, api_key: str, search_engine_id: str) -> Optional[bytes]:
    """Use the official Google Programmable Search API as the final fallback."""
    if not api_key or not search_engine_id:
        return None
    search_terms = f'"{artist}" "{album}" album cover' if artist else f'"{album}" album cover'
    url = "https://www.googleapis.com/customsearch/v1?" + urllib.parse.urlencode({
        "key": api_key,
        "cx": search_engine_id,
        "q": search_terms,
        "searchType": "image",
        "imgSize": "large",
        "num": 5,
        "safe": "active",
    })
    data = request_json(url)
    items = data.get("items", []) if isinstance(data, dict) else []
    for item in items:
        link = item.get("link")
        if not link:
            continue
        try:
            return request_bytes(link)
        except Exception:
            continue
    return None


def fetch_cover(artist: str, album: str, google_api_key: str = "", google_search_engine_id: str = "") -> tuple[Optional[bytes], str]:
    try:
        cover = find_cover_art_archive(artist, album)
        if cover:
            return cover, "Cover Art Archive / MusicBrainz"
    except Exception:
        pass
    try:
        cover = find_apple_music_artwork(artist, album)
        if cover:
            return cover, "Apple Music / iTunes"
    except Exception:
        pass
    try:
        cover = find_google_images_artwork(artist, album, google_api_key, google_search_engine_id)
        if cover:
            return cover, "Google Images (Programmable Search)"
    except Exception:
        pass
    return None, "No matching artwork found"


class AlbumCoverApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_NAME)
        self.minsize(760, 630)
        self.folder_var = tk.StringVar()
        self.overwrite_var = tk.BooleanVar(value=False)
        self.trash_images_var = tk.BooleanVar(value=False)
        self.google_key_var = tk.StringVar()
        self.google_cx_var = tk.StringVar()
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self._build_ui()
        self.after(100, self._consume_events)

    def _build_ui(self) -> None:
        shell = ttk.Frame(self, padding=18)
        shell.pack(fill="both", expand=True)
        ttk.Label(shell, text=APP_NAME, font=("TkDefaultFont", 18, "bold")).pack(anchor="w")
        ttk.Label(shell, text="Find trusted artwork for every album folder in your music library.").pack(anchor="w", pady=(2, 15))

        folder_row = ttk.Frame(shell)
        folder_row.pack(fill="x")
        ttk.Entry(folder_row, textvariable=self.folder_var).pack(side="left", fill="x", expand=True)
        ttk.Button(folder_row, text="Choose music folder…", command=self.choose_folder).pack(side="left", padx=(8, 0))
        ttk.Checkbutton(shell, text="Refresh covers already in album folders", variable=self.overwrite_var).pack(anchor="w", pady=(10, 3))
        ttk.Checkbutton(shell, text="After saving a cover, move other images in that album folder to Recycle Bin / Trash", variable=self.trash_images_var).pack(anchor="w", pady=(3, 8))

        google_box = ttk.LabelFrame(shell, text="Optional final fallback — Google Images", padding=10)
        google_box.pack(fill="x", pady=(0, 10))
        ttk.Label(google_box, text="Uses Google's official Programmable Search API only after the music sources fail. These details stay only in this session.").grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 6))
        ttk.Label(google_box, text="API key").grid(row=1, column=0, sticky="w")
        ttk.Entry(google_box, textvariable=self.google_key_var, show="•", width=28).grid(row=1, column=1, sticky="ew", padx=(6, 14))
        ttk.Label(google_box, text="Search engine ID").grid(row=1, column=2, sticky="w")
        ttk.Entry(google_box, textvariable=self.google_cx_var, width=28).grid(row=1, column=3, sticky="ew", padx=(6, 0))
        google_box.columnconfigure(1, weight=1)
        google_box.columnconfigure(3, weight=1)

        action_row = ttk.Frame(shell)
        action_row.pack(fill="x")
        self.start_button = ttk.Button(action_row, text="Find and save album covers", command=self.start)
        self.start_button.pack(side="left")
        self.progress = ttk.Progressbar(action_row, mode="determinate")
        self.progress.pack(side="left", fill="x", expand=True, padx=12)
        self.status_var = tk.StringVar(value="Choose the top-level folder containing your albums.")
        ttk.Label(shell, textvariable=self.status_var).pack(anchor="w", pady=(10, 4))

        self.log = tk.Text(shell, height=17, state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True)

    def choose_folder(self) -> None:
        selected = filedialog.askdirectory(title="Choose your music library folder")
        if selected:
            self.folder_var.set(selected)

    def append_log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def start(self) -> None:
        root = Path(self.folder_var.get()).expanduser()
        if not root.is_dir():
            messagebox.showerror(APP_NAME, "Please choose a valid music folder first.")
            return
        self.start_button.configure(state="disabled")
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        threading.Thread(
            target=self._worker,
            args=(root, self.overwrite_var.get(), self.trash_images_var.get(), self.google_key_var.get().strip(), self.google_cx_var.get().strip()),
            daemon=True,
        ).start()

    def _worker(self, root: Path, overwrite: bool, move_images_to_trash: bool, google_api_key: str, google_search_engine_id: str) -> None:
        self.events.put(("status", "Scanning album folders…"))
        albums = scan_album_folders(root, lambda message: self.events.put(("log", message)))
        self.events.put(("maximum", len(albums)))
        if not albums:
            self.events.put(("done", "No folders containing supported audio files were found."))
            return
        saved = skipped = missing = 0
        for number, item in enumerate(albums, start=1):
            target = item.folder / f"{safe_filename(item.album)}.jpg"
            self.events.put(("status", f"{number}/{len(albums)}: {item.artist or 'Unknown artist'} — {item.album}"))
            if target.exists() and not overwrite:
                skipped += 1
                self.events.put(("log", f"Skipped existing cover: {target.name}"))
            else:
                image, source = fetch_cover(item.artist, item.album, google_api_key, google_search_engine_id)
                if image:
                    try:
                        # The new source image must save first; failures leave existing
                        # artwork untouched.
                        target.write_bytes(image)
                    except PermissionError:
                        missing += 1
                        self.events.put(("log", f"Permission denied — could not save {target.name}. Allow this app access to the music folder, then try again."))
                        self.events.put(("progress", number))
                        continue
                    except OSError as exc:
                        missing += 1
                        self.events.put(("log", f"Could not save {target.name}: {exc}"))
                        self.events.put(("progress", number))
                        continue
                    saved += 1
                    self.events.put(("log", f"Saved: {target.name}  [{source}]"))
                    if move_images_to_trash:
                        moved, warnings = move_other_images_to_trash(item.folder, {target})
                        if moved:
                            self.events.put(("log", f"Moved {moved} other image(s) to Recycle Bin / Trash: {item.folder.name}"))
                        for warning in warnings:
                            self.events.put(("log", warning))
                else:
                    missing += 1
                    self.events.put(("log", f"No cover found: {item.artist or 'Unknown artist'} — {item.album}"))
            self.events.put(("progress", number))
        self.events.put(("done", f"Finished — saved {saved}, skipped {skipped}, not found {missing}."))

    def _consume_events(self) -> None:
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "log":
                    self.append_log(str(value))
                elif kind == "status":
                    self.status_var.set(str(value))
                elif kind == "maximum":
                    self.progress.configure(maximum=max(1, int(value)), value=0)
                elif kind == "progress":
                    self.progress.configure(value=int(value))
                elif kind == "done":
                    self.status_var.set(str(value))
                    self.start_button.configure(state="normal")
                    self.append_log(str(value))
        except queue.Empty:
            pass
        self.after(100, self._consume_events)


if __name__ == "__main__":
    AlbumCoverApp().mainloop()
