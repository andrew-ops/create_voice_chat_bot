# -*- coding: utf-8 -*-

# 필요한 라이브러리들을 임포트합니다.
import os
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
import discord
from discord.ext import commands, tasks
from discord import app_commands, ui, ButtonStyle, Embed

# --- 환경 변수 및 초기 설정 ---

# .env 파일에서 환경 변수를 로드합니다.
# 봇 토큰, 어드민 ID 등 민감한 정보를 코드에서 분리합니다.
load_dotenv('token.env')
load_dotenv('admin_id.env')

# 어드민 ID를 .env 파일에서 불러와 리스트로 변환합니다.
# 쉼표로 구분된 여러 ID를 처리할 수 있습니다.
ADMIN_IDS_STR = os.getenv('ADMIN_IDS')
ADMIN_IDS = [int(admin_id.strip()) for admin_id in ADMIN_IDS_STR.split(',')] if ADMIN_IDS_STR else []

# 디스코드 봇이 필요로 하는 권한(인텐트)을 설정합니다.
# guilds: 서버 정보 접근
# voice_states: 음성 상태(채널 입장/퇴장 등) 접근
intents = discord.Intents.default()
intents.guilds = True
intents.voice_states = True

# 봇의 기본 설정을 구성합니다. 명령어 접두사는 '!'로 설정합니다.
bot = commands.Bot(command_prefix='!', intents=intents)

# --- 이벤트 핸들러 ---

@bot.event
async def on_ready():
    """봇이 성공적으로 디스코드에 로그인했을 때 실행되는 이벤트입니다."""
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    try:
        # 슬래시 커맨드를 서버와 동기화합니다.
        synced = await bot.tree.sync()
        print(f'Synced {len(synced)} commands.')
    except Exception as e:
        print(f'Error syncing commands: {e}')

# --- JSON 데이터 관리 함수 ---

# 생성된 음성 채널 정보를 저장할 파일 이름
CHANNELS_FILE = 'created_channels.json'
# 봇 사용이 허용된 텍스트 채널 정보를 저장할 파일 이름
ALLOWED_CHANNELS_FILE = 'allowed_channels.json'

def load_json(filename):
    """지정된 JSON 파일을 읽어 데이터를 반환합니다."""
    # 파일이 없으면 빈 리스트를 담은 새 파일을 생성합니다.
    if not os.path.exists(filename):
        with open(filename, 'w') as f:
            json.dump([], f)
        return []
    try:
        # 파일이 존재하면 데이터를 읽어 반환합니다.
        with open(filename, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        # 파일 내용이 비어있거나 JSON 형식이 아닐 경우 빈 리스트를 반환합니다.
        return []

def save_json(data, filename):
    """주어진 데이터를 지정된 JSON 파일에 저장합니다."""
    with open(filename, 'w') as f:
        # indent=4 옵션으로 가독성 좋게 저장합니다.
        json.dump(data, f, indent=4)

# --- UI 컴포넌트 (버튼) 클래스 ---

class ConfirmView(ui.View):
    """채널 삭제 확인/취소 버튼을 표시하는 View 클래스입니다."""
    def __init__(self, voice_channel: discord.VoiceChannel):
        super().__init__(timeout=60)  # 60초 후 버튼 비활성화
        self.voice_channel = voice_channel

    async def remove_channel_from_json(self):
        """JSON 파일에서 해당 음성 채널 정보를 삭제합니다."""
        channels_data = load_json(CHANNELS_FILE)
        # 삭제할 채널 ID를 제외한 나머지 채널 정보만 다시 저장합니다.
        updated_data = [d for d in channels_data if d.get('channel_id') != self.voice_channel.id]
        save_json(updated_data, CHANNELS_FILE)

    @ui.button(label='확인', style=ButtonStyle.red)
    async def confirm(self, interaction: discord.Interaction, button: ui.Button):
        """'확인' 버튼 클릭 시 실행됩니다."""
        channel_name = self.voice_channel.name
        await self.remove_channel_from_json() # JSON에서 채널 정보 제거
        await self.voice_channel.delete(reason=f'{interaction.user}의 요청으로 삭제') # 채널 삭제
        self.clear_items() # 모든 버튼 제거
        # 메시지를 수정하여 채널이 삭제되었음을 알립니다.
        await interaction.response.edit_message(content=f'🗑️ **{channel_name}** 채널이 삭제되었습니다.', embed=None, view=self)

    @ui.button(label='취소', style=ButtonStyle.grey)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        """'취소' 버튼 클릭 시 실행됩니다."""
        # 이전의 관리 View(채널 삭제 버튼만 있는)로 메시지를 되돌립니다.
        # creator_id를 다시 전달하여 권한 확인을 유지합니다.
        view = ManagementView(voice_channel=self.voice_channel, creator_id=interaction.user.id)
        await interaction.response.edit_message(view=view)


class ManagementView(ui.View):
    """채널 관리(삭제) 버튼을 표시하는 View 클래스입니다."""
    def __init__(self, voice_channel: discord.VoiceChannel, creator_id: int):
        super().__init__(timeout=None)  # 타임아웃을 설정하지 않아 버튼이 계속 활성화됩니다.
        self.voice_channel = voice_channel
        self.creator_id = creator_id # 채널 생성자의 ID를 저장합니다.

    @ui.button(label='채널 삭제', style=ButtonStyle.danger)
    async def delete_channel(self, interaction: discord.Interaction, button: ui.Button):
        """'채널 삭제' 버튼 클릭 시 실행됩니다."""
        # 버튼을 누른 사용자가 채널 생성자인지 확인합니다.
        if interaction.user.id != self.creator_id:
            await interaction.response.send_message("❌ 채널을 생성한 유저만 삭제할 수 있습니다.", ephemeral=True)
            return
        
        # 확인/취소 버튼이 있는 ConfirmView로 메시지를 교체합니다.
        view = ConfirmView(voice_channel=self.voice_channel)
        await interaction.response.edit_message(content='**정말로 채널을 삭제하시겠습니까?**', view=view, embed=None)

# --- 명령어 및 기능(Cog) 클래스 ---

class VoiceManagement(commands.Cog):
    """봇의 주요 기능(명령어, 백그라운드 작업 등)을 담고 있는 클래스입니다."""
    def __init__(self, bot):
        self.bot = bot
        self.empty_since = {}  # 각 채널이 비어있기 시작한 시간을 기록하는 딕셔너리
        self.check_empty_channels.start() # 봇이 준비되면 백그라운드 작업 시작

    def cog_unload(self):
        """Cog가 언로드될 때 백그라운드 작업을 중지합니다."""
        self.check_empty_channels.cancel()

    # --- 데코레이터 (권한 확인용) ---
    def is_admin():
        """명령어 사용자가 어드민인지 확인하는 데코레이터입니다."""
        async def predicate(interaction: discord.Interaction) -> bool:
            if interaction.user.id not in ADMIN_IDS:
                await interaction.response.send_message("❌ 이 명령어를 사용할 권한이 없습니다.", ephemeral=True)
                return False
            return True
        return app_commands.check(predicate)

    def is_allowed_channel():
        """명령어가 허용된 채널에서 사용되었는지 확인하는 데코레이터입니다."""
        async def predicate(interaction: discord.Interaction) -> bool:
            allowed_channels = load_json(ALLOWED_CHANNELS_FILE)
            if interaction.channel_id not in allowed_channels:
                await interaction.response.send_message("❌ 이 채널에서는 봇을 사용할 수 없습니다.", ephemeral=True)
                return False
            return True
        return app_commands.check(predicate)
    
    # --- 백그라운드 작업 ---
    @tasks.loop(minutes=1)
    async def check_empty_channels(self):
        """1분마다 생성된 음성 채널들을 확인하여 비어있는 채널을 자동으로 삭제합니다."""
        channels_data = load_json(CHANNELS_FILE)
        if not channels_data:
            return

        channels_to_remove = [] # 삭제할 채널 ID를 임시 저장할 리스트
        for data in channels_data:
            channel_id = data.get('channel_id')
            if not channel_id:
                continue

            try:
                # 봇 캐시 또는 API 호출을 통해 채널 객체를 가져옵니다.
                channel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)
                
                # 채널이 음성 채널이 아니면 목록에서 제거합니다.
                if not isinstance(channel, discord.VoiceChannel):
                    channels_to_remove.append(channel_id)
                    continue

                # 채널에 아무도 없는 경우
                if len(channel.members) == 0:
                    # 비어있는 상태가 처음 감지된 경우, 현재 시간을 기록합니다.
                    if channel_id not in self.empty_since:
                        self.empty_since[channel_id] = datetime.utcnow()
                    # 비어있는 상태가 10분 이상 지속된 경우
                    elif datetime.utcnow() - self.empty_since[channel_id] > timedelta(minutes=10):
                        print(f"'{channel.name}' 채널이 10분 이상 비어있어 삭제합니다.")
                        
                        # 원본 관리 메시지를 수정하여 자동 삭제되었음을 알립니다.
                        msg_channel_id = data.get('message_channel_id')
                        msg_id = data.get('message_id')
                        if msg_channel_id and msg_id:
                            try:
                                msg_channel = self.bot.get_channel(msg_channel_id) or await self.bot.fetch_channel(msg_channel_id)
                                message = await msg_channel.fetch_message(msg_id)
                                await message.edit(content=f"🗑️ **{channel.name}** 채널이 10분 이상 비어있어 자동으로 삭제되었습니다.", embed=None, view=None)
                            except discord.NotFound:
                                print(f"자동 삭제 메시지를 수정하려 했으나 원본 메시지를 찾을 수 없습니다. (ID: {msg_id})")
                            except Exception as e:
                                print(f"자동 삭제 메시지 수정 중 오류 발생: {e}")

                        await channel.delete(reason="10분 이상 비어있어 자동 삭제")
                        channels_to_remove.append(channel_id)
                        if channel_id in self.empty_since:
                            del self.empty_since[channel_id]
                # 채널에 누군가 있는 경우, 비어있던 기록을 삭제합니다.
                else:
                    if channel_id in self.empty_since:
                        del self.empty_since[channel_id]

            except discord.NotFound:
                # 채널이 이미 삭제된 경우, 목록에서 제거합니다.
                channels_to_remove.append(channel_id)
            except Exception as e:
                print(f'채널 확인 중 오류 발생 (ID: {channel_id}): {e}')

        # 삭제 대상 채널들을 JSON 파일에서 최종적으로 제거합니다.
        if channels_to_remove:
            current_channels = load_json(CHANNELS_FILE)
            updated_channels = [d for d in current_channels if d.get('channel_id') not in channels_to_remove]
            save_json(updated_channels, CHANNELS_FILE)

    @check_empty_channels.before_loop
    async def before_check_empty_channels(self):
        """백그라운드 작업이 시작되기 전에 봇이 준비될 때까지 기다립니다."""
        await self.bot.wait_until_ready()

    # --- 슬래시 명령어 ---
    @app_commands.command(name='setchannel', description='(어드민) 현재 채널을 봇 사용 가능 채널로 등록합니다.')
    @is_admin() # 어드민만 사용 가능
    async def setchannel(self, interaction: discord.Interaction):
        allowed_channels = load_json(ALLOWED_CHANNELS_FILE)
        if interaction.channel_id in allowed_channels:
            await interaction.response.send_message("이미 등록된 채널입니다.", ephemeral=True)
        else:
            allowed_channels.append(interaction.channel_id)
            save_json(allowed_channels, ALLOWED_CHANNELS_FILE)
            await interaction.response.send_message(f"✅ **{interaction.channel.name}** 채널을 봇 사용 가능 채널로 등록했습니다.", ephemeral=True)

    @app_commands.command(name='unsetchannel', description='(어드민) 현재 채널을 봇 사용 가능 채널에서 제외합니다.')
    @is_admin() # 어드민만 사용 가능
    async def unsetchannel(self, interaction: discord.Interaction):
        allowed_channels = load_json(ALLOWED_CHANNELS_FILE)
        if interaction.channel_id not in allowed_channels:
            await interaction.response.send_message("등록되지 않은 채널입니다.", ephemeral=True)
        else:
            allowed_channels.remove(interaction.channel_id)
            save_json(allowed_channels, ALLOWED_CHANNELS_FILE)
            await interaction.response.send_message(f"🗑️ **{interaction.channel.name}** 채널을 봇 사용 가능 채널에서 제외했습니다.", ephemeral=True)


    @app_commands.command(name='listchannels', description='(어드민) 봇 사용이 허용된 모든 채널 목록을 보여줍니다.')
    @is_admin()
    async def listchannels(self, interaction: discord.Interaction):
        """봇 사용이 허용된 채널의 목록을 임베드로 보여줍니다."""
        await interaction.response.defer(ephemeral=True)

        allowed_channel_ids = load_json(ALLOWED_CHANNELS_FILE)
        
        if not allowed_channel_ids:
            await interaction.followup.send("봇 사용이 허용된 채널이 없습니다.", ephemeral=True)
            return

        embed = Embed(title="✅ 봇 사용 가능 채널 목록", color=discord.Color.blue())
        
        description_lines = []
        for channel_id in allowed_channel_ids:
            channel = self.bot.get_channel(channel_id)
            if channel:
                description_lines.append(f"- {channel.mention} (`{channel.name}`)")
            else:
                # 캐시에서 채널을 찾지 못한 경우 (예: 봇 재시작 직후)
                try:
                    channel = await self.bot.fetch_channel(channel_id)
                    description_lines.append(f"- {channel.mention} (`{channel.name}`)")
                except discord.NotFound:
                    description_lines.append(f"- ❓ 알 수 없는 채널 (ID: `{channel_id}`)")
                except discord.Forbidden:
                    description_lines.append(f"- 🔒 접근 불가 채널 (ID: `{channel_id}`)")

        embed.description = "\n".join(description_lines)
        await interaction.followup.send(embed=embed, ephemeral=True)


    @app_commands.command(name='createvoice', description='음성 채널을 생성하고 관리합니다.')
    @app_commands.describe(
        name='생성할 채널 이름',
        limit='최대 인원 수 (0은 무제한)',
        bitrate='음성 채널의 비트레이트 (kbps, 8-96, 서버 부스트에 따라 더 높게 가능)'
    )
    @is_allowed_channel() # 허용된 채널에서만 사용 가능
    async def createvoice(self, interaction: discord.Interaction, name: str, limit: int, bitrate: int = 64):
        # defer()를 사용하여 3초 이상 걸릴 수 있는 작업에 대한 타임아웃을 방지하고, 응답을 명령어 사용자에게만 표시합니다.
        await interaction.response.defer(ephemeral=True)
        
        # 명령어가 사용된 채널의 카테고리를 찾습니다.
        category = interaction.channel.category
        if not category:
            # 스레드 채널 등은 parent 속성을 통해 카테고리를 찾습니다.
            if hasattr(interaction.channel, 'parent') and isinstance(interaction.channel.parent, discord.CategoryChannel):
                category = interaction.channel.parent
            else:
                return await interaction.followup.send('❌ 이 채널은 카테고리에 속해 있지 않습니다.', ephemeral=True)

        try:
            # 카테고리 안에 음성 채널을 생성합니다. 비트레이트는 bps 단위이므로 1000을 곱합니다.
            vc = await category.create_voice_channel(name=name, user_limit=limit, bitrate=bitrate * 1000)
            
            # 생성 완료 임베드 메시지를 구성합니다.
            embed = Embed(title="✅ 음성 채널 생성 완료",
                            description=f"음성 채널 **{vc.mention}**이(가) 성공적으로 생성되었습니다.",
                            color=discord.Color.green())
            embed.add_field(name="**카테고리**", value=f"`{category.name}`", inline=True)
            embed.add_field(name="**채널 이름**", value=f"`{name}`", inline=True)
            embed.add_field(name="**최대 인원**", value=f"`{limit if limit > 0 else '무제한'}`", inline=True)
            embed.add_field(name="**비트레이트**", value=f"`{bitrate} kbps`", inline=True)
            
            # 채널 관리 버튼 View를 생성하고 메시지를 전송합니다.
            view = ManagementView(voice_channel=vc, creator_id=interaction.user.id)
            message = await interaction.followup.send(embed=embed, view=view)

            # 생성된 채널 정보를 JSON 파일에 저장합니다.
            channels = load_json(CHANNELS_FILE)
            channels.append({
                'channel_id': vc.id,
                'message_id': message.id,
                'message_channel_id': message.channel.id
            })
            save_json(channels, CHANNELS_FILE)

        except discord.Forbidden:
            await interaction.followup.send(f'❌ 생성 실패: 봇이 `{category.name}` 카테고리에 채널을 생성할 권한이 없습니다.', ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f'❌ 생성 실패: {e}', ephemeral=True)

# --- 봇 실행 ---

async def setup(bot):
    """봇에 Cog를 등록합니다."""
    await bot.add_cog(VoiceManagement(bot))

# 이 파일이 직접 실행될 때만 아래 코드를 실행합니다.
if __name__ == '__main__':
    # .env 파일에서 봇 토큰을 가져옵니다.
    token = os.getenv('BOT_TOKEN')
    if not token:
        print('Error: BOT_TOKEN 환경 변수가 설정되지 않았습니다.')
        exit(1)
    
    async def main():
        """봇을 비동기적으로 실행하기 위한 메인 함수입니다."""
        async with bot:
            # 봇이 시작되기 전에 필요한 JSON 파일들을 로드(또는 생성)합니다.
            load_json(CHANNELS_FILE)
            load_json(ALLOWED_CHANNELS_FILE)
            # Cog를 설정합니다.
            await setup(bot)
            # 봇을 시작합니다.
            await bot.start(token)

    # 비동기 main 함수를 실행합니다.
    import asyncio
    asyncio.run(main())
