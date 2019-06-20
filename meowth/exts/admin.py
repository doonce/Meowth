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

class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.guild_cleanup.start()

    def cog_unload(self):
        self.guild_cleanup.cancel()

    @tasks.loop(seconds=0)
    async def guild_cleanup(self, loop=True):
        while True:
            guilddict_srvtemp = copy.deepcopy(self.bot.guild_dict)
            logger.info('------ BEGIN ------')
            dict_guild_list = []
            bot_guild_list = []
            dict_guild_delete = []
            for guildid in guilddict_srvtemp.keys():
                dict_guild_list.append(guildid)
            for guild in self.bot.guilds:
                bot_guild_list.append(guild.id)
            guild_diff = set(dict_guild_list) - set(bot_guild_list)
            for s in guild_diff:
                dict_guild_delete.append(s)
            for s in dict_guild_delete:
                try:
                    del self.guild_dict[s]
                    logger.info(('Cleared ' + str(s)) +
                                ' from save data')
                except KeyError:
                    pass
            logger.info('SAVING CHANGES')
            try:
                await self.bot.save
            except Exception as err:
                logger.info('SAVING FAILED' + err)
            logger.info('------ END ------')
            if not loop:
                return
            await asyncio.sleep(7200)
            continue

    @guild_cleanup.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()

    @commands.command(name='save')
    @checks.is_owner()
    async def save_cmd(self, ctx):
        """Save persistent state to file.

        Usage: !save
        File path is relative to current directory."""
        try:
            await self.bot.save
            logger.info('CONFIG SAVED')
        except Exception as err:
            print(_('Error occured while trying to save!'))
            print(err)

    @commands.command()
    @checks.is_owner()
    async def restart(self, ctx):
        """Restart after saving.

        Usage: !restart.
        Calls the save function and restarts Meowth."""
        try:
            await self.bot.save
        except Exception as err:
            print(_('Error occured while trying to save!'))
            print(err)
        await ctx.channel.send(embed=discord.Embed(colour=ctx.guild.me.colour, description=f"Restarting..."))
        self.bot._shutdown_mode = 26
        await self.bot.logout()

    @commands.command(name='reload')
    @checks.is_owner()
    async def _reload(self, ctx, *extensions):
        """Reload all current extensions

        Useful if restarts become slow due to large guilds"""
        reload_str = []
        reloaded_exts = []
        for ext in self.bot.extensions:
            try:
                if ext not in reloaded_exts:
                    ctx.bot.reload_extension(ext)
                    reloaded_exts.append(ext)
                    reload_str.append(f"**{ext.replace('meowth.exts.', '')}**")
            except Exception as e:
                error_title = _('**Error when loading extension')
                await ctx.send(f'{error_title} {ext}:**\n'
                               f'{type(e).__name__}: {e}')
                return
        await ctx.send(embed=discord.Embed(colour=ctx.guild.me.colour, description=f"Reloaded the following extensions:\n\n{(', ').join(reload_str)}"))

    @commands.command(name="shutdown", aliases=["exit"])
    @checks.is_owner()
    async def exit(self, ctx):
        """Exit after saving.

        Usage: !exit.
        Calls the save function and quits the script."""
        try:
            await self.bot.save
        except Exception as err:
            print(_('Error occured while trying to save!'))
            print(err)
        await ctx.send(embed=discord.Embed(colour=ctx.guild.me.colour, description=f"Shutting Down..."))
        self.bot._shutdown_mode = 0
        await self.bot.logout()

    @commands.command(name='load')
    @checks.is_owner()
    async def _load(self, ctx, *extensions):
        """Load or reload an extension"""
        for ext in extensions:
            try:
                if f"meowth.exts.{ext}" in self.bot.extensions:
                    ctx.bot.reload_extension(f"meowth.exts.{ext}")
                    await ctx.send(_('**Extension {ext} Reloaded.**\n').format(ext=ext))
                    return
                ctx.bot.load_extension(f"meowth.exts.{ext}")
                await ctx.send(_('**Extension {ext} Loaded.**\n').format(ext=ext))
            except Exception as e:
                error_title = _('**Error when loading extension')
                await ctx.send(f'{error_title} {ext}:**\n'
                               f'{type(e).__name__}: {e}')

    @commands.command(name='unload')
    @checks.is_owner()
    async def _unload(self, ctx, *extensions):
        """Unload an extension"""
        exts = [e for e in extensions if f"meowth.exts.{e}" in self.bot.extensions]
        for ext in exts:
            if ext in required_exts:
                exts.remove(ext)
                continue
            try:
                ctx.bot.unload_extension(f"meowth.exts.{ext}")
            except Exception as e:
                error_title = _('**Error when loading extension')
                await ctx.send(f'{error_title} {ext}:**\n'
                               f'{type(e).__name__}: {e}')
        s = 's' if len(exts) > 1 else ''
        if exts:
            await ctx.send(_("**Extension{plural} {est} unloaded.**\n").format(plural=s, est=', '.join(exts)))
        else:
            await ctx.send(_("**Extension{plural} {est} not loaded.**\n").format(plural=s, est=', '.join(exts)))

    @commands.command(hidden=True, name="eval")
    @checks.is_owner()
    async def _eval(self, ctx, *, body: str):
        """Evaluates a code"""
        env = {
            'Meowth': ctx.bot,
            'bot': ctx.bot,
            'ctx': ctx,
            'channel': ctx.channel,
            'author': ctx.author,
            'guild': ctx.guild,
            'message': ctx.message
        }
        def cleanup_code(content):
            """Automatically removes code blocks from the code."""
            # remove ```py\n```
            if content.startswith('```') and content.endswith('```'):
                return '\n'.join(content.split('\n')[1:-1])
            # remove `foo`
            return content.strip('` \n')
        env.update(globals())
        body = cleanup_code(body)
        stdout = io.StringIO()
        to_compile = (f'async def func():\n{textwrap.indent(body, "  ")}')
        try:
            exec(to_compile, env)
        except Exception as e:
            return await ctx.send(f'```py\n{e.__class__.__name__}: {e}\n```')
        func = env['func']
        try:
            with redirect_stdout(stdout):
                ret = await func()
        except Exception as e:
            value = stdout.getvalue()
            await ctx.send(f'```py\n{value}{traceback.format_exc()}\n```')
        else:
            value = stdout.getvalue()
            try:
                await utils.safe_reaction(ctx.message, config['command_done'])
            except:
                pass
            if ret is None:
                if value:
                    paginator = commands.Paginator(prefix='```py')
                    for line in textwrap.wrap(value, 80):
                        paginator.add_line(line.rstrip().replace('`', '\u200b`'))
                    for p in paginator.pages:
                        await ctx.send(p)
            else:
                ctx.bot._last_result = ret
                await ctx.send(f'```py\n{value}{ret}\n```')

    @commands.command(hidden=True)
    @commands.has_permissions(manage_guild=True)
    async def welcome(self, ctx, user: discord.Member=None):
        """Test welcome on yourself or mentioned member.

        Usage: !welcome [@member]"""
        if (not user):
            user = ctx.author
        await self.bot.on_member_join(user)

def setup(bot):
    bot.add_cog(Admin(bot))

def teardown(bot):
    bot.remove_cog(Admin)
