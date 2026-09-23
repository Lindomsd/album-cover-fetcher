# Album Cover Fetcher

A small desktop app for Windows, macOS and Linux that fills a music library with album-cover JPGs.

Choose the top-level folder holding your albums, select **Find and save album covers**, and the app will:

1. find each folder that contains audio files;
2. read the album artist and album title from its audio metadata (using the folder name if an album tag is missing);
3. look for verified artwork first via **MusicBrainz + Cover Art Archive**;
4. use **Apple Music/iTunes** as a fallback;
5. optionally use **Google Images** via Google's official Programmable Search API as a final fallback; and
6. save the result in the matching album folder as **`Album Title.jpg`**.

It never changes or deletes audio files. Existing cover JPGs are left alone unless **Refresh covers already in album folders** is selected.

## Reliable sources

- [Cover Art Archive](https://coverartarchive.org/) / [MusicBrainz](https://musicbrainz.org/): community-curated, release-specific music metadata and cover art.
- [Apple Music / iTunes Search API](https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/index.html): catalogue artwork fallback.
- [Google Programmable Search JSON API](https://developers.google.com/custom-search/v1/overview): optional image-search fallback, used only when the sources above have no cover.

Artwork remains subject to the applicable rights of its owner. This tool is intended for personal music-library organisation.

## Install and run

Install [Python 3.10 or later](https://www.python.org/downloads/), then in this project folder run:

```bash
python -m pip install -r requirements.txt
python app.py
```

On Windows, if `python` is not recognised, use `py` instead.

## Enable Google Images fallback (optional)

The app does **not** scrape Google Images. Google blocks and changes that method regularly, and it would make the program fragile. Instead, it uses Google's supported **Programmable Search JSON API**.

1. Create an image-enabled [Programmable Search Engine](https://programmablesearchengine.google.com/), configured to search the entire web.
2. In Google Cloud, enable **Custom Search JSON API** and create an API key.
3. In the app, paste the API key and the Search Engine ID into the two optional fields.
4. Run the cover search. Google is tried only if MusicBrainz/Cover Art Archive and Apple Music/iTunes do not find an image.

The key and Search Engine ID are kept in the app only for the current session; they are not written into the project or your music folders. Google may charge after its API's free allowance, so check the current Google Cloud pricing before processing a large library.

## Updating covers later

Yes — run the program again whenever you want. It is safe to rerun:

- By default, existing `Album Title.jpg` files are skipped.
- To search again with the new Google fallback and replace existing covers, tick **Refresh covers already in album folders** before starting.
- You can rerun the tool after adding new albums; it scans only folders containing supported audio files.

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

The app sends only artist and album search terms to the public music catalogues. It does not upload your music files. Public services can occasionally have no matching artwork or rate-limit requests; these cases appear in the activity log and do not stop the rest of the library being processed.

## Licence

MIT — see [LICENSE](LICENSE).
