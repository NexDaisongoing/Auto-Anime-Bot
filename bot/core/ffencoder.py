from re import findall 
from math import floor
from time import time
from os import path as ospath
from aiofiles import open as aiopen
from aiofiles.os import remove as aioremove, rename as aiorename
from shlex import split as ssplit
from asyncio import sleep as asleep, gather, create_subprocess_shell, create_task
from asyncio.subprocess import PIPE

from bot import Var, bot_loop, ffpids_cache, LOGS
from .func_utils import mediainfo, convertBytes, convertTime, sendMessage, editMessage
from .reporter import rep

ffargs = {
    '1080': Var.FFCODE_1080,
    '720': Var.FFCODE_720,
    '480': Var.FFCODE_480,
    '360': Var.FFCODE_360,
}

class FFEncoder:
    def __init__(self, message, path, name, qual):
        self.__proc = None
        self.is_cancelled = False
        self.message = message
        self.__name = name
        self.__qual = qual
        self.dl_path = path
        self.__total_time = None
        self.out_path = ospath.join("encode", name)
        self.__prog_file = 'prog.txt'
        self.__start_time = time()

    async def progress(self):
        self.__total_time = await mediainfo(self.dl_path, get_duration=True)
        if isinstance(self.__total_time, str):
            self.__total_time = 1.0

        last_logged_time = time()  # Track time of last log
        last_logged_percent = 0  # Track last logged percent
        stuck_counter = 0  # To detect if it's stuck at the same progress

        while not (self.__proc is None or self.is_cancelled):
            async with aiopen(self.__prog_file, 'r+') as p:
                text = await p.read()

            if text.strip():  # Check if progress data is available
                time_done = floor(int(t[-1]) / 1000000) if (t := findall("out_time_ms=(\d+)", text)) else 1
                ensize = int(s[-1]) if (s := findall(r"total_size=(\d+)", text)) else 0

                diff = time() - self.__start_time
                speed = ensize / diff
                percent = round((time_done/self.__total_time)*100, 2)

                # If percent has not changed for 3 cycles (24s), log stuck
                if percent == last_logged_percent:
                    stuck_counter += 1
                    if stuck_counter >= 3:
                        LOGS.warning(f"Stuck at {percent}% for more than {stuck_counter * 8}s")
                else:
                    stuck_counter = 0  # Reset counter if progress is happening

                last_logged_percent = percent

                tsize = ensize / (max(percent, 0.01)/100)
                eta = (tsize-ensize)/max(speed, 0.01)

                bar = floor(percent/8)*"█" + (12 - floor(percent/8))*"▒"

                progress_str = f"""<blockquote>‣ <b>Anime Name :</b> <b><i>{self.__name}</i></b></blockquote>
<blockquote>‣ <b>Status :</b> <i>Encoding</i>
    <code>[{bar}]</code> {percent}%</blockquote> 
<blockquote>   ‣ <b>Size :</b> {convertBytes(ensize)} out of ~ {convertBytes(tsize)}
    ‣ <b>Speed :</b> {convertBytes(speed)}/s
    ‣ <b>Time Took :</b> {convertTime(diff)}
    ‣ <b>Time Left :</b> {convertTime(eta)}</blockquote>
<blockquote>‣ <b>File(s) Encoded:</b> <code>{Var.QUALS.index(self.__qual)} / {len(Var.QUALS)}</code></blockquote>"""

                await editMessage(self.message, progress_str)

                if (prog := findall(r"progress=(\w+)", text)) and prog[-1] == 'end':
                    break

            # Log every 15 seconds for tracking progress
            if time() - last_logged_time > 15:
                LOGS.info(f"Current progress at {percent}% after {round(diff)} seconds")
                last_logged_time = time()

            await asleep(8)

    async def start_encode(self):
        if ospath.exists(self.__prog_file):
            await aioremove(self.__prog_file)

        async with aiopen(self.__prog_file, 'w+'):
            LOGS.info("Progress Temp Generated!")

        dl_npath, out_npath = ospath.join("encode", "ffanimeadvin.mkv"), ospath.join("encode", "ffanimeadvout.mkv")
        await aiorename(self.dl_path, dl_npath)

        ffcode = ffargs[self.__qual].format(dl_npath, self.__prog_file, out_npath)

        LOGS.info(f"FFmpeg command: {ffcode}")
        self.__proc = await create_subprocess_shell(ffcode, stdout=PIPE, stderr=PIPE)
        proc_pid = self.__proc.pid
        ffpids_cache.append(proc_pid)

        # Log the output of FFmpeg while encoding
        async def log_output(pipe, label):
            while True:
                line = await pipe.readline()
                if not line:
                    break
                LOGS.info(f"{label}: {line.decode().strip()}")

        # Create tasks to log stdout and stderr of FFmpeg
        stdout_task = create_task(log_output(self.__proc.stdout, "stdout"))
        stderr_task = create_task(log_output(self.__proc.stderr, "stderr"))

        _, return_code = await gather(self.__proc.wait(), stdout_task, stderr_task)
        ffpids_cache.remove(proc_pid)

        if return_code != 0:
            LOGS.error(f"FFmpeg failed with error code {return_code}")
        else:
            LOGS.info("Encoding finished successfully.")

        await aiorename(dl_npath, self.dl_path)
        if self.is_cancelled:
            return

        if return_code == 0 and ospath.exists(out_npath):
            await aiorename(out_npath, self.out_path)
            return self.out_path
        else:
            await rep.report((await self.__proc.stderr.read()).decode().strip(), "error")

    async def cancel_encode(self):
        self.is_cancelled = True
        if self.__proc is not None:
            try:
                self.__proc.kill()
            except Exception as e:
                LOGS.error(f"Error while canceling encoding: {e}")