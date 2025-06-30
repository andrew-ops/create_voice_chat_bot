import os
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
import discord
from discord.ext import commands, tasks
from discord import app_commands, ui, ButtonStyle, Embed

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

# --- JSON 파일 관리 ---
CHANNELS_FILE = 'created_channels.json'

def load_channels():
    if not os.path.exists(CHANNELS_FILE):
        with open(CHANNELS_FILE, 'w') as f:
            json.dump([], f)
        return []
    with open(CHANNELS_FILE, 'r') as f:
        return json.load(f)

def save_channels(channels):
    with open(CHANNELS_FILE, 'w') as f:
        json.dump(channels, f, indent=4)

class ConfirmView(ui.View):
    def __init__(self, voice_channel: discord.VoiceChannel):
        super().__init__(timeout=60)
        self.voice_channel = voice_channel

    async def remove_channel_from_json(self):
        channels = load_channels()
        if self.voice_channel.id in channels:
            channels.remove(self.voice_channel.id)
            save_channels(channels)

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
        self.empty_since = {}
        self.check_empty_channels.start()

    def cog_unload(self):
        self.check_empty_channels.cancel()

    @tasks.loop(minutes=1)
    async def check_empty_channels(self):
        channels_to_check = load_channels()
        channels_to_remove = []

        for channel_id in channels_to_check:
            try:
                channel = await self.bot.fetch_channel(channel_id)
                if not isinstance(channel, discord.VoiceChannel):
                    channels_to_remove.append(channel_id)
                    continue

                if len(channel.members) == 0:
                    if channel_id not in self.empty_since:
                        self.empty_since[channel_id] = datetime.utcnow()
                    elif datetime.utcnow() - self.empty_since[channel_id] > timedelta(minutes=10):
                        print(f'{channel.name} 채널이 10분 이상 비어있어 삭제합니다.')
                        await channel.delete(reason="10분 이상 비어있어 자동 삭제")
                        channels_to_remove.append(channel_id)
                        del self.empty_since[channel_id]
                else:
                    if channel_id in self.empty_since:
                        del self.empty_since[channel_id]

            except discord.NotFound:
                print(f'{channel_id} 채널을 찾을 수 없어 목록에서 제거합니다.')
                channels_to_remove.append(channel_id)
            except Exception as e:
                print(f'채널 확인 중 오류 발생 (ID: {channel_id}): {e}')

        if channels_to_remove:
            current_channels = load_channels()
            updated_channels = [ch for ch in current_channels if ch not in channels_to_remove]
            save_channels(updated_channels)

    @check_empty_channels.before_loop
    async def before_check_empty_channels(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name='test', description='봇이 작동하는지 테스트합니다.')
    async def test(self,interaction: discord.Interaction):
        print("🛠 test called")

        # 1. 3초 타임아웃 방지
        await interaction.response.defer(ephemeral=True)

        # 2. 명령어 실행 채널 정보
        ch = interaction.channel
        cat_id = getattr(ch, 'category_id', None) or getattr(ch, 'parent_id', None)
        if not cat_id:
            return await interaction.followup.send(
                '❌ 카테고리 ID를 읽어올 수가 없네…', ephemeral=True
            )

        # 3. client.fetch_channel 로 API 호출  
        try:
            category = interaction.client.get_channel(cat_id)
            if category is None:
                category = await interaction.client.fetch_channel(cat_id)
            print("▶ client.fetch_channel 결과:", category)
        except Exception as e:
            return await interaction.followup.send(
                f'❌ 카테고리 조회 중 오류: {e}', ephemeral=True
            )

        # 4. CategoryChannel 인지 확인
        if not isinstance(category, discord.CategoryChannel):
            return await interaction.followup.send(
                '❌ 가져온 채널이 카테고리가 아니야.', ephemeral=True
            )

        # 5. 최종 응답
        await interaction.followup.send(
            f'✅ 이 채널의 카테고리는 **{category.name}** (ID: {category.id}) 야.',
            ephemeral=True
        )


        tcategory = interaction.channel.parent
        if tcategory is None:
            await interaction.response.send_message('❌ 이 채널은 카테고리에 속해 있지 않습니다.', ephemeral=True)
        else:
            await interaction.response.send_message(f'✅ 이 채널은 카테고리 **{tcategory.name}**에 속해 있습니다.', ephemeral=True)

    @app_commands.command(name='createvoice', description='현재 카테고리에 음성 채널을 생성하고 관리합니다.')
    @app_commands.describe(name='생성할 채널 이름', limit='최대 인원 수 (0은 무제한)')
    async def createvoice(self, interaction: discord.Interaction, name: str, limit: int):
        await interaction.response.defer(ephemeral=False) # 메시지를 모두에게 보이도록 변경
        
        ch = interaction.channel
        category = ch.category
        if not category:
            # 스레드나 포럼 같은 경우 parent를 통해 카테고리를 찾음
            if hasattr(ch, 'parent') and isinstance(ch.parent, discord.CategoryChannel):
                category = ch.parent
            else:
                return await interaction.followup.send('❌ 이 채널은 카테고리에 속해 있지 않습니다.', ephemeral=True)

        try:
            vc = await category.create_voice_channel(
                name=name,
                user_limit=limit
            )
            
            # JSON 파일에 채널 ID 추가
            channels = load_channels()
            channels.append(vc.id)
            save_channels(channels)

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
