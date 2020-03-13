import asyncio
import copy
import re
import time
import datetime
import dateparser
import textwrap
import logging
import io
import traceback

import discord
from discord.ext import commands, tasks
from contextlib import redirect_stdout

from meowth import checks
from meowth.exts import pokemon as pkmn_class
from meowth.exts import utilities as utils

logger = logging.getLogger("meowth")

# This is a place for server-specific things or fun things outside of the main Meowth bot.
# You can remove this cog entirely or remove any function within it.
# If you know Discord.py you can add your own functions here.

class Advanced(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def cog_unload(self):
        pass

    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.guild:
            return
        if message.guild.id not in list(self.bot.guild_dict.keys()):
            return
        if "niandick" in message.content.lower():
            await utils.add_reaction(message, "\U0001F346")
        if message.author.id == 358090000371286018:
            if message.channel.id == 458696131594158099 and message.attachments:
                ctx = await self.get_context(message)
                ctx.prefix = '!'
                await utils.safe_delete(message)
                tutorial_command = self.get_command("tutorial")
                trade_command = tutorial_command.all_commands.get('trade')
                if trade_command:
                    await ctx.invoke(trade_command)
                    return

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        channel = self.bot.get_channel(payload.channel_id)
        guild = getattr(channel, "guild", None)
        if guild and guild.id not in list(self.bot.guild_dict.keys()):
            return
        try:
            user = self.bot.get_user(payload.user_id)
        except AttributeError:
            return
        if user == self.bot.user:
            return
        if guild:
            user = guild.get_member(payload.user_id)
        else:
            return
        try:
            message = await channel.fetch_message(payload.message_id)
        except (discord.errors.NotFound, AttributeError, discord.Forbidden):
            return
        if payload.emoji.name =='\U00002705' and message.id == 644615360968130603:
            categories = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(user.id, {}).setdefault('alerts', {}).setdefault('settings', {}).setdefault('categories', {}).setdefault('pokemon', {})
            self.bot.guild_dict[guild.id]['trainers'][user.id]['alerts']['settings']['categories']['pokemon']['trade'] = True
        if message.id == 687748212030832709:
            if payload.emoji.name == "mystic":
                role = discord.utils.get(guild.roles, name="mystic")
                await user.add_roles(role)
            elif payload.emoji.name == "valor":
                role = discord.utils.get(guild.roles, name="valor")
                await user.add_roles(role)
            elif payload.emoji.name == "instinct":
                role = discord.utils.get(guild.roles, name="instinct")
                await user.add_roles(role)

def setup(bot):
    bot.add_cog(Advanced(bot))

def teardown(bot):
    bot.remove_cog(Advanced)
