
# --- Koyeb health check server (HTTP) ---
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

def _start_health_server():
    try:
        port = int(os.getenv("PORT", "8000"))
        class _Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/healthz":
                    self.send_response(200); self.end_headers(); self.wfile.write(b"ok")
                else:
                    self.send_response(404); self.end_headers()
            def log_message(self, *args):
                return
        srv = HTTPServer(("0.0.0.0", port), _Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
    except Exception:
        pass

_start_health_server()
# --- end health check block ---

Token = os.getenv('DISCORD_TOKEN')
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

import asyncio
import json
import threading
import socket
import discord
import yt_dlp as youtube_dl
import os



# Suppress noise about console usage from errors
youtube_dl.utils.bug_reports_message = lambda: ''

# 고정된 서버 ID와 채널 ID, URL
GUILD_ID = 1427122992915288167  # 여기에 실제 디스코드 서버 ID 입력
CHANNEL_ID = 1432966432970244179  # 여기에 실제 음성 채널 ID 입력
YOUTUBE_URL = "https://www.youtube.com/watch?v=tsXsC97YJcI"  # 재생할 고정 URL

# TCP 서버 포트
TCP_PORT = 8766

ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',  # bind to ipv4 since ipv6 addresses cause issues sometimes
}

ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)

        self.data = data

        self.title = data.get('title')
        self.url = data.get('url')

# bot.py 파일에서 YTDLSource 클래스 내부의 from_url 메서드를 다음과 같이 수정하세요.

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        
        # 새로운 헬퍼 함수 정의
        def extract_data():
            # ytdl.extract_info 호출 시 download=True 옵션이 없으면 yt-dlp가
            # 임시 파일을 만들지 않고 스트림 URL만 가져옵니다. (stream=True인 경우)
            return ytdl.extract_info(url, download=not stream)

        # lambda 대신 헬퍼 함수를 executor에서 실행
        data = await loop.run_in_executor(None, extract_data)
        
        if 'entries' in data:
            # take first item from a playlist
            data = data['entries'][0]

        # FFMPEG_EXECUTABLE 인자를 명시적으로 추가하여 경로 문제도 예방 (선택적)
        FFMPEG_EXECUTABLE = "ffmpeg"  # FFmpeg의 경로가 PATH에 설정되어 있다면 "ffmpeg" 유지
        # FFMPEG_EXECUTABLE = "C:/path/to/ffmpeg/bin/ffmpeg.exe" # 경로가 확실치 않다면 이렇게 지정

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        
        # discord.FFmpegPCMAudio 호출 시 executable 인자를 추가
        return cls(discord.FFmpegPCMAudio(filename, executable=FFMPEG_EXECUTABLE, **ffmpeg_options), data=data)

# 인텐트 설정
intents = discord.Intents.default()
intents.message_content = True

# 클라이언트(봇) 생성
bot = discord.Client(intents=intents)

# 고정된 URL로 음악 재생 함수
async def play_music():
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        print(f"길드(서버) ID {GUILD_ID}를 찾을 수 없습니다.")
        return {"status": "error", "message": "서버를 찾을 수 없습니다."}
    
    voice_channel = guild.get_channel(CHANNEL_ID)
    if not voice_channel:
        print(f"음성 채널 ID {CHANNEL_ID}를 찾을 수 없습니다.")
        return {"status": "error", "message": "음성 채널을 찾을 수 없습니다."}
    
    # 채널에 연결
    voice_client = discord.utils.get(bot.voice_clients, guild=guild)
    if voice_client and voice_client.is_connected():
        await voice_client.move_to(voice_channel)
    else:
        voice_client = await voice_channel.connect()
    
    # URL에서 음악 재생
    try:
        player = await YTDLSource.from_url(YOUTUBE_URL, loop=bot.loop, stream=True)
        if voice_client.is_playing():
            voice_client.stop()
        
        # 재생이 끝난 후 호출될 콜백 함수 정의
        def after_playing(error):
            if error:
                print(f'Player error: {error}')
            
            # 비동기 함수를 호출하기 위해 코루틴을 만들고 실행
            coro = voice_client.disconnect()
            # future를 만들어서 코루틴 실행
            fut = asyncio.run_coroutine_threadsafe(coro, bot.loop)
            try:
                fut.result()
                print("재생이 끝나서 음성 채널에서 나갔습니다.")
            except:
                # 에러 처리
                print("음성 채널에서 나가는 중 오류가 발생했습니다.")
        
        voice_client.play(player, after=after_playing)
        print(f'Now playing: {player.title} in channel: {voice_channel.name}')
        return {"status": "success", "message": f"재생 중: {player.title}"}
    except Exception as e:
        print(f"음악 재생 중 오류 발생: {e}")
        return {"status": "error", "message": f"음악 재생 중 오류 발생: {e}"}

# 음악 재생 중지 함수
async def stop_music():
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return {"status": "error", "message": "서버를 찾을 수 없습니다."}
    
    voice_client = discord.utils.get(bot.voice_clients, guild=guild)
    if voice_client and voice_client.is_connected():
        if voice_client.is_playing():
            voice_client.stop()
        await voice_client.disconnect()
        return {"status": "success", "message": "재생을 중지하고 음성 채널에서 나갔습니다."}
    else:
        return {"status": "error", "message": "봇이 음성 채널에 연결되어 있지 않습니다."}

# TCP 소켓 서버 핸들러 - 커널 클라이언트용
def tcp_server_thread():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind(('0.0.0.0', TCP_PORT))  # 모든 인터페이스에서 수신
        server_socket.listen(5)
        
        print(f"TCP 서버가 포트 {TCP_PORT}에서 실행 중입니다.")
        
        while True:
            try:
                client_socket, addr = server_socket.accept()
                print(f"TCP 클라이언트 연결됨: {addr}")
                
                # 클라이언트 핸들러 스레드 시작
                client_thread = threading.Thread(
                    target=handle_tcp_client,
                    args=(client_socket, addr),
                    daemon=True
                )
                client_thread.start()
            except Exception as e:
                print(f"TCP 연결 수락 중 오류 발생: {e}")

# TCP 클라이언트 핸들러
def handle_tcp_client(client_socket, addr):
    try:
        # 클라이언트로부터 데이터 수신 (최대 1024 바이트)
        data = client_socket.recv(1024)
        if data:
            try:
                # 데이터 디코딩 및 JSON 파싱 시도
                decoded_data = data.decode('utf-8')
                print(f"TCP 클라이언트로부터 받은 데이터: {decoded_data}")
                
                try:
                    json_data = json.loads(decoded_data)
                    command = json_data.get("command")
                    
                    if command == "play":
                        print("TCP 클라이언트가 재생 명령을 보냈습니다.")
                        
                        # 비동기 함수를 실행하기 위한 future 생성
                        future = asyncio.run_coroutine_threadsafe(
                            play_music(), bot.loop
                        )
                        
                        # future 결과 기다리기 (최대 10초)
                        try:
                            result = future.result(timeout=10)
                            response = json.dumps(result).encode('utf-8')
                        except Exception as e:
                            print(f"play_music 실행 중 오류: {e}")
                            response = json.dumps({
                                "status": "error",
                                "message": f"명령 처리 중 오류 발생: {str(e)}"
                            }).encode('utf-8')
                    
                    elif command == "stop":
                        print("TCP 클라이언트가 중지 명령을 보냈습니다.")
                        
                        future = asyncio.run_coroutine_threadsafe(
                            stop_music(), bot.loop
                        )
                        
                        try:
                            result = future.result(timeout=10)
                            response = json.dumps(result).encode('utf-8')
                        except Exception as e:
                            print(f"stop_music 실행 중 오류: {e}")
                            response = json.dumps({
                                "status": "error",
                                "message": f"명령 처리 중 오류 발생: {str(e)}"
                            }).encode('utf-8')
                    
                    else:
                        response = json.dumps({
                            "status": "error",
                            "message": f"알 수 없는 명령어: {command}"
                        }).encode('utf-8')
                
                except json.JSONDecodeError:
                    print("잘못된 JSON 형식입니다.")
                    response = json.dumps({
                        "status": "error",
                        "message": "잘못된 JSON 형식입니다."
                    }).encode('utf-8')
            
            except UnicodeDecodeError:
                print("데이터 디코딩 중 오류가 발생했습니다.")
                response = json.dumps({
                    "status": "error",
                    "message": "데이터 디코딩 중 오류가 발생했습니다."
                }).encode('utf-8')
            
            # 응답 전송
            try:
                client_socket.sendall(response)
                print(f"TCP 클라이언트에게 응답 전송: {response.decode('utf-8')}")
            except Exception as e:
                print(f"응답 전송 중 오류 발생: {e}")
    
    except Exception as e:
        print(f"TCP 클라이언트 처리 중 오류 발생: {e}")
    
    finally:
        # 연결 종료
        try:
            client_socket.close()
            print(f"TCP 클라이언트 연결 종료됨: {addr}")
        except:
            pass

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    print('디스코드 봇이 온라인 상태가 되었습니다.')
    print(f'서버 ID: {GUILD_ID}, 채널 ID: {CHANNEL_ID}에서 음악을 재생합니다.')
    print(f'재생할 URL: {YOUTUBE_URL}')
    print('------')

# 메인 함수: 디스코드 봇과 TCP 서버를 동시에 실행
async def main():
    # TCP 서버 스레드 시작
    tcp_thread = threading.Thread(target=tcp_server_thread, daemon=True)
    tcp_thread.start()
    
    print(f"TCP 서버가 포트 {TCP_PORT}에서 시작되었습니다. 클라이언트의 연결을 기다립니다...")
    
    # 디스코드 봇 실행
    await bot.start(Token)

# 프로그램 실행
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("프로그램이 종료되었습니다.")
