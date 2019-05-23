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

class Pvp(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.pvp_cleanup.start()

    def cog_unload(self):
        self.pvp_cleanup.cancel()

    @tasks.loop(seconds=0)
    async def pvp_cleanup(self, loop=True):
        while True:
            logger.info('------ BEGIN ------')
            guilddict_temp = copy.deepcopy(self.bot.guild_dict)
            expire_list = []
            count = 0
            for guildid in guilddict_temp.keys():
                pvp_dict = guilddict_temp[guildid].setdefault('pvp_dict', {})
                for reportid in pvp_dict.keys():
                    if pvp_dict[reportid].get('exp', 0) <= time.time():
                        report_channel = self.bot.get_channel(pvp_dict[reportid].get('reportchannel'))
                        if report_channel:
                            try:
                                report_message = await report_channel.fetch_message(reportid)
                                self.bot.loop.create_task(self.expire_pvp(report_message))
                                count += 1
                                continue
                            except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException):
                                pass
                        try:
                            del self.bot.guild_dict[guildid]['pvp_dict'][reportid]
                        except KeyError:
                            continue
                    to_expire = pvp_dict[reportid].get('exp', 0) - time.time()
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
            logger.info(f"------ END - {count} PVPs Cleaned - Waiting {min(expire_list)} seconds. ------")
            if not loop:
                return
            await asyncio.sleep(min(expire_list))
            continue

    @pvp_cleanup.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()

    async def expire_pvp(self, message):
        guild = message.channel.guild
        channel = message.channel
        pvp_dict = copy.deepcopy(self.bot.guild_dict[guild.id]['pvp_dict'])
        await utils.safe_delete(message)
        try:
            user_message = await channel.fetch_message(pvp_dict[message.id]['reportmessage'])
            await utils.safe_delete(user_message)
        except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException, KeyError):
            pass
        await utils.expire_dm_reports(self.bot, pvp_dict.get(message.id, {}).get('dm_dict', {}))
        try:
            del self.bot.guild_dict[guild.id]['pvp_dict'][message.id]
        except KeyError:
            pass

    @commands.group(invoke_without_command=True, case_insensitive=True)
    @checks.allowpvpreport()
    async def pvp(self, ctx, pvp_type=None, *, location:commands.clean_content(fix_channel_mentions=True)="", timer="30"):
        """Report a PVP battle request.

        Usage: !pvp [type] [location] [minutes]
        Guided report available with just !pvp"""
        message = ctx.message
        channel = message.channel
        author = message.author
        guild = message.guild
        timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset']))
        error = False
        pvp_embed = discord.Embed(colour=message.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/CombatButton.png?cache=1')
        pvp_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=author.display_name, timestamp=timestamp.strftime(_('%I:%M %p (%H:%M)'))), icon_url=author.avatar_url_as(format=None, static_format='jpg', size=32))
        while True:
            async with ctx.typing():
                if pvp_type and any([pvp_type.lower() == "any", pvp_type.lower() == "great", pvp_type.lower() == "ultra", pvp_type.lower() == "master"]) and location:
                    if location.split()[-1].isdigit():
                        timer = location.split()[-1]
                        location = location.replace(timer, '').strip()
                    if int(timer) > 720:
                        timer = "720"
                    await self._pvp(ctx, pvp_type, location, timer)
                    return
                else:
                    pvp_embed.add_field(name=_('**New PVP Request**'), value=_("Meowth! I'll help you report a PVP battle!\n\nFirst, I'll need to know what **type** of PVP battle you'd like to start. Reply with the **any, great, ultra, or master**. You can reply with **cancel** to stop anytime."), inline=False)
                    pvp_type_wait = await channel.send(embed=pvp_embed)
                    def check(reply):
                        if reply.author is not guild.me and reply.channel.id == channel.id and reply.author == message.author:
                            return True
                        else:
                            return False
                    try:
                        pvp_type_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        pvp_type_msg = None
                    await utils.safe_delete(pvp_type_wait)
                    if not pvp_type_msg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(pvp_type_msg)
                    if pvp_type_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    elif not any([pvp_type_msg.clean_content.lower() == "any", pvp_type_msg.clean_content.lower() == "great", pvp_type_msg.clean_content.lower() == "ultra", pvp_type_msg.clean_content.lower() == "master"]):
                        error = _("entered an invalid type")
                        break
                    else:
                        pvp_type = pvp_type_msg.clean_content.lower()
                        if pvp_type != "any":
                            pvp_embed.set_thumbnail(url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/pogo_{pvp_type}_league.png?cache=1")
                    pvp_embed.clear_fields()
                    pvp_embed.add_field(name="**New PVP Request**", value=f"Great! Now, reply with the **location** that you will be at for **{pvp_type} PVP** battles. You can reply with **cancel** to stop anytime.", inline=False)
                    location_wait = await channel.send(embed=pvp_embed)
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
                        poi_info = ""
                        if gym_matching_cog:
                            poi_info, location, poi_url = await gym_matching_cog.get_poi_info(ctx, location, "pvp")
                            if poi_url:
                                loc_url = poi_url
                        if not location:
                            return
                    pvp_embed.clear_fields()
                    pvp_embed.add_field(name="**New PVP Request**", value=f"Fantastic! Now, reply with the **minutes remaining** that you'll be available for **{pvp_type} PVP** battles. You can reply with **cancel** to stop anytime.", inline=False)
                    expire_wait = await channel.send(embed=pvp_embed)
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
                    elif not expire_msg.clean_content.isdigit():
                        error = _("didn't enter a number")
                        break
                    elif int(expire_msg.clean_content) > 720:
                        timer = "720"
                    elif expire_msg:
                        timer = expire_msg.clean_content
                    pvp_embed.remove_field(0)
                    break
        if not error:
            await self._pvp(ctx, pvp_type, location, timer)
        else:
            pvp_embed.clear_fields()
            pvp_embed.add_field(name=_('**PVP Request Cancelled**'), value=_("Meowth! Your report has been cancelled because you {error}! Retry when you're ready.").format(error=error), inline=False)
            confirmation = await channel.send(embed=pvp_embed, delete_after=10)
            await utils.safe_delete(message)

    async def _pvp(self, ctx, pvp_type, location, timer):
        dm_dict = {}
        timestamp = (ctx.message.created_at + datetime.timedelta(hours=self.bot.guild_dict[ctx.message.channel.guild.id]['configure_dict']['settings']['offset']))
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict']['settings']['offset'])
        end = now + datetime.timedelta(minutes=int(timer))
        pvp_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/TroyKey.png?cache=1')
        pvp_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=ctx.author.display_name, timestamp=timestamp.strftime(_('%I:%M %p (%H:%M)'))), icon_url=ctx.author.avatar_url_as(format=None, static_format='jpg', size=32))
        pvp_msg = _("PVP Requested by {author}").format(author=ctx.author.mention)
        pvp_embed.title = _('Meowth! Click here for my directions to the PVP!')
        pvp_embed.description = f"Ask {ctx.author.name} if my directions aren't perfect!\n**Location:** {location}"
        loc_url = utils.create_gmaps_query(self.bot, location, ctx.channel, type="pvp")
        gym_matching_cog = self.bot.cogs.get('GymMatching')
        stop_info = ""
        if gym_matching_cog:
            stop_info, location, stop_url = await gym_matching_cog.get_poi_info(ctx, location, "pvp", dupe_check=False)
            if stop_url:
                loc_url = stop_url
                pvp_embed.description = stop_info
        if not location:
            return
        pvp_embed.url = loc_url
        item = None
        pvp_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/CombatButton.png")
        pvp_embed.set_author(name=f"PVP Request", icon_url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/CombatButton.png?cache=1")
        if pvp_type != "any":
            pvp_embed.set_thumbnail(url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/pogo_{pvp_type}_league.png")
            pvp_embed.set_author(name=f"{pvp_type.title()} League PVP Request", icon_url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/pogo_{pvp_type}_league.png?cache=1")
        pvp_embed.add_field(name=f"**PVP Type:**", value=pvp_type.title())
        pvp_embed.add_field(name=f"**Available Until:**", value=end.strftime(_('%I:%M %p (%H:%M)')))
        confirmation = await ctx.channel.send(pvp_msg, embed=pvp_embed)
        test_var = self.bot.guild_dict[ctx.guild.id].setdefault('pvp_dict', {}).setdefault(confirmation.id, {})
        self.bot.guild_dict[ctx.guild.id]['pvp_dict'][confirmation.id] = {
            'exp':time.time() + int(timer)*60,
            'expedit':"delete",
            'reportmessage':ctx.message.id,
            'reportchannel':ctx.channel.id,
            'reportauthor':ctx.author.id,
            'dm_dict':dm_dict,
            'location':location,
            'url':loc_url,
            'type':pvp_type
        }

    @pvp.command(aliases=['expire'])
    @checks.allowpvpreport()
    @commands.has_permissions(manage_channels=True)
    async def reset(self, ctx, *, report_message=None):
        """Resets all PVP requests."""
        author = ctx.author
        guild = ctx.guild
        message = ctx.message
        channel = ctx.channel

        # get settings
        pvp_dict = copy.deepcopy(self.bot.guild_dict[guild.id].setdefault('pvp_dict', {}))
        await utils.safe_delete(message)

        if not pvp_dict:
            return
        if report_message and int(report_message) in pvp_dict.keys():
            report_message = await channel.fetch_message(report_message)
            await self.expire_pvp(report_message)
            return
        rusure = await channel.send(_('**Meowth!** Are you sure you\'d like to remove all PVP requests?'))
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
            for report in pvp_dict:
                report_message = await channel.fetch_message(report)
                self.bot.loop.create_task(self.expire_pvp(report_message))
            confirmation = await channel.send(_('PVPs reset.'), delete_after=10)
            return
        else:
            return

def setup(bot):
    bot.add_cog(Pvp(bot))
