import asyncio
import copy
import re
import time
import datetime
import dateparser
import textwrap
import logging
import string

import discord
from discord.ext import commands, tasks

from meowth import checks
from meowth.exts import pokemon as pkmn_class
from meowth.exts import utilities as utils

logger = logging.getLogger("meowth")

class Lure(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.lure_cleanup.start()

    def cog_unload(self):
        self.lure_cleanup.cancel()

    @tasks.loop(seconds=0)
    async def lure_cleanup(self, loop=True):
        while True:
            logger.info('------ BEGIN ------')
            guilddict_temp = copy.deepcopy(self.bot.guild_dict)
            expire_list = []
            count = 0
            for guildid in guilddict_temp.keys():
                lure_dict = guilddict_temp[guildid].setdefault('lure_dict', {})
                for reportid in lure_dict.keys():
                    if lure_dict[reportid].get('exp', 0) <= time.time():
                        report_channel = self.bot.get_channel(lure_dict[reportid].get('reportchannel'))
                        if report_channel:
                            try:
                                report_message = await report_channel.fetch_message(reportid)
                                self.bot.loop.create_task(self.expire_lure(report_message))
                                count += 1
                                continue
                            except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException):
                                pass
                        try:
                            del self.bot.guild_dict[guildid]['lure_dict'][reportid]
                        except KeyError:
                            continue
                    to_expire = lure_dict[reportid].get('exp', 0) - time.time()
                    expire_list.append(to_expire)
            # save server_dict changes after cleanup
            logger.info('SAVING CHANGES')
            try:
                await self.bot.save()
            except Exception as err:
                logger.info('SAVING FAILED' + err)
                pass
            if not expire_list:
                expire_list = [600]
            logger.info(f"------ END - {count} Lures Cleaned - Waiting {min(expire_list)} seconds. ------")
            if not loop:
                return
            await asyncio.sleep(min(expire_list))
            continue

    @lure_cleanup.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        channel = self.bot.get_channel(payload.channel_id)
        try:
            message = await channel.fetch_message(payload.message_id)
        except (discord.errors.NotFound, AttributeError, discord.Forbidden):
            return
        guild = message.guild
        try:
            user = guild.get_member(payload.user_id)
        except AttributeError:
            return
        guild = message.guild
        try:
            lure_dict = self.bot.guild_dict[guild.id]['lure_dict']
        except KeyError:
            lure_dict = []
        if message.id in lure_dict and user.id != self.bot.user.id:
            wild_dict = self.bot.guild_dict[guild.id]['lure_dict'][message.id]
            if str(payload.emoji) == self.bot.config.get('lure_expire', '\U0001F4A8'):
                for reaction in message.reactions:
                    await self.expire_lure(message)

    async def expire_lure(self, message):
        guild = message.channel.guild
        channel = message.channel
        lure_dict = copy.deepcopy(self.bot.guild_dict[guild.id]['lure_dict'])
        await utils.safe_delete(message)
        try:
            user_message = await channel.fetch_message(lure_dict[message.id]['reportmessage'])
            await utils.safe_delete(user_message)
        except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException, KeyError):
            pass
        await utils.expire_dm_reports(self.bot, lure_dict.get(message.id, {}).get('dm_dict', {}))
        try:
            del self.bot.guild_dict[guild.id]['lure_dict'][message.id]
        except KeyError:
            pass

    @commands.group(invoke_without_command=True, case_insensitive=True)
    @checks.allowlurereport()
    async def lure(self, ctx, lure_type=None, *, location:commands.clean_content(fix_channel_mentions=True)="", timer=""):
        """Report an ongoing lure.

        Usage: !lure [type] [pokestop] [minutes]
        Guided report available with just !lure"""
        message = ctx.message
        channel = message.channel
        author = message.author
        guild = message.guild
        timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset']))
        error = False
        lure_embed = discord.Embed(colour=message.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/TroyKey.png?cache=1')
        lure_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=author.display_name, timestamp=timestamp.strftime(_('%I:%M %p (%H:%M)'))), icon_url=author.avatar_url_as(format=None, static_format='jpg', size=32))
        while True:
            async with ctx.typing():
                if lure_type and any([lure_type.lower() == "normal", lure_type.lower() == "mossy", lure_type.lower() == "glacial", lure_type.lower() == "magnetic"]) and location:
                    if location.split()[-1].isdigit():
                        timer = location.split()[-1]
                        location = location.replace(timer, '').strip()
                    if timer.isdigit() and int(timer) > 720:
                        timer = "720"
                    await self._lure(ctx, lure_type, location, timer)
                    return
                else:
                    lure_embed.add_field(name=_('**New Lure Report**'), value=_("Meowth! I'll help you report a lure!\n\nFirst, I'll need to know what **type** the lure is. Reply with the **normal, mossy, magnetic, or glacial**. You can reply with **cancel** to stop anytime."), inline=False)
                    lure_type_wait = await channel.send(embed=lure_embed)
                    def check(reply):
                        if reply.author is not guild.me and reply.channel.id == channel.id and reply.author == message.author:
                            return True
                        else:
                            return False
                    try:
                        lure_type_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        lure_type_msg = None
                    await utils.safe_delete(lure_type_wait)
                    if not lure_type_msg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(lure_type_msg)
                    if lure_type_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    elif not any([lure_type_msg.clean_content.lower() == "normal", lure_type_msg.clean_content.lower() == "mossy", lure_type_msg.clean_content.lower() == "magnetic", lure_type_msg.clean_content.lower() == "glacial"]):
                        error = _("entered an invalid type")
                        break
                    else:
                        lure_type = lure_type_msg.clean_content.lower()
                        if lure_type != "normal":
                            lure_embed.set_thumbnail(url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/TroyKey_{lure_type}.png?cache=1")
                    lure_embed.clear_fields()
                    lure_embed.add_field(name="**New Lure Report**", value=f"Great! Now, reply with the **pokestop** that has the **{lure_type} lure**. You can reply with **cancel** to stop anytime.", inline=False)
                    location_wait = await channel.send(embed=lure_embed)
                    try:
                        location_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        location_msg = None
                    await utils.safe_delete(location_wait)
                    if not location_msg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(location_msg)
                    if location_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    elif location_msg:
                        location = location_msg.clean_content
                        gym_matching_cog = self.bot.cogs.get('GymMatching')
                        stop_info = ""
                        if gym_matching_cog:
                            stop_info, location, stop_url = await gym_matching_cog.get_poi_info(ctx, location, "lure", dupe_check=False)
                            if stop_url:
                                loc_url = stop_url
                        if not location:
                            return
                    lure_embed.clear_fields()
                    lure_embed.add_field(name="**New Lure Report**", value=f"Fantastic! Now, reply with the **minutes remaining** before the **{lure_type} lure** ends. This is usually 30 minutes from when the lure started unless there is an event. If you don't know, reply with **N**. You can reply with **cancel** to stop anytime.", inline=False)
                    expire_wait = await channel.send(embed=lure_embed)
                    try:
                        expire_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        expire_msg = None
                    await utils.safe_delete(expire_wait)
                    if not expire_msg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(expire_msg)
                    if expire_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    elif expire_msg.clean_content.lower() == "n":
                        timer = ""
                    elif not expire_msg.clean_content.isdigit():
                        error = _("didn't enter a number")
                        break
                    elif int(expire_msg.clean_content) > 720:
                        timer = "720"
                    elif expire_msg:
                        timer = expire_msg.clean_content
                    lure_embed.remove_field(0)
                    break
        if not error:
            await self._lure(ctx, lure_type, location, timer)
        else:
            lure_embed.clear_fields()
            lure_embed.add_field(name=_('**Lure Report Cancelled**'), value=_("Meowth! Your report has been cancelled because you {error}! Retry when you're ready.").format(error=error), inline=False)
            confirmation = await channel.send(embed=lure_embed, delete_after=10)
            await utils.safe_delete(message)

    async def _lure(self, ctx, lure_type, location, timer):
        dm_dict = {}
        expire_time = "30"
        if timer:
            expire_time = timer
        timestamp = (ctx.message.created_at + datetime.timedelta(hours=self.bot.guild_dict[ctx.message.channel.guild.id]['configure_dict']['settings']['offset']))
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict']['settings']['offset'])
        end = now + datetime.timedelta(minutes=int(expire_time))
        lure_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/TroyKey.png?cache=1')
        lure_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=ctx.author.display_name, timestamp=timestamp.strftime(_('%I:%M %p (%H:%M)'))), icon_url=ctx.author.avatar_url_as(format=None, static_format='jpg', size=32))
        lure_msg = _("Lure reported by {author}").format(author=ctx.author.mention)
        lure_embed.title = _('Meowth! Click here for my directions to the lure!')
        lure_embed.description = f"Ask {ctx.author.name} if my directions aren't perfect!\n**Location:** {location}"
        loc_url = utils.create_gmaps_query(self.bot, location, ctx.channel, type="lure")
        gym_matching_cog = self.bot.cogs.get('GymMatching')
        stop_info = ""
        if gym_matching_cog:
            stop_info, location, stop_url = await gym_matching_cog.get_poi_info(ctx, location, "lure", dupe_check=False)
            if stop_url:
                loc_url = stop_url
                lure_embed.description = stop_info
        if not location:
            return
        lure_embed.url = loc_url
        item = None
        lure_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/TroyKey.png")
        lure_embed.set_author(name=f"Normal Lure Report", icon_url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/TroyKey.png?cache=1")
        item = "lure module"
        if lure_type != "normal":
            lure_embed.set_thumbnail(url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/TroyKey_{lure_type}.png")
            lure_embed.set_author(name=f"{lure_type.title()} Lure Report", icon_url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/TroyKey_{lure_type}.png?cache=1")
            item = f"{lure_type} lure module"
        lure_embed.add_field(name=f"**Lure Type:**", value=item.title())
        lure_embed.add_field(name=f"**{'Expires' if timer else 'Expire Estimate'}:**", value=end.strftime(_('%I:%M %p (%H:%M)')))
        confirmation = await ctx.channel.send(lure_msg, embed=lure_embed)
        test_var = self.bot.guild_dict[ctx.guild.id].setdefault('lure_dict', {}).setdefault(confirmation.id, {})
        self.bot.guild_dict[ctx.guild.id]['lure_dict'][confirmation.id] = {
            'exp':time.time() + int(expire_time)*60,
            'expedit':"delete",
            'reportmessage':ctx.message.id,
            'reportchannel':ctx.channel.id,
            'reportauthor':ctx.author.id,
            'dm_dict':dm_dict,
            'location':location,
            'url':loc_url,
            'type':lure_type
        }
        if not timer:
            await utils.safe_reaction(confirmation, self.bot.config.get('lure_expire', '\U0001F4A8'))
        lure_embed.description = lure_embed.description + f"\n**Report:** [Jump to Message]({confirmation.jump_url})"
        for trainer in self.bot.guild_dict[ctx.guild.id].get('trainers', {}):
            user_stops = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('stops', [])
            user_items = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('items', [])
            if not checks.dm_check(ctx, trainer):
                continue
            if location.lower() in user_stops or item in user_items:
                try:
                    user = ctx.guild.get_member(trainer)
                    luredmmsg = await user.send(f"{lure_msg} in {ctx.channel.mention}", embed=lure_embed)
                    dm_dict[user.id] = luredmmsg.id
                except:
                    continue
        self.bot.guild_dict[ctx.guild.id]['lure_dict'][confirmation.id]['dm_dict'] = dm_dict
        lure_reports = ctx.bot.guild_dict[message.guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('lure_reports', 0) + 1
        self.bot.guild_dict[message.guild.id]['trainers'][message.author.id]['lure_reports'] = lure_reports

    @lure.command(aliases=['expire'])
    @checks.allowlurereport()
    @commands.has_permissions(manage_channels=True)
    async def reset(self, ctx, *, report_message=None):
        """Resets all lure reports."""
        author = ctx.author
        guild = ctx.guild
        message = ctx.message
        channel = ctx.channel

        # get settings
        lure_dict = copy.deepcopy(self.bot.guild_dict[guild.id].setdefault('lure_dict', {}))
        await utils.safe_delete(message)

        if not lure_dict:
            return
        if report_message and int(report_message) in lure_dict.keys():
            report_message = await channel.fetch_message(report_message)
            await self.expire_lure(report_message)
            return
        rusure = await channel.send(_('**Meowth!** Are you sure you\'d like to remove all lures?'))
        try:
            timeout = False
            res, reactuser = await utils.ask(self.bot, rusure, author.id)
        except TypeError:
            timeout = True
        if timeout or res.emoji == self.bot.config.get('answer_no', '\u274e'):
            await utils.safe_delete(rusure)
            confirmation = await channel.send(_('Manual reset cancelled.'), delete_after=10)
            return
        elif res.emoji == self.bot.config.get('answer_yes', '\u2705'):
            await utils.safe_delete(rusure)
            for report in lure_dict:
                report_message = await channel.fetch_message(report)
                self.bot.loop.create_task(self.expire_lure(report_message))
            confirmation = await channel.send(_('Lures reset.'), delete_after=10)
            return
        else:
            return

def setup(bot):
    bot.add_cog(Lure(bot))
