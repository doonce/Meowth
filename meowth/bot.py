import discord
from discord.ext import commands

from meowth import checks, errors
from meowth.exts import utilities as utils
from meowth.context import Context

class MeowthBot(commands.AutoShardedBot):
    """Custom Discord Bot class for Meowth"""

    async def process_commands(self, message):
        """Processes commands that are registed with the bot and it's groups.

        Without this being run in the main `on_message` event, commands will
        not be processed.
        """
        if message.author.bot:
            return
        ctx = await self.get_context(message, cls=Context)
        if ctx.guild and ctx.channel.id in ctx.bot.guild_dict[ctx.guild.id]['raidchannel_dict']:
            if ctx.bot.guild_dict[ctx.guild.id]['configure_dict']['invite']['enabled']:
                raid_type = ctx.bot.guild_dict[ctx.guild.id]['raidchannel_dict'].get(ctx.channel.id, {}).get('type', None)
                raid_level = ctx.bot.guild_dict[ctx.guild.id]['raidchannel_dict'].get(ctx.channel.id, {}).get('egglevel', None)
                if raid_type == "exraid" or raid_level == "EX":
                    if ctx.author not in [i[0] for i in ctx.channel.overwrites]:
                        if not ctx.channel.permissions_for(ctx.author).manage_guild and not ctx.channel.permissions_for(ctx.author).manage_channels and not ctx.channel.permissions_for(ctx.author).manage_messages:
                            ow = ctx.channel.overwrites_for(ctx.author)
                            ow.send_messages = False
                            try:
                                await ctx.channel.set_permissions(ctx.author, overwrite = ow)
                            except (discord.errors.Forbidden, discord.errors.HTTPException, discord.errors.InvalidArgument):
                                pass
                            await utils.safe_delete(ctx.message)
                            await ctx.bot.on_command_error(ctx, errors.EXInviteFail())
                            return
        if not ctx.command:
            return
        await self.invoke(ctx)
