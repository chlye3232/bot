# bot_multi_final.py
import asyncio
import json
import discord
import yt_dlp as youtube_dl
from typing import Optional
import shutil, subprocess, os

# ====== 필수 설정 ======
TOKEN1 = "MTQzMjk2NTI4NDc3MTM5Nzc2NQ.Gk1kSp.thbndv4UOGdFBjZmjFKI7WtR1bXV6qSfSJNv7M"  # 메인 봇 토큰 (우선 배정)
TOKEN2 = "MTQzMzA5MTQ4MTU4NDc5NTcxMA.GY9MOe.oQ5j6lDWXlsmOVMISa2CwLtMfGTPrj_97HPJys"  # 서브 봇 1
TOKEN3 = "MTQzMzA5Mjg4NzYyODc0MjczOA.GHTwiW.VCWmPHnKSUrpPO-NEk2hM6_YfjukRXz1d6-Ieo"  # 서브 봇 2

GUILD_ID = 1427122992915288167  # << 여기에 고정 서버 ID 입력 (정수)
TCP_PORT = 8766
YOUTUBE_URL_DEFAULT = "https://www.youtube.com/watch?v=tsXsC97YJcI"
KEEPALIVE_SEC = 300  # 5분
# ======================

# yt_dlp / ffmpeg 설정
youtube_dl.utils.bug_reports_message = lambda: ''
ytdl_format_options = {
    "format": "bestaudio/best",
    "outtmpl": "%(extractor)s-%(id)s-%(title)s.%(ext)s",
    "restrictfilenames": True,
    "noplaylist": True,
    "nocheckcertificate": True,
    "ignoreerrors": False,
    "logtostderr": False,
    "quiet": True,
    "no_warnings": True,
    "default_search": "auto",
    "source_address": "0.0.0.0",
}
ffmpeg_options = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}
ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get("title")
        self.url = data.get("url")

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        if "entries" in data:
            data = data["entries"][0]
        filename = data["url"] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

# 최소 인텐트(게이트웨이 4014 방지)
intents = discord.Intents.none()
intents.guilds = True
intents.voice_states = True

class ManagedBot:
    def __init__(self, name: str, token: str, priority: int):
        self.name = name
        self.token = token
        self.priority = priority
        self.client = discord.Client(intents=intents)
        self.ready_evt = asyncio.Event()
        self.keepalive_task: Optional[asyncio.Task] = None

        @self.client.event
        async def on_ready():
            print(f"[{self.name}] READY: {self.client.user}")
            await self.client.change_presence(status=discord.Status.online)
            if self.keepalive_task is None:
                self.keepalive_task = asyncio.create_task(self._keepalive())
            self.ready_evt.set()

    async def _keepalive(self):
        try:
            while True:
                await self.client.change_presence(status=discord.Status.online)
                await asyncio.sleep(KEEPALIVE_SEC)
        except asyncio.CancelledError:
            pass

    def is_busy(self) -> bool:
        return any(vc.is_connected() for vc in self.client.voice_clients)

    def _find_vc_in_guild(self, guild: discord.Guild):
        return discord.utils.get(self.client.voice_clients, guild=guild)

    async def play_in_channel(self, channel_id: int, youtube_url: Optional[str] = None):
        youtube_url = youtube_url or YOUTUBE_URL_DEFAULT
        guild = self.client.get_guild(int(GUILD_ID))
        if not guild:
            return {"status": "error", "message": f"[{self.name}] 길드({GUILD_ID}) 미참여"}

        channel = guild.get_channel(int(channel_id))
        if not channel or not isinstance(channel, discord.VoiceChannel):
            return {"status": "error", "message": f"[{self.name}] 채널({channel_id}) 없음/음성 아님"}

        voice_client = self._find_vc_in_guild(guild)
        if voice_client and voice_client.is_connected():
            await voice_client.move_to(channel)
        else:
            voice_client = await channel.connect()

        try:
            player = await YTDLSource.from_url(youtube_url, loop=asyncio.get_event_loop(), stream=True)
            if voice_client.is_playing():
                voice_client.stop()

            def after_playing(error):
                if error:
                    print(f"[{self.name}] Player error: {error}")
                coro = voice_client.disconnect()
                fut = asyncio.run_coroutine_threadsafe(coro, self.client.loop)
                try:
                    fut.result()
                except Exception as e:
                    print(f"[{self.name}] 퇴장 오류: {e}")

            voice_client.play(player, after=after_playing)
            print(f"[{self.name}] PLAY: {player.title} -> #{channel.name}")
            return {"status": "success", "bot": self.name, "channel_id": channel_id, "message": f"재생 중: {player.title}"}
        except Exception as e:
            return {"status": "error", "message": f"[{self.name}] 재생 오류: {e}"}

    async def stop_in_channel(self, channel_id: int):
        guild = self.client.get_guild(int(GUILD_ID))
        if not guild:
            return {"status": "error", "message": f"[{self.name}] 길드({GUILD_ID}) 미참여"}
        channel = guild.get_channel(int(channel_id))
        if not channel or not isinstance(channel, discord.VoiceChannel):
            return {"status": "error", "message": f"[{self.name}] 채널({channel_id}) 없음/음성 아님"}

        vc = self._find_vc_in_guild(guild)
        if vc and vc.is_connected():
            if vc.is_playing():
                vc.stop()
            await vc.disconnect()
            print(f"[{self.name}] STOP: #{channel.name}")
            return {"status": "success", "bot": self.name, "message": "퇴장 완료"}
        return {"status": "error", "message": f"[{self.name}] 연결 아님"}

    async def stop_all(self):
        any_done = False
        for vc in list(self.client.voice_clients):
            try:
                if vc.is_playing(): vc.stop()
                await vc.disconnect()
                any_done = True
            except Exception as e:
                print(f"[{self.name}] stop_all 오류: {e}")
        return {"status": "success", "bot": self.name, "message": "모든 연결 해제" if any_done else "연결 없음"}

class BotManager:
    def __init__(self):
        self.bots = [
            ManagedBot("Bot1", TOKEN1, priority=0),
            ManagedBot("Bot2", TOKEN2, priority=1),
            ManagedBot("Bot3", TOKEN3, priority=2),
        ]
        self.assign_lock = asyncio.Lock()  # 동시 play 분배 보호

    async def start_all(self):
        tasks = []
        for bot in self.bots:
            if bot.token:
                tasks.append(asyncio.create_task(bot.client.start(bot.token)))
        # READY 이벤트 기다리되, 한 봇이 지연돼도 전체 진행
        waiters = [asyncio.wait_for(bot.ready_evt.wait(), timeout=20) for bot in self.bots if bot.token]
        if waiters:
            try:
                await asyncio.gather(*waiters)
            except Exception:
                pass
        print("[Manager] 봇 준비 완료(또는 일부 타임아웃).")
        return tasks

    def pick_available_bot(self) -> Optional[ManagedBot]:
        for bot in sorted(self.bots, key=lambda b: b.priority):
            if bot.token and (not bot.is_busy()):
                return bot
        return None

    async def route_play(self, channel_id: int, youtube_url: Optional[str] = None):
        async with self.assign_lock:
            bot = self.pick_available_bot()
            if bot is None:
                return {"status": "error", "message": "모든 봇이 바쁨"}
            return await bot.play_in_channel(channel_id, youtube_url)

    async def route_stop(self, channel_id: int):
        for bot in self.bots:
            if not bot.token: continue
            guild = bot.client.get_guild(int(GUILD_ID))
            if not guild: continue
            channel = guild.get_channel(int(channel_id))
            if not isinstance(channel, discord.VoiceChannel): continue
            vc = discord.utils.get(bot.client.voice_clients, guild=guild)
            if vc and vc.is_connected():
                return await bot.stop_in_channel(channel_id)
        return {"status": "error", "message": "해당 채널에 연결된 봇 없음"}

    async def route_stop_all(self):
        results = []
        for bot in self.bots:
            if not bot.token: continue
            results.append(await bot.stop_all())
        return {"status": "success", "results": results}

manager = BotManager()

# ==== 단일 asyncio TCP 서버 ====
# 요청(JSON):
#   {"command":"play", "channel_id":123, "youtube_url":"..."}  # youtube_url은 선택
#   {"command":"stop", "channel_id":123}
#   {"command":"stop_all"}
async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    try:
        data = await reader.read(4096)
        if not data:
            writer.close()
            await writer.wait_closed()
            return
        try:
            req = json.loads(data.decode("utf-8"))
        except Exception:
            writer.write(json.dumps({"status": "error", "message": "잘못된 JSON/인코딩"}).encode("utf-8"))
            await writer.drain()
            writer.close()
            await writer.wait_closed()
            return

        cmd = (req.get("command") or "").lower()
        channel_id = req.get("channel_id")
        youtube_url = req.get("youtube_url")

        if cmd == "play":
            if not channel_id:
                resp = {"status": "error", "message": "channel_id 필요"}
            else:
                resp = await manager.route_play(int(channel_id), youtube_url)
        elif cmd == "stop":
            if not channel_id:
                resp = {"status": "error", "message": "channel_id 필요"}
            else:
                resp = await manager.route_stop(int(channel_id))
        elif cmd == "stop_all":
            resp = await manager.route_stop_all()
        else:
            resp = {"status": "error", "message": f"알 수 없는 명령: {cmd}"}

        writer.write(json.dumps(resp).encode("utf-8"))
        await writer.drain()
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except:
            pass



def _preflight_audio(ffmpeg_path: str | None = None, opus_path: str | None = None):
    # 1) ffmpeg 경로 확인
    ff = ffmpeg_path or shutil.which("ffmpeg")
    print("[CHECK] ffmpeg:", ff or "NOT FOUND")
    if not ff:
        print("       -> ffmpeg 설치/경로 지정 필요 (Windows: C:\\ffmpeg\\bin\\ffmpeg.exe)")
    else:
        try:
            out = subprocess.run([ff, "-version"], capture_output=True, text=True, timeout=5)
            print("[CHECK] ffmpeg version head:", (out.stdout or out.stderr).splitlines()[0][:120])
        except Exception as e:
            print("[CHECK] ffmpeg 실행 실패:", e)

    # 2) PyNaCl
    try:
        import nacl  # noqa
        print("[CHECK] PyNaCl: OK")
    except Exception as e:
        print("[CHECK] PyNaCl: MISSING -> pip install -U 'discord.py[voice]' PyNaCl", e)

    # 3) Opus (discord 음성 인코딩)
    import discord as _d
    if not _d.opus.is_loaded():
        try:
            if opus_path:
                _d.opus.load_opus(opus_path)
                print("[CHECK] Opus: loaded via path:", opus_path)
            else:
                _d.opus.load_opus('opus')  # 시스템 라이브러리
                print("[CHECK] Opus: loaded via 'opus'")
        except Exception as e:
            print("[CHECK] Opus: NOT LOADED -> Windows: opus.dll PATH에 두기 / Linux: libopus", e)
    else:
        print("[CHECK] Opus: already loaded")

# 필요시 절대경로 지정(없으면 None)
FFMPEG_ABS = None          # 예) r"C:\ffmpeg\bin\ffmpeg.exe"
OPUS_DLL_ABS = None        # 예) r"C:\path\to\opus.dll"


async def main():
    await manager.start_all()
    server = await asyncio.start_server(handle_client, host="0.0.0.0", port=TCP_PORT)
    addrs = ", ".join(str(sock.getsockname()) for sock in server.sockets)
    print(f"[TCP] 서버 시작: {addrs}")
    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    _preflight_audio(FFMPEG_ABS, OPUS_DLL_ABS)
    try:
        # Windows에서 이벤트 루프 정책 충돌 방지
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        except Exception:
            pass
        asyncio.run(main())
    except KeyboardInterrupt:
        print("종료됨.")
