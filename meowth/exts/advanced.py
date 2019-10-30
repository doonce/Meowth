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
        if "niandick" in message.content.lower():
            await utils.safe_reaction(message, "\U0001F346")
    
def setup(bot):
    bot.add_cog(Advanced(bot))

def teardown(bot):
    bot.remove_cog(Advanced)
