import os
from dotenv import load_dotenv
import discord
from discord.ext import commands
from discord import app_commands

# token.env 파일에서 환경 변수 로드
load_dotenv('token.env')

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

class VoiceManagement(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name='createvoice', description='현재 카테고리에 음성 채널을 생성합니다')
    @app_commands.describe(name='생성할 채널 이름', limit='최대 인원 수')
    async def createvoice(self, interaction: discord.Interaction, name: str, limit: int):
        await interaction.response.defer(ephemeral=True)
        category = interaction.channel.category
        if not category:
            return await interaction.followup.send('❌ 이 채널이 카테고리에 속해 있지 않습니다.')
        # 카테고리의 권한 오버라이트를 그대로 복사
        overwrites = category.overwrites
        try:
            vc = await category.create_voice_channel(
                name=name,
                overwrites=overwrites,
                user_limit=limit
            )
            await interaction.followup.send(f'✅ 음성 채널 생성됨: {vc.mention}')
        except Exception as e:
            await interaction.followup.send(f'❌ 생성 실패: {e}')

    @app_commands.command(name='deletevoice', description='음성 채널을 삭제합니다')
    @app_commands.describe(channel='삭제할 음성 채널')
    async def deletevoice(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        await interaction.response.defer(ephemeral=True)
        if not isinstance(channel, discord.VoiceChannel):
            return await interaction.followup.send('❌ 음성 채널을 선택하세요.')
        try:
            await channel.delete(reason=f'{interaction.user} 요청')
            await interaction.followup.send(f'🗑️ 채널 삭제됨: {channel.name}')
        except Exception as e:
            await interaction.followup.send(f'❌ 삭제 실패: {e}')

# Cog 등록
bot.add_cog(VoiceManagement(bot))

# 봇 실행
if __name__ == '__main__':
    token = os.getenv('BOT_TOKEN')
    if not token:
        print('Error: BOT_TOKEN 환경 변수가 설정되지 않았습니다.')
        exit(1)
    bot.run(token)
