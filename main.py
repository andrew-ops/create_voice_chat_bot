import os
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
import discord
from discord.ext import commands, tasks
from discord import app_commands, ui, ButtonStyle, Embed

# .env 파일에서 환경 변수 로드
load_dotenv('token.env')
load_dotenv('admin_id.env')

# 어드민 ID 로드 및 처리
ADMIN_IDS_STR = os.getenv('ADMIN_IDS')
ADMIN_IDS = [int(admin_id.strip()) for admin_id in ADMIN_IDS_STR.split(',')] if ADMIN_IDS_STR else []

# 봇 인텐트 설정
intents = discord.Intents.default()
intents.guilds = True
intents.voice_states = True

# 커맨드 프리픽스와 인텐트로 Bot 인스턴스 생성
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    try:
        synced = await bot.tree.sync()
        print(f'Synced {len(synced)} commands.')
    except Exception as e:
        print(f'Error syncing commands: {e}')

# --- JSON 파일 관리 ---
CHANNELS_FILE = 'created_channels.json'
ALLOWED_CHANNELS_FILE = 'allowed_channels.json'

def load_json(filename):
    if not os.path.exists(filename):
        with open(filename, 'w') as f:
            json.dump([], f)
        return []
    with open(filename, 'r') as f:
        return json.load(f)

def save_json(data, filename):
    with open(filename, 'w') as f:
        json.dump(data, f, indent=4)

class ConfirmView(ui.View):
    def __init__(self, voice_channel: discord.VoiceChannel):
        super().__init__(timeout=60)
        self.voice_channel = voice_channel

    async def remove_channel_from_json(self):
        channels = load_json(CHANNELS_FILE)
        if self.voice_channel.id in channels:
            channels.remove(self.voice_channel.id)
            save_json(channels, CHANNELS_FILE)

    @ui.button(label='확인', style=ButtonStyle.red)
    async def confirm(self, interaction: discord.Interaction, button: ui.Button):
        channel_name = self.voice_channel.name
        await self.remove_channel_from_json()
        await self.voice_channel.delete(reason=f'{interaction.user}의 요청으로 삭제')
        self.clear_items()
        await interaction.response.edit_message(content=f'🗑️ **{channel_name}** 채널이 삭제되었습니다.', embed=None, view=self)

    @ui.button(label='취소', style=ButtonStyle.grey)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        view = ManagementView(voice_channel=self.voice_channel)
        await interaction.response.edit_message(view=view)


class ManagementView(ui.View):
    def __init__(self, voice_channel: discord.VoiceChannel):
        super().__init__(timeout=None) # 자동 삭제 기능이 있으므로 버튼은 비활성화 되지 않도록 함
        self.voice_channel = voice_channel

    @ui.button(label='채널 삭제', style=ButtonStyle.danger)
    async def delete_channel(self, interaction: discord.Interaction, button: ui.Button):
        # 확인/취소 버튼이 있는 새로운 View로 교체
        view = ConfirmView(voice_channel=self.voice_channel)
        await interaction.response.edit_message(content='**정말로 채널을 삭제하시겠습니까?**', view=view, embed=None)


class VoiceManagement(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.empty_since = {}
        self.check_empty_channels.start()

    def cog_unload(self):
        self.check_empty_channels.cancel()

    # --- 데코레이터 ---
    def is_admin():
        async def predicate(interaction: discord.Interaction) -> bool:
            if interaction.user.id not in ADMIN_IDS:
                await interaction.response.send_message("❌ 이 명령어를 사용할 권한이 없습니다.", ephemeral=True)
                return False
            return True
        return app_commands.check(predicate)

    def is_allowed_channel():
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
        channels_to_check = load_json(CHANNELS_FILE)
        if not channels_to_check:
            return

        channels_to_remove = []
        for channel_id in channels_to_check:
            try:
                channel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)
                
                if not isinstance(channel, discord.VoiceChannel):
                    channels_to_remove.append(channel_id)
                    continue

                if len(channel.members) == 0:
                    if channel_id not in self.empty_since:
                        self.empty_since[channel_id] = datetime.utcnow()
                    elif datetime.utcnow() - self.empty_since[channel_id] > timedelta(minutes=10):
                        print(f"'{channel.name}' 채널이 10분 이상 비어있어 삭제합니다.")
                        await channel.delete(reason="10분 이상 비어있어 자동 삭제")
                        channels_to_remove.append(channel_id)
                        if channel_id in self.empty_since:
                            del self.empty_since[channel_id]
                else:
                    if channel_id in self.empty_since:
                        del self.empty_since[channel_id]

            except discord.NotFound:
                channels_to_remove.append(channel_id)
            except Exception as e:
                print(f'채널 확인 중 오류 발생 (ID: {channel_id}): {e}')

        if channels_to_remove:
            current_channels = load_json(CHANNELS_FILE)
            updated_channels = [ch for ch in current_channels if ch not in channels_to_remove]
            save_json(updated_channels, CHANNELS_FILE)

    @check_empty_channels.before_loop
    async def before_check_empty_channels(self):
        await self.bot.wait_until_ready()

    # --- 명령어 ---
    @app_commands.command(name='setchannel', description='(어드민) 현재 채널을 봇 사용 가능 채널로 등록합니다.')
    @is_admin()
    async def setchannel(self, interaction: discord.Interaction):
        allowed_channels = load_json(ALLOWED_CHANNELS_FILE)
        if interaction.channel_id in allowed_channels:
            await interaction.response.send_message("이미 등록된 채널입니다.", ephemeral=True)
        else:
            allowed_channels.append(interaction.channel_id)
            save_json(allowed_channels, ALLOWED_CHANNELS_FILE)
            await interaction.response.send_message(f"✅ **{interaction.channel.name}** 채널을 봇 사용 가능 채널로 등록했습니다.", ephemeral=True)

    @app_commands.command(name='unsetchannel', description='(어드민) 현재 채널을 봇 사용 가능 채널에서 제외합니다.')
    @is_admin()
    async def unsetchannel(self, interaction: discord.Interaction):
        allowed_channels = load_json(ALLOWED_CHANNELS_FILE)
        if interaction.channel_id not in allowed_channels:
            await interaction.response.send_message("등록되지 않은 채널입니다.", ephemeral=True)
        else:
            allowed_channels.remove(interaction.channel_id)
            save_json(allowed_channels, ALLOWED_CHANNELS_FILE)
            await interaction.response.send_message(f"🗑️ **{interaction.channel.name}** 채널을 봇 사용 가능 채널에서 제외했습니다.", ephemeral=True)


    @app_commands.command(name='createvoice', description='음성 채널을 생성하고 관리합니다.')
    @app_commands.describe(name='생성할 채널 이름', limit='최대 인원 수 (0은 무제한)')
    @is_allowed_channel()
    async def createvoice(self, interaction: discord.Interaction, name: str, limit: int):
        await interaction.response.defer(ephemeral=False)
        
        category = interaction.channel.category
        if not category:
            if hasattr(interaction.channel, 'parent') and isinstance(interaction.channel.parent, discord.CategoryChannel):
                category = interaction.channel.parent
            else:
                return await interaction.followup.send('❌ 이 채널은 카테고리에 속해 있지 않습니다.', ephemeral=True)

        try:
            vc = await category.create_voice_channel(name=name, user_limit=limit)
            
            channels = load_json(CHANNELS_FILE)
            channels.append(vc.id)
            save_json(channels, CHANNELS_FILE)

            embed = Embed(title="✅ 음성 채널 생성 완료",
                            description=f"음성 채널 **{vc.mention}**이(가) 성공적으로 생성되었습니다.",
                            color=discord.Color.green())
            embed.add_field(name="**카테고리**", value=f"`{category.name}`", inline=True)
            embed.add_field(name="**채널 이름**", value=f"`{name}`", inline=True)
            embed.add_field(name="**최대 인원**", value=f"`{limit if limit > 0 else '무제한'}`", inline=True)
            
            view = ManagementView(voice_channel=vc)
            await interaction.followup.send(embed=embed, view=view)

        except Exception as e:
            await interaction.followup.send(f'❌ 생성 실패: {e}')

# Cog 등록
async def setup(bot):
    await bot.add_cog(VoiceManagement(bot))

# 봇 실행
if __name__ == '__main__':
    token = os.getenv('BOT_TOKEN')
    if not token:
        print('Error: BOT_TOKEN 환경 변수가 설정되지 않았습니다.')
        exit(1)
    
    async def main():
        async with bot:
            # JSON 파일 로드/생성
            load_json(CHANNELS_FILE)
            load_json(ALLOWED_CHANNELS_FILE)
            await setup(bot)
            await bot.start(token)

    import asyncio
    asyncio.run(main())
