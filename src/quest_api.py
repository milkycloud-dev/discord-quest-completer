import threading
import json
import re
import requests
import os

API_ENDPOINT = "https://discord.com/api/v9/applications/detectable"
CACHE_SCHEMA = 2


def build_list(raw):
    """
    Converts the raw Discord detectable-applications response into the app's game list.
    Entries without any known executable (unreleased games) are kept with a generated name.
    """
    games = []
    for entry in raw:
        executables = entry.get('executables', [])
        exe_list = [e['name'] for e in executables if e.get('os') == 'win32' and e.get('name')]
        if not exe_list:
            exe_list = [e['name'] for e in executables if e.get('name')]
        title = entry.get('name', 'Unknown App')
        no_exe = not exe_list
        if no_exe:
            exe_list = [(re.sub(r'[^a-z0-9]+', '', title.lower()) or 'game') + '.exe']

        game_id = entry.get('id')
        icon_hash = entry.get('icon_hash')
        icon_url = None
        if icon_hash:
            icon_url = f"https://cdn.discordapp.com/app-icons/{game_id}/{icon_hash}.png?size=64"

        aliases = [a for a in entry.get('aliases', []) if a]
        games.append({
            "title": title,
            "id": game_id,
            "exes": exe_list,
            "icon_url": icon_url,
            "aliases": aliases,
            "no_exe": no_exe,
            "search": " ".join([title] + aliases).lower()
        })
    return games


class DiscordAPIWorker:
    """
    Worker class responsible for loading the detectable games database.
    The processed list is cached on disk and shown immediately; the network
    refresh runs afterwards and only replaces the list when the data changed.
    """
    def __init__(self, on_data, on_status):
        self.on_data = on_data
        self.on_status = on_status
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.save_dir = os.path.join(base_dir, "cache")
        self.save_file = os.path.join(self.save_dir, "detectable.json")
        self.games_file = os.path.join(self.save_dir, "games.json")

        if not os.path.exists(self.save_dir):
            try:
                os.makedirs(self.save_dir)
            except:
                pass

    def start(self):
        thread = threading.Thread(target=self.run)
        thread.daemon = True
        thread.start()

    def run(self):
        cached = self.read_games()
        etag = None
        if cached:
            etag = cached.get('etag')
            self.on_status(f"Loaded {len(cached['games'])} games from cache. Checking for updates...")
            self.on_data(cached['games'])
        else:
            self.on_status("Connecting to Discord API...")

        headers = {'If-None-Match': etag} if etag else {}
        try:
            r = requests.get(API_ENDPOINT, headers=headers, timeout=30)
        except Exception:
            r = None

        if r is not None and r.status_code == 304:
            self.on_status(f"Up to date: {len(cached['games'])} games.")
            return

        if r is not None and r.status_code == 200:
            try:
                games = build_list(r.json())
            except Exception:
                games = None
            if games:
                self.write_games(games, r.headers.get('ETag'))
                self.on_data(games)
                return

        if cached:
            self.on_status("Update check failed. Using cached list.")
            return

        self.on_status("Connection failed. Using offline cache mode.")
        raw = self.read_local()
        if not raw:
            self.on_status("No data available to show.")
            self.on_data([])
            return
        self.on_data(build_list(raw))

    def read_games(self):
        try:
            with open(self.games_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if data.get('schema') == CACHE_SCHEMA and data.get('games'):
                return data
        except:
            pass
        return None

    def write_games(self, games, etag):
        tmp = self.games_file + ".tmp"
        try:
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump({"schema": CACHE_SCHEMA, "etag": etag, "games": games}, f, ensure_ascii=False)
            os.replace(tmp, self.games_file)
        except:
            pass

    def read_local(self):
        if os.path.exists(self.save_file):
            try:
                with open(self.save_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return None
