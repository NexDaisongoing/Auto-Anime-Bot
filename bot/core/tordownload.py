from os import path as ospath
from aiofiles import open as aiopen
from aiofiles.os import path as aiopath, remove as aioremove, mkdir
from aiohttp import ClientSession
from torrentp import TorrentDownloader
from time import time
from asyncio import sleep as asleep, create_task
from bot import Var
from bot.core.func_utils import handle_logs, convertBytes, convertTime, editMessage

class TorDownloader:
    def __init__(self, path="."):
        self.__downdir = path
        self.__torpath = "torrents/"

    @handle_logs
    async def download(self, torrent, name, stat_msg=None):
        start_time = time()
        last_check = start_time
        last_size = 0

        if torrent.startswith("magnet:"):
            torp = TorrentDownloader(torrent, self.__downdir)
        elif torfile := await self.get_torfile(torrent):
            torp = TorrentDownloader(torfile, self.__downdir)
        else:
            return None

        download_path = ospath.join(self.__downdir, name)

        async def progress_updater():
            nonlocal last_check, last_size
            while not torp.done:
                await asleep(3)
                if not ospath.exists(download_path):
                    continue
                try:
                    current_size = ospath.getsize(download_path)
                except:
                    continue
                now = time()
                speed = (current_size - last_size) / (now - last_check + 1e-6)
                percent = (current_size / torp.total_size) * 100 if torp.total_size else 0
                eta = (torp.total_size - current_size) / (speed + 1e-6)
                bar = "".join(["■" if i < percent // 5 else "□" for i in range(20)])

                progress_str = f"""‣ <b>Anime Name :</b> <b><i>{name}</i></b>

‣ <b>Status :</b> <i>Downloading</i>
    <code>[{bar}]</code> {percent:.2f}%
    
    ‣ <b>Size :</b> {convertBytes(current_size)} out of ~ {convertBytes(torp.total_size)}
    ‣ <b>Speed :</b> {convertBytes(speed)}/s
    ‣ <b>Time Took :</b> {convertTime(now - start_time)}
    ‣ <b>Time Left :</b> {convertTime(eta)}

‣ <b>File(s) Encoded:</b> <code>0 / {len(Var.QUALS)}</code>"""

                if stat_msg:
                    await editMessage(stat_msg, progress_str)
                last_size = current_size
                last_check = now

        task = create_task(progress_updater())
        await torp.start_download()
        task.cancel()

        if not torrent.startswith("magnet:"):
            await aioremove(torfile)
        return download_path

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