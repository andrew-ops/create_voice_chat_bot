import os
from dotenv import load_dotenv
import discord
from discord.ext import commands
from discord import app_commands, ui, ButtonStyle, Embed
from discord.utils import get

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

class ConfirmView(ui.View):
    def __init__(self, voice_channel: discord.VoiceChannel):
        super().__init__(timeout=60)
        self.voice_channel = voice_channel

    @ui.button(label='확인', style=ButtonStyle.red)
    async def confirm(self, interaction: discord.Interaction, button: ui.Button):
        channel_name = self.voice_channel.name
        await self.voice_channel.delete(reason=f'{interaction.user}의 요청으로 삭제')
        self.clear_items()
        await interaction.response.edit_message(content=f'🗑️ **{channel_name}** 채널이 삭제되었습니다.', embed=None, view=self)

    @ui.button(label='취소', style=ButtonStyle.grey)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        # ManagementView를 다시 생성하여 원래 상태로 되돌립니다.
        view = ManagementView(voice_channel=self.voice_channel)
        await interaction.response.edit_message(view=view)


class ManagementView(ui.View):
    def __init__(self, voice_channel: discord.VoiceChannel):
        super().__init__(timeout=300) # 5분 후 버튼 비활성화
        self.voice_channel = voice_channel

    @ui.button(label='채널 삭제', style=ButtonStyle.danger)
    async def delete_channel(self, interaction: discord.Interaction, button: ui.Button):
        # 확인/취소 버튼이 있는 새로운 View로 교체
        view = ConfirmView(voice_channel=self.voice_channel)
        await interaction.response.edit_message(content='**정말로 채널을 삭제하시겠습니까?**', view=view)


class VoiceManagement(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name='test', description='봇이 작동하는지 테스트합니다.')
    async def test(self,interaction: discord.Interaction):
        print("🛠 test called")

        tcategory = interaction.channel.category
        if tcategory is None:
            await interaction.response.send_message('❌ 이 채널은 카테고리에 속해 있지 않습니다.', ephemeral=True)
        else:
            await interaction.response.send_message(f'✅ 이 채널은 카테고리 **{tcategory.name}**에 속해 있습니다.', ephemeral=True)

    @app_commands.command(name='createvoice', description='현재 카테고리에 음성 채널을 생성하고 관리합니다.')
    @app_commands.describe(name='생성할 채널 이름', limit='최대 인원 수 (0은 무제한)')
    async def createvoice(self, interaction: discord.Interaction, name: str, limit: int):
        await interaction.response.defer(ephemeral=True)
        category = interaction.channel.category
        if not category:
            return await interaction.followup.send('❌ 이 채널은 카테고리에 속해 있지 않습니다.')

        try:
            vc = await category.create_voice_channel(
                name=name,
                user_limit=limit
            )
            
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
            await setup(bot)
            await bot.start(token)

    import asyncio
    asyncio.run(main())
