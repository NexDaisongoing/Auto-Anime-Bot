from os import path as ospath
from aiofiles import open as aiopen
from aiofiles.os import path as aiopath, remove as aioremove, mkdir
from aiohttp import ClientSession
from torrentp import TorrentDownloader
from time import time
from math import floor
from bot import LOGS
from bot.core.func_utils import handle_logs
import asyncio

# Utility function to format speed
def format_speed(speed):
    if speed < 1024:
        return f"{speed:.2f} KB/s"
    elif speed < 1024 * 1024:
        return f"{speed / 1024:.2f} MB/s"
    else:
        return f"{speed / (1024 * 1024):.2f} GB/s"

# Utility function to format bytes to a human-readable size
def convertBytes(size):
    if size < 1024:
        return f"{size:.2f} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.2f} KB"
    elif size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.2f} MB"
    else:
        return f"{size / (1024 * 1024 * 1024):.2f} GB"

# Utility function to convert time in seconds to HH:MM:SS format
def convertTime(seconds):
    mins, secs = divmod(seconds, 60)
    hours, mins = divmod(mins, 60)
    return f"{int(hours):02}:{int(mins):02}:{int(secs):02}"

class TorDownloader:
    def __init__(self, path="."):
        self.__downdir = path
        self.__torpath = "torrents/"
        self.prev_size = 0
        self.start_time = time()
        self.__name = ""  # Name of the file will be set when downloading

    @handle_logs
    async def download(self, torrent, name=None):
        self.__name = name  # Set file name when downloading
        self.start_time = time()  # Set the start time when the download begins
        if torrent.startswith("magnet:"):
            torp = TorrentDownloader(torrent, self.__downdir)
            await torp.start_download()
            return ospath.join(self.__downdir, name)
        elif torfile := await self.get_torfile(torrent):
            torp = TorrentDownloader(torfile, self.__downdir)
            await torp.start_download()
            await aioremove(torfile)
            return ospath.join(self.__downdir, torp._torrent_info._info.name())

    @handle_logs
    async def get_torfile(self, url):
        if not await aiopath.isdir(self.__torpath):
            await mkdir(self.__torpath)

        tor_name = url.split('/')[-1]
        des_dir = ospath.join(self.__torpath, tor_name)

        async with ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    async with aiopen(des_dir, 'wb') as file:
                        async for chunk in response.content.iter_any():
                            await file.write(chunk)
                    return des_dir
        return None

    # Progress update function to calculate speed and show detailed status
    async def progress_status(self, current, total):
        now = time()
        time_diff = now - self.start_time

        # Skip the calculation if no progress has been made yet
        if self.prev_size == 0:
            self.prev_size = current
            return

        # Calculate speed in KB/s
        speed = (current - self.prev_size) / time_diff / 1024  # KB/s
        formatted_speed = format_speed(speed)

        # Calculate time left and other metrics
        progress = (current / total) * 100
        eta = (total - current) / (speed * 1024)  # Time Left in seconds

        # Progress bar (8 blocks for 100%)
        bar = floor(progress / 8) * "█" + (12 - floor(progress / 8)) * "▒"

        # Create the progress message
        progress_str = f"""‣ <b>Anime Name :</b> <b><i>{self.__name}</i></b>

‣ <b>Status :</b> <i>Downloading</i>
    <code>[{bar}]</code> {progress:.2f}%
    
‣ <b>Size :</b> {convertBytes(current)} out of ~ {convertBytes(total)}
‣ <b>Speed :</b> {formatted_speed}
‣ <b>Time Took :</b> {convertTime(time_diff)}
‣ <b>Time Left :</b> {convertTime(eta)}

‣ <b>File(s) Downloaded:</b> <code>{current / total * 100:.2f}%</code>"""

        # Display progress (You can update this message in the UI here)
        print(progress_str)

        # Update previous size for next calculation
        self.prev_size = current
        self.start_time = now

        # Delay for 3 seconds before updating again
        await asyncio.sleep(3)  # Sleep for 3 seconds