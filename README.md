# Album Cover Fetcher

A small desktop app for Windows, macOS and Linux that fills a music library with album-cover JPGs.

Choose the top-level folder holding your albums, select **Find and save album covers**, and the app will:

1. find each folder that contains audio files;
2. read the album artist and album title from its audio metadata (using the folder name if an album tag is missing);
3. look for verified artwork first via **MusicBrainz + Cover Art Archive**;
4. use **Apple Music/iTunes** as a fallback; and
5. save the result in the matching album folder as **`Album Title.jpg`**.

It never changes or deletes audio files. Existing cover JPGs are left alone unless **Replace existing JPG cover files** is selected.

## Reliable sources

- [Cover Art Archive](https://coverartarchive.org/) / [MusicBrainz](https://musicbrainz.org/): community-curated, release-specific music metadata and cover art.
- [Apple Music / iTunes Search API](https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/index.html): catalogue artwork fallback.

Artwork remains subject to the applicable rights of its owner. This tool is intended for personal music-library organisation.

## Install and run

Install [Python 3.10 or later](https://www.python.org/downloads/), then in this project folder run:

```bash
python -m pip install -r requirements.txt
python app.py
```

On Windows, if `python` is not recognised, use `py` instead.

## How folder matching works

A folder counts as an album when it contains supported audio files: MP3, FLAC, M4A/MP4, OGG/OPUS, AAC, WMA, WAV or AIFF. The app scans subfolders too.

For best results, ensure a track in each album folder has `Album` and `Album Artist` (or `Artist`) metadata. The app can still search by folder name when the album tag is missing.

## Optional: build a standalone Windows app

```bash
python -m pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed --name AlbumCoverFetcher app.py
```

The executable will be created in the `dist` folder.

## Limits and privacy

The app sends only the artist and album search terms to the public music catalogues. It does not upload your music files. Public services can occasionally have no matching artwork or rate-limit requests; these cases appear in the activity log and do not stop the rest of the library being processed.

## Licence

MIT — see [LICENSE](LICENSE).
